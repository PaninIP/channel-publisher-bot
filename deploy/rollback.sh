#!/usr/bin/env bash

set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/channel-publisher-bot}"
PREVIOUS_COMMIT_FILE="${APP_DIR}/.deploy/previous_commit"
TARGET_COMMIT="${TARGET_COMMIT:-}"
RESTORE_DB="${RESTORE_DB:-}"
RESTORE_MEDIA="${RESTORE_MEDIA:-}"

cd "${APP_DIR}"

if [[ -z "${TARGET_COMMIT}" ]]; then
    if [[ ! -f "${PREVIOUS_COMMIT_FILE}" ]]; then
        echo "Previous commit file not found: ${PREVIOUS_COMMIT_FILE}" >&2
        exit 1
    fi

    TARGET_COMMIT="$(<"${PREVIOUS_COMMIT_FILE}")"
fi

if [[ -n "${RESTORE_MEDIA}" ]]; then
    if [[ ! -f "${RESTORE_MEDIA}" ]]; then
        echo "Media backup not found: ${RESTORE_MEDIA}" >&2
        exit 1
    fi

    docker compose stop bot web
    rm -rf "${APP_DIR}/data/media"
    tar -C "${APP_DIR}/data" -xzf "${RESTORE_MEDIA}"
fi

if [[ -n "${RESTORE_DB}" ]]; then
    if [[ ! -f "${RESTORE_DB}" ]]; then
        echo "Database backup not found: ${RESTORE_DB}" >&2
        exit 1
    fi

    docker compose stop bot web
    cp --preserve=mode,timestamps "${RESTORE_DB}" "${APP_DIR}/data/app.db"
fi

git fetch --all --prune
git reset --hard "${TARGET_COMMIT}"

docker compose build
docker compose up -d --remove-orphans
docker compose ps

echo "Rollback completed: ${TARGET_COMMIT}"
