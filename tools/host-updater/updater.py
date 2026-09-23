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
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_COMPOSE = Path("/opt/docker-compose.yaml")
COMPOSE = Path("/opt/frigate-updater/docker-compose.updater.yaml")
CONFIG = Path("/mnt/frigate-recordings/config")
BACKUPS = Path("/root/frigate-update-backups")
SOCKET = Path("/opt/frigate-updater/run/updater.sock")
IMAGE = "frigate-local"
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
IMAGE_LINE = re.compile(r"^(\s+image:\s*)([\"']?)([^\"'\s]+)\2(\s*(?:#.*)?)$")
state = {"phase": "idle", "message": "Checking for a release"}
logger = logging.getLogger(__name__)
lock = threading.Lock()
last_check = 0.0
available = None


def command(*arguments: str, timeout: int = 300) -> str:
    return subprocess.run(
        arguments, cwd="/opt", check=True, capture_output=True, text=True, timeout=timeout
    ).stdout


def compose(*arguments: str) -> str:
    return command(
        "docker", "compose", "-f", str(BASE_COMPOSE), "-f", str(COMPOSE), *arguments
    )


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
    if not match[3].startswith((IMAGE + ":", "ghcr.io/blakeblackshear/frigate:")):
        raise ValueError("Unexpected image in the Frigate service")
    return index, match


def compose_with_image(contents: str, version: str) -> str:
    index, match = current_image(contents)
    lines = contents.splitlines(keepends=True)
    lines[index] = f"{match[1]}{match[2]}{IMAGE}:{version}{match[2]}{match[4]}\n"
    return "".join(lines)


def write_compose(contents: str) -> None:
    temporary = COMPOSE.with_suffix(".updater-tmp")
    temporary.write_text(contents)
    os.chmod(temporary, COMPOSE.stat().st_mode & 0o777)
    os.replace(temporary, COMPOSE)


def latest_version() -> str:
    global last_check, available
    if last_check and time.monotonic() - last_check < 300:
        return available
    request = urllib.request.Request(
        "https://api.github.com/repos/blakeblackshear/frigate/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "frigate-updater"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        version = json.load(response)["tag_name"].removeprefix("v")
    if not VERSION.fullmatch(version):
        raise ValueError("Latest stable version is invalid")
    available = version
    last_check = time.monotonic()
    return available


def build_image(version: str) -> None:
    """Fetch upstream source, apply our patch, and build an image on this host."""
    if not VERSION.fullmatch(version):
        raise ValueError("Only stable upstream version tags are supported")
    if shutil.disk_usage("/opt").free < 10 * 1024**3:
        raise RuntimeError("At least 10 GiB of free space is required to build")
    build_dir = Path(tempfile.mkdtemp(prefix="frigate-source-", dir="/opt"))
    try:
        command(
            "git", "clone", "--depth", "1", "--branch", f"v{version}",
            "https://github.com/blakeblackshear/frigate.git", str(build_dir),
            timeout=300,
        )
        patch = Path("/opt/frigate-updater/upstream-overlay.patch")
        command("git", "-C", str(build_dir), "apply", "--check", str(patch))
        command("git", "-C", str(build_dir), "apply", str(patch))
        command(
            "docker", "build", "-f", "/opt/frigate-updater/Dockerfile",
            "--build-arg", f"FRIGATE_VERSION={version}",
            "-t", f"{IMAGE}:{version}", str(build_dir), timeout=5400,
        )
    finally:
        shutil.rmtree(build_dir)


def health() -> bool:
    return command("docker", "inspect", "frigate", "--format", "{{.State.Health.Status}}").strip() == "healthy"


def run_update() -> None:
    previous = COMPOSE.read_text()
    backup = None
    stopped = False
    try:
        version = latest_version()
        target = compose_with_image(previous, version)
        if target == previous:
            state.update(phase="complete", message=f"Already running {version}")
            return
        state.update(phase="pulling", message=f"Fetching and building Frigate {version}")
        build_image(version)
        config_bytes = sum(
            path.stat().st_size for path in CONFIG.rglob("*") if path.is_file()
        )
        if shutil.disk_usage(BACKUPS.parent).free < config_bytes + 1024**3:
            raise RuntimeError("Insufficient space for the configuration backup")
        backup = BACKUPS / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup.mkdir(parents=True, exist_ok=False)
        (backup / "docker-compose.yaml").write_text(previous)
        state.update(phase="installing", message="Stopping Frigate and backing up configuration")
        compose("stop", "frigate")
        stopped = True
        shutil.copytree(CONFIG, backup / "config")
        write_compose(target)
        compose("config", "--quiet")
        compose("up", "-d", "frigate")
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
                compose("stop", "frigate")
                write_compose(previous)
                if backup and (backup / "config").exists():
                    failed_config = CONFIG.with_name(f"config.failed-{backup.name}")
                    CONFIG.rename(failed_config)
                    shutil.copytree(backup / "config", CONFIG)
                compose("up", "-d", "frigate")
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
            result["available"] = latest_version()
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
    if len(sys.argv) == 3 and sys.argv[1] == "--build":
        build_image(sys.argv[2])
        sys.exit(0)
    SOCKET.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        os.chmod(SOCKET, 0o600)
        server.serve_forever()
