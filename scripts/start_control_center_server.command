#!/bin/zsh

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
BOOT_LOG="$REPO_ROOT/data/logs/control_center_server_boot.log"
SYSTEM_PYTHON_BIN="/usr/bin/python3"
VENV_PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

cd "$REPO_ROOT"

mkdir -p "$(dirname "$BOOT_LOG")"

log_line() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$BOOT_LOG"
}

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

WEB_HOST="$(read_env_value TRADINGX_WEB_HOST)"
WEB_PORT="$(read_env_value TRADINGX_WEB_PORT)"

if [[ -z "$WEB_HOST" ]]; then
  WEB_HOST="127.0.0.1"
fi

if [[ -z "$WEB_PORT" ]]; then
  WEB_PORT="8765"
fi

HEALTH_URL="http://$WEB_HOST:$WEB_PORT/api/config/summary"

if /usr/bin/curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
  log_line "server_already_running"
  exit 0
fi

if [[ ! -x "$SYSTEM_PYTHON_BIN" ]]; then
  log_line "system_python_missing"
  exit 1
fi

if [[ ! -x "$VENV_PYTHON_BIN" ]]; then
  log_line "venv_python_missing path=$VENV_PYTHON_BIN"
  exit 1
fi

REAL_PYTHON_BIN="$("$SYSTEM_PYTHON_BIN" - <<'PY' "$VENV_PYTHON_BIN"
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve())
PY
)"
PYTHON_VERSION="$("$REAL_PYTHON_BIN" - <<'PY'
import sys

print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
SITE_PACKAGES="$REPO_ROOT/.venv/lib/python$PYTHON_VERSION/site-packages"

log_line "real_python=$REAL_PYTHON_BIN"
log_line "python_version=$PYTHON_VERSION"
log_line "site_packages=$SITE_PACKAGES"

nohup "$REAL_PYTHON_BIN" - <<'PY' "$REPO_ROOT" "$ENV_FILE" "$SITE_PACKAGES" "$WEB_HOST" "$WEB_PORT" >>"$BOOT_LOG" 2>&1 &
import os
from pathlib import Path
import sys

repo_root = Path(sys.argv[1])
env_file = Path(sys.argv[2])
site_packages = Path(sys.argv[3])
host = sys.argv[4]
port = sys.argv[5]

os.chdir(repo_root)
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(site_packages))

from tradingx import __main__ as cli

raise SystemExit(
    cli.main(
        [
            "web",
            "--env-file",
            str(env_file),
            "--host",
            host,
            "--port",
            port,
        ]
    )
)
PY

disown || true
log_line "web_launch_dispatched"
exit 0
