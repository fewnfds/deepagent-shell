#!/usr/bin/env sh
set -eu

project=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
data=${1:-"$project/data"}
image=${AGENT_SHELL_IMAGE:-"ghcr.io/fewnfds/agent-shell:latest"}
mkdir -p "$data"
data=$(CDPATH= cd -- "$data" && pwd -P)
settings="$data/config/agent-shell.env"
uid=$(id -u)
gid=$(id -g)

docker run --rm -it \
  --user "$uid:$gid" \
  --mount "type=bind,source=$data,target=/app/data" \
  "$image" \
  python -I -B -m agent_shell \
  --home /app \
  --data-dir /app/data \
  --initialize-docker-settings

export COMPOSE_DATA_DIR="$data"
export AGENT_SHELL_UID="$uid"
export AGENT_SHELL_GID="$gid"
export AGENT_SHELL_IMAGE="$image"
docker compose \
  --project-directory "$project" \
  --env-file "$settings" \
  -f "$project/compose.yaml" \
  up -d --wait --wait-timeout 60

host_port=$(sed -n 's/^[[:space:]]*AGENT_SHELL_PORT[[:space:]]*=[[:space:]]*\([0-9][0-9]*\)[[:space:]]*$/\1/p' "$settings" | tail -n 1)
host_port=${host_port:-19100}
printf 'Agent Shell is ready: http://127.0.0.1:%s/admin\n' "$host_port"
printf 'Persistent data: %s\n' "$data"
