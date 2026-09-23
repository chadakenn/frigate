#!/usr/bin/env bash
# One-time setup for CT114. Review this script before running it as root.
set -euo pipefail

if (( EUID != 0 )); then
  echo "Run as root inside frigate777" >&2
  exit 1
fi

source_ref=${FRIGATE_UPDATER_REF:-feature/local-upstream-updater-v0.18}
source_url="https://raw.githubusercontent.com/chadakenn/frigate/${source_ref}/tools/host-updater"
base=/opt/docker-compose.yaml
updater_dir=/opt/frigate-updater
config_dir=/mnt/frigate-recordings/config
override="$updater_dir/docker-compose.updater.yaml"

test -f "$base"
test -d "$config_dir"
command -v git >/dev/null || { echo "git is required in the LXC" >&2; exit 1; }
install -d -m 700 "$updater_dir" "$updater_dir/run"
for filename in updater.py docker-compose.updater.yaml frigate-updater.service Dockerfile upstream-overlay.patch; do
  curl -fsSL "$source_url/$filename" -o "$updater_dir/$filename"
done
chmod 600 "$updater_dir/updater.py" "$override"
install -m 644 "$updater_dir/frigate-updater.service" /etc/systemd/system/frigate-updater.service

docker compose -f "$base" -f "$override" config --quiet
python3 "$updater_dir/updater.py" --build 0.18.0
systemctl daemon-reload
systemctl enable --now frigate-updater.service

config_bytes=$(du -sb "$config_dir" | cut -f1)
free_bytes=$(df -PB1 /root | awk 'NR == 2 { print $4 }')
if (( free_bytes < config_bytes + 1073741824 )); then
  echo "Insufficient free space in /root for the configuration backup" >&2
  exit 1
fi
backup="/root/frigate-before-button-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a "$base" "$backup/"
docker compose -f "$base" stop frigate
cp -a "$config_dir" "$backup/config"

restore() {
  echo "Install failed. Restoring the previous Frigate image and config." >&2
  docker compose -f "$base" -f "$override" stop frigate || true
  if [[ -d "$backup/config" ]]; then
    mv "$config_dir" "${config_dir}.failed-$(date -u +%Y%m%d-%H%M%S)" || true
    cp -a "$backup/config" "$config_dir"
  fi
  docker compose -f "$base" up -d frigate
}
trap restore ERR

docker compose -f "$base" -f "$override" up -d frigate
for attempt in $(seq 1 60); do
  if [[ $(docker inspect frigate --format '{{.State.Health.Status}}' 2>/dev/null) == healthy ]]; then
    trap - ERR
    echo "Custom Frigate 0.18.0 is healthy. Backup: $backup"
    exit 0
  fi
  sleep 5
done
echo "Frigate did not become healthy within five minutes" >&2
false
