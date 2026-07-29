#!/bin/sh
set -eu

# Bind mounts are commonly created by Docker as root. Align the unprivileged
# application account with the host owner on each start, without needing an
# image rebuild for a different Linux account.
bf_uid="${PUID:-1000}"
bf_gid="${PGID:-1000}"

if ! grep -q "^[^:]*:[^:]*:${bf_gid}:" /etc/group; then
  groupadd --gid "${bf_gid}" birdframe-host
fi
if [ "$(id -u birdframe)" != "${bf_uid}" ]; then
  usermod --uid "${bf_uid}" birdframe
fi
usermod --gid "${bf_gid}" birdframe

mkdir -p "${BIRDFRAME_DATA_DIR:-/data}"
chown -R "${bf_uid}:${bf_gid}" "${BIRDFRAME_DATA_DIR:-/data}"

exec gosu "${bf_uid}:${bf_gid}" "$@"
