#!/usr/bin/env python3
"""Single-purpose Frigate updater for the frigate777 Docker Compose host."""

import http.server
import json
import logging
import os
import re
import shutil
import socketserver
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

COMPOSE = Path("/opt/docker-compose.yaml")
CONFIG = Path("/mnt/frigate-recordings/config")
BACKUPS = Path("/root/frigate-update-backups")
SOCKET = Path("/opt/frigate-updater/run/updater.sock")
IMAGE = "ghcr.io/chadakenn/frigate"
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
IMAGE_LINE = re.compile(r"^(\s+image:\s*)(\S+)(\s*(?:#.*)?)$")
state = {"phase": "idle", "message": "Checking for a release"}
logger = logging.getLogger(__name__)
lock = threading.Lock()
last_check = 0.0
available = None


def command(*arguments: str, timeout: int = 300) -> str:
    return subprocess.run(
        arguments, cwd="/opt", check=True, capture_output=True, text=True, timeout=timeout
    ).stdout


def current_image(contents: str) -> tuple[int, re.Match[str]]:
    lines = contents.splitlines(keepends=True)
    start = next(
        (i for i, line in enumerate(lines) if re.fullmatch(r"  frigate:\s*", line)),
        None,
    )
    if start is None:
        raise ValueError("Expected a Frigate service in Compose")
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^  [\w-]+:", lines[i])),
        len(lines),
    )
    matches = [(i, IMAGE_LINE.fullmatch(lines[i].rstrip("\n"))) for i in range(start + 1, end)]
    matches = [(i, match) for i, match in matches if match]
    if len(matches) != 1:
        raise ValueError("Expected one image in the Frigate service")
    index, match = matches[0]
    if not match[2].startswith((IMAGE + ":", "ghcr.io/blakeblackshear/frigate:")):
        raise ValueError("Unexpected image in the Frigate service")
    return index, match


def compose_with_image(contents: str, version: str) -> str:
    index, match = current_image(contents)
    lines = contents.splitlines(keepends=True)
    lines[index] = f"{match[1]}{IMAGE}:{version}{match[3]}\n"
    return "".join(lines)


def write_compose(contents: str) -> None:
    temporary = COMPOSE.with_suffix(".updater-tmp")
    temporary.write_text(contents)
    os.chmod(temporary, COMPOSE.stat().st_mode & 0o777)
    os.replace(temporary, COMPOSE)


def newest_image() -> str | None:
    global last_check, available
    if time.monotonic() - last_check < 300:
        return available
    request = urllib.request.Request(
        "https://api.github.com/repos/blakeblackshear/frigate/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "frigate-updater"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        version = json.load(response)["tag_name"].removeprefix("v")
    if not VERSION.fullmatch(version):
        raise ValueError("Latest stable version is invalid")
    # Never offer a version before the custom image actually exists.
    try:
        command("docker", "manifest", "inspect", f"{IMAGE}:{version}", timeout=30)
        available = version
    except subprocess.SubprocessError:
        available = None
    last_check = time.monotonic()
    return available


def health() -> bool:
    return command("docker", "inspect", "frigate", "--format", "{{.State.Health.Status}}").strip() == "healthy"


def run_update() -> None:
    previous = COMPOSE.read_text()
    backup = None
    stopped = False
    try:
        version = newest_image()
        if not version:
            raise ValueError("No custom image is published for the latest release")
        target = compose_with_image(previous, version)
        if target == previous:
            state.update(phase="complete", message=f"Already running {version}")
            return
        state.update(phase="pulling", message=f"Downloading Frigate {version}")
        command("docker", "pull", f"{IMAGE}:{version}", timeout=1800)
        backup = BACKUPS / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup.mkdir(parents=True, exist_ok=False)
        (backup / "docker-compose.yaml").write_text(previous)
        state.update(phase="installing", message="Stopping Frigate and backing up configuration")
        command("docker", "compose", "-f", str(COMPOSE), "stop", "frigate")
        stopped = True
        shutil.copytree(CONFIG, backup / "config")
        write_compose(target)
        command("docker", "compose", "-f", str(COMPOSE), "config", "--quiet")
        command("docker", "compose", "-f", str(COMPOSE), "up", "-d", "frigate")
        for _ in range(60):
            try:
                if health():
                    state.update(phase="complete", message=f"Frigate {version} is healthy")
                    return
            except subprocess.SubprocessError:
                pass
            time.sleep(5)
        raise RuntimeError("Frigate did not become healthy within five minutes")
    except Exception:
        logger.exception("Frigate update failed")
        state.update(phase="rollback", message="Update failed. Restoring previous version")
        try:
            if stopped:
                command("docker", "compose", "-f", str(COMPOSE), "stop", "frigate")
                write_compose(previous)
                if backup and (backup / "config").exists():
                    shutil.copytree(backup / "config", CONFIG, dirs_exist_ok=True)
                command("docker", "compose", "-f", str(COMPOSE), "up", "-d", "frigate")
            state.update(phase="failed", message="Update failed. Previous version restarted")
        except Exception:
            logger.exception("Frigate rollback failed")
            state.update(phase="failed", message="Rollback needs manual attention. Check updater service logs")
    finally:
        lock.release()


class Handler(http.server.BaseHTTPRequestHandler):
    def respond(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/status":
            return self.respond(404, {"error": "Not found"})
        result = state.copy()
        try:
            result["available"] = newest_image()
        except Exception:
            result["available"] = None
            result["message"] = "Cannot check for a new image right now"
        self.respond(200, result)

    def do_POST(self) -> None:
        if self.path != "/start":
            return self.respond(404, {"error": "Not found"})
        if not lock.acquire(blocking=False):
            return self.respond(409, {"error": "Update in progress"})
        state.update(phase="pulling", message="Starting update")
        threading.Thread(target=run_update, daemon=True).start()
        self.respond(202, state.copy())

    def log_message(self, format: str, *args: object) -> None:
        pass


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    SOCKET.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        os.chmod(SOCKET, 0o600)
        server.serve_forever()
