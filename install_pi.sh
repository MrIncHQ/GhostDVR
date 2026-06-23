#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Ghost DVR"
INSTALL_DIR="${GHOST_DVR_INSTALL_DIR:-$HOME/GhostDVR}"
REPO_URL="${GHOST_DVR_REPO_URL:-https://github.com/YOUR_USERNAME/GhostDVR.git}"
BRANCH="${GHOST_DVR_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

LAUNCHERS=(
  "Run_Ghost_DVR_Pi.sh"
  "Run_Ghost_DVR_Setup_Pi.sh"
  "Run_Ghost_DVR_API_Pi.sh"
)

echo "$APP_NAME Raspberry Pi installer"
echo

if [ "$REPO_URL" = "https://github.com/YOUR_USERNAME/GhostDVR.git" ]; then
  echo "Installer needs the real GitHub repository URL first."
  echo "Edit install_pi.sh and set REPO_URL, or run with:"
  echo "GHOST_DVR_REPO_URL=https://github.com/YOUR_USERNAME/GhostDVR.git bash install_pi.sh"
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo was not found. Install dependencies manually, then rerun this script."
  exit 1
fi

echo "Installing system packages..."
sudo apt update
sudo apt install -y git python3 python3-gpiozero ffmpeg

echo
echo "Installing app to: $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Existing Git install found. Updating..."
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
elif [ -d "$INSTALL_DIR" ] && [ "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 | head -n 1)" ]; then
  echo "Install directory already exists and is not empty:"
  echo "$INSTALL_DIR"
  echo "Move it, remove it, or set GHOST_DVR_INSTALL_DIR to another path."
  exit 1
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
chmod +x "${LAUNCHERS[@]}"
mkdir -p runtime/recordings runtime/logs runtime/preview

if [ -d "$HOME/Desktop" ]; then
  echo "Creating desktop launchers..."
  for launcher in "${LAUNCHERS[@]}"; do
    name="${launcher%.sh}"
    desktop_file="$HOME/Desktop/$name.desktop"
    cat > "$desktop_file" <<EOF
[Desktop Entry]
Type=Application
Name=$name
Exec=$INSTALL_DIR/$launcher
Path=$INSTALL_DIR
Terminal=true
Categories=Utility;
EOF
    chmod +x "$desktop_file"
  done
fi

echo
echo "$APP_NAME installed."
echo
echo "Run setup first:"
echo "$INSTALL_DIR/Run_Ghost_DVR_Setup_Pi.sh"
echo
echo "Start the main screen:"
echo "$INSTALL_DIR/Run_Ghost_DVR_Pi.sh"
echo
echo "For headless/API mode:"
echo "$INSTALL_DIR/Run_Ghost_DVR_API_Pi.sh"
