#!/usr/bin/env bash

set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/channel-publisher-bot}"

cd "${APP_DIR}"

git fetch origin main
git reset --hard origin/main

docker compose build --pull
docker compose up -d --remove-orphans

docker compose ps
