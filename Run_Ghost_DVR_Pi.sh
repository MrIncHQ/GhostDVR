#!/usr/bin/env sh
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

export PYTHONPATH="$SCRIPT_DIR/src"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it with: sudo apt install python3"
  printf "Press Enter to close..."
  read -r _
  exit 1
fi

while :; do
  "$PYTHON_BIN" -m ghost_dvr.app --ui
  status=$?
  if [ "$status" -eq 75 ]; then
    echo
    echo "Ghost DVR updated. Restarting..."
    continue
  fi
  break
done

if [ "$status" -ne 0 ]; then
  echo
  echo "Ghost DVR exited with an error."
  printf "Press Enter to close..."
  read -r _
fi

exit "$status"
