# Frigate one-click update for CT114

This integration is specific to the Docker Compose service named `frigate` in
`/opt/docker-compose.yaml`. It uses `/mnt/frigate-recordings/config` for backups.
The updater runs in the LXC, outside the Frigate container. It accepts requests
only through a Unix socket; Frigate exposes an admin-only API for the button.

## Image build

Run the `Custom Frigate updater image` GitHub Actions workflow on this branch
with version `0.18.0`. Make the resulting GHCR package publicly readable before
installing it. The overlay starts with the official Frigate image and adds the
updated web UI and API routes. Build a corresponding image for each later
upstream release after checking that this overlay is compatible. The updater
will never offer a version without its custom image.

## One-time installation inside frigate777

Download and review `install.sh`, then run it as root inside the LXC. It carries
out the steps below, including a stopped database backup and rollback if the
custom image does not become healthy.

1. Copy `updater.py` to `/opt/frigate-updater/updater.py`, and the systemd unit
   to `/etc/systemd/system/frigate-updater.service`. Keep the script owned by
   root and not writable by other users.
2. Copy `docker-compose.updater.yaml` to
   `/opt/frigate-updater/docker-compose.updater.yaml`. This override adds the
   versioned image and a directory mount for the socket. It retains existing
   mounts and devices from `/opt/docker-compose.yaml`. Do not mount the Docker
   socket into the Frigate container.
3. Start the host helper with `systemctl daemon-reload` and
   `systemctl enable --now frigate-updater.service`.
4. Back up the existing config and Compose file. Check the merged configuration
   and start the customized image with:

   ```sh
   docker compose -f /opt/docker-compose.yaml -f /opt/frigate-updater/docker-compose.updater.yaml config --quiet
   docker compose -f /opt/docker-compose.yaml -f /opt/frigate-updater/docker-compose.updater.yaml up -d frigate
   ```
5. Sign in to Frigate as admin, open System, and use the Update button when a
   newer custom image is available. The helper downloads it before interrupting
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
