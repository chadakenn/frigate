# Frigate one-click update for CT114

This integration is specific to the Docker Compose service named `frigate` in
`/opt/docker-compose.yaml`. It uses `/mnt/frigate-recordings/config` for backups.
The updater runs in the LXC, outside the Frigate container. It accepts requests
only through a Unix socket; Frigate exposes an admin-only API for the button.

## Update flow

The helper checks the latest stable release on upstream GitHub. When an admin
clicks Update, it clones that exact upstream tag, checks and applies
`upstream-overlay.patch`, builds a Docker image locally using the matching
official image as the base, and only then stops recording. Frigate migrates its
configuration on startup. The helper backs up the stopped config and restores
the previous image and config if the new container fails to become healthy.

The local build requires Docker, Git, working internet access to GitHub and
GHCR, and enough free disk space in `/opt` for the source and Docker build.
If an upstream release changes code touched by the patch, `git apply --check`
fails before Frigate is stopped. The patch then needs to be ported to that
release. No image or modified Frigate code is published to a registry.

## One-time installation inside frigate777

Download and review `install.sh`, then run it as root inside the LXC. It carries
out the steps below, including a stopped database backup and rollback if the
custom image does not become healthy.

1. Copy `updater.py` to `/opt/frigate-updater/updater.py`, and the systemd unit
   to `/etc/systemd/system/frigate-updater.service`. Keep the script owned by
   root and not writable by other users.
2. Copy `Dockerfile`, `upstream-overlay.patch`, and `docker-compose.updater.yaml`
   into `/opt/frigate-updater/`. The Compose override adds the
   local image and a directory mount for the socket. It retains existing
   mounts and devices from `/opt/docker-compose.yaml`. Do not mount the Docker
   socket into the Frigate container.
3. Start the host helper with `systemctl daemon-reload` and
   `systemctl enable --now frigate-updater.service`.
4. Build the initial local image from upstream 0.18.0, back up the existing
   config and Compose file, check the merged configuration, and start with:

   ```sh
   python3 /opt/frigate-updater/updater.py --build 0.18.0
   docker compose -f /opt/docker-compose.yaml -f /opt/frigate-updater/docker-compose.updater.yaml config --quiet
   docker compose -f /opt/docker-compose.yaml -f /opt/frigate-updater/docker-compose.updater.yaml up -d frigate
   ```
5. Sign in to Frigate as admin, open System, and use the Update button when a
   newer upstream release is available. The helper builds it before interrupting
   recording, copies the stopped config and Compose file under
   `/root/frigate-update-backups`, then restarts and checks container health.

The button is only for authenticated admins. Frigate port 5000 is treated as an
internal admin port by upstream; the update API additionally requires a named
user. Restrict that port to trusted clients, as with a normal Frigate install.

If the update fails before restart, inspect
`journalctl -u frigate-updater.service`. The helper attempts to restore the
previous Compose image and config after a failed health check. Camera streams
and recording should be checked in the UI after every update; container health
does not verify each camera.
