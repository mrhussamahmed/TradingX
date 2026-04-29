#!/bin/zsh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
BOOT_LOG="$REPO_ROOT/data/logs/control_center_server_boot.log"
VENV_PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
FALLBACK_REAL_PYTHON_BIN="/Users/ahmedabd/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3.12"

mkdir -p "$(dirname "$BOOT_LOG")"

log_line() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$BOOT_LOG"
}

exec 2>> "$BOOT_LOG"
trap 'STATUS=$?; if [[ "$STATUS" -ne 0 ]]; then log_line "server_shell_exit status=$STATUS line=$LINENO"; fi' EXIT

read_env_value() {
  local key="$1"
  /usr/bin/awk -F= -v key="$key" '
    $1 == key {
      gsub(/\r/, "", $2)
      print $2
      exit
    }
  ' "$ENV_FILE"
}

if ! cd "$REPO_ROOT"; then
  log_line "repo_chdir_failed path=$REPO_ROOT"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  log_line "env_missing path=$ENV_FILE"
  exit 1
fi

WEB_HOST="$(read_env_value TRADINGX_WEB_HOST)"
WEB_PORT="$(read_env_value TRADINGX_WEB_PORT)"

if [[ -z "$WEB_HOST" ]]; then
  WEB_HOST="127.0.0.1"
fi

if [[ -z "$WEB_PORT" ]]; then
  WEB_PORT="8765"
fi

BROWSER_HOST="$WEB_HOST"
if [[ "$BROWSER_HOST" == "0.0.0.0" ]]; then
  BROWSER_HOST="127.0.0.1"
fi

CONFIG_HEALTH_URL="http://$BROWSER_HOST:$WEB_PORT/api/config/summary"
PORTFOLIO_HEALTH_URL="http://$BROWSER_HOST:$WEB_PORT/api/platform/portfolio"

if /usr/bin/curl -fsS --max-time 2 "$CONFIG_HEALTH_URL" >/dev/null 2>&1 \
  && /usr/bin/curl -fsS --max-time 2 "$PORTFOLIO_HEALTH_URL" >/dev/null 2>&1; then
  log_line "server_already_running"
  exit 0
fi

if [[ ! -x "$VENV_PYTHON_BIN" ]]; then
  log_line "venv_python_missing path=$VENV_PYTHON_BIN"
  exit 1
fi

REAL_PYTHON_BIN="$VENV_PYTHON_BIN"
if [[ -L "$VENV_PYTHON_BIN" ]]; then
  LINK_TARGET="$(/usr/bin/readlink "$VENV_PYTHON_BIN" || true)"
  log_line "venv_link_target=$LINK_TARGET"
  if [[ -z "$LINK_TARGET" && -x "$FALLBACK_REAL_PYTHON_BIN" ]]; then
    REAL_PYTHON_BIN="$FALLBACK_REAL_PYTHON_BIN"
    log_line "venv_link_target_empty_using_fallback=$FALLBACK_REAL_PYTHON_BIN"
  elif [[ -z "$LINK_TARGET" ]]; then
    log_line "venv_readlink_failed path=$VENV_PYTHON_BIN"
    exit 1
  elif [[ "$LINK_TARGET" == /* ]]; then
    REAL_PYTHON_BIN="$LINK_TARGET"
  else
    REAL_PYTHON_BIN="$(cd "$(dirname "$VENV_PYTHON_BIN")" && cd "$(dirname "$LINK_TARGET")" && pwd)/$(basename "$LINK_TARGET")"
  fi
fi

if [[ ! -x "$REAL_PYTHON_BIN" ]]; then
  log_line "real_python_missing path=$REAL_PYTHON_BIN"
  exit 1
fi

PYTHON_SITE_VERSION="$("$REAL_PYTHON_BIN" -I -S - <<'PY' || true
import sys

print(f"python{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ -z "$PYTHON_SITE_VERSION" ]]; then
  PYTHON_SITE_VERSION="python3.12"
fi

SITE_PACKAGES="$REPO_ROOT/.venv/lib/$PYTHON_SITE_VERSION/site-packages"
if [[ ! -d "$SITE_PACKAGES" ]]; then
  log_line "site_packages_missing path=$SITE_PACKAGES"
  exit 1
fi

log_line "real_python=$REAL_PYTHON_BIN"
log_line "python_site_version=$PYTHON_SITE_VERSION"
log_line "site_packages=$SITE_PACKAGES"
log_line "web_launch_start host=$WEB_HOST port=$WEB_PORT"

exec "$REAL_PYTHON_BIN" -I -S - "$REPO_ROOT" "$ENV_FILE" "$SITE_PACKAGES" "$WEB_HOST" "$WEB_PORT" <<'PY'
import os
import site
import sys

repo_root = sys.argv[1]
env_file = sys.argv[2]
site_packages = sys.argv[3]
host = sys.argv[4]
port = sys.argv[5]

os.chdir(repo_root)
sys.path.insert(0, repo_root + "/src")
site.addsitedir(site_packages)

from tradingx import __main__ as cli

raise SystemExit(
    cli.main(
        [
            "web",
            "--env-file",
            env_file,
            "--host",
            host,
            "--port",
            port,
        ]
    )
)
PY
