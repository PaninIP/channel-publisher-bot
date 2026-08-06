#!/usr/bin/env bash

set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/channel-publisher-bot}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
HEALTH_RETRIES="${HEALTH_RETRIES:-12}"
HEALTH_DELAY_SECONDS="${HEALTH_DELAY_SECONDS:-5}"

cd "${APP_DIR}"

mkdir -p "${BACKUP_DIR}" "${APP_DIR}/.deploy"

PREVIOUS_COMMIT="$(git rev-parse HEAD)"
printf '%s\n' "${PREVIOUS_COMMIT}" > "${APP_DIR}/.deploy/previous_commit"

CODE_CHANGED=false

recover_after_error() {
    trap - ERR

    if [[ "${CODE_CHANGED}" == "true" ]]; then
        echo "Deployment failed. Rolling code back to ${PREVIOUS_COMMIT}."
        git reset --hard "${PREVIOUS_COMMIT}"
        docker compose build
    else
        echo "Deployment preparation failed. Starting existing containers."
    fi

    docker compose up -d --remove-orphans
}

trap recover_after_error ERR

TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DATABASE_PATH="${APP_DIR}/data/app.db"

if [[ -f "${DATABASE_PATH}" ]]; then
    DATABASE_BACKUP="${BACKUP_DIR}/app-${TIMESTAMP}.db"

    if command -v python3 >/dev/null 2>&1; then
        python3 - "${DATABASE_PATH}" "${DATABASE_BACKUP}" <<'PYBACKUP'
import sqlite3
import sys

source_path, destination_path = sys.argv[1:3]

with sqlite3.connect(source_path) as source:
    with sqlite3.connect(destination_path) as destination:
        source.backup(destination)
PYBACKUP
    else
        echo "python3 not found; stopping application for a consistent backup."
        docker compose stop bot web
        cp --preserve=mode,timestamps \
            "${DATABASE_PATH}" \
            "${DATABASE_BACKUP}"
    fi

    echo "Database backup: ${DATABASE_BACKUP}"
fi

git fetch origin main
git reset --hard origin/main
CODE_CHANGED=true

docker compose build --pull
docker compose up -d --remove-orphans

healthy=false

for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt += 1)); do
    if docker compose exec -T web python -c '
import urllib.request
urllib.request.urlopen(
    "http://127.0.0.1:8080/health",
    timeout=5,
).read()
'; then
        healthy=true
        break
    fi

    echo "Healthcheck attempt ${attempt}/${HEALTH_RETRIES} failed."
    sleep "${HEALTH_DELAY_SECONDS}"
done

service_is_running() {
    local service_name="$1"
    local container_id

    container_id="$(docker compose ps -q "${service_name}")"

    [[ -n "${container_id}" ]] \
        && [[ "$(docker inspect -f '{{.State.Running}}' "${container_id}")" == "true" ]]
}

if [[ "${healthy}" != "true" ]] \
    || ! service_is_running bot \
    || ! service_is_running web \
    || ! service_is_running caddy; then
    echo "Application did not become healthy."
    recover_after_error
    exit 1
fi

trap - ERR

docker compose ps
docker compose logs --tail=100 bot web caddy

find "${BACKUP_DIR}" \
    -maxdepth 1 \
    -type f \
    -name 'app-*.db' \
    -printf '%T@ %p\n' \
    | sort -nr \
    | tail -n +11 \
    | cut -d' ' -f2- \
    | xargs -r rm -f

echo "Deployment completed successfully."
