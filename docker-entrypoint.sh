#!/bin/sh
set -eu

workdir="${TG_SIGNER_WORKDIR:-/data/.signer}"
session_dir="${TG_SIGNER_SESSION_DIR:-/data/sessions}"
log_dir="${TG_SIGNER_LOG_DIR:-/data/logs}"
log_file="${TG_SIGNER_LOG_FILE:-/data/logs/tg-signer.log}"
host="${TG_SIGNER_GUI_HOST:-0.0.0.0}"
port="${TG_SIGNER_GUI_PORT:-8080}"

mkdir -p "$workdir" "$session_dir" "$log_dir"

set -- tg-signer \
  --session_dir "$session_dir" \
  --workdir "$workdir" \
  --log-dir "$log_dir" \
  --log-file "$log_file"

if [ -n "${TG_PROXY:-}" ]; then
  set -- "$@" --proxy "$TG_PROXY"
fi

set -- "$@" webgui -H "$host" -P "$port"

if [ -n "${TG_SIGNER_GUI_STORAGE_SECRET:-}" ]; then
  set -- "$@" -S "$TG_SIGNER_GUI_STORAGE_SECRET"
fi

if [ -n "${TG_SIGNER_GUI_AUTHCODE:-}" ]; then
  set -- "$@" --auth-code "$TG_SIGNER_GUI_AUTHCODE"
fi

exec "$@"
