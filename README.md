# Ghost DVR

Ghost DVR is an offline-first portable DVR app for local camera recording.

Supported targets include Raspberry Pi and Windows PC systems.

## Install On Raspberry Pi

Install Raspberry Pi OS first. After the Pi is booted and connected to the
internet, open a terminal on the Pi and run:

```bash
curl -fsSL https://raw.githubusercontent.com/MrIncHQ/GhostDVR/main/install_pi.sh | bash
```

The installer will:

* install `git`, `python3`, `python3-gpiozero`, and `ffmpeg`
* download Ghost DVR to `$HOME/GhostDVR`
* create the runtime folders
* make the Pi launch files executable
* create desktop launchers when the Pi has a Desktop folder

## First Setup

After install, run setup:

```bash
~/GhostDVR/Run_Ghost_DVR_Setup_Pi.sh
```

For an RTSP camera, choose:

```text
Source Type: rtsp
Source Name: your camera name
Source Address: your rtsp:// camera stream URL
```

For a USB camera on Raspberry Pi or Linux:

```text
Source Type: usb
Source Name: USB Camera
Source Address: /dev/video0
```

For a USB camera on Windows:

```text
Source Type: usb
Source Name: USB Camera
Source Address: video=Camera Name
```

The app saves local settings under:

```text
~/GhostDVR/runtime/
```

Do not upload or share that folder. It can contain camera credentials,
recordings, logs, and device identity.

## Start Ghost DVR

For a Pi with a screen:

```bash
~/GhostDVR/Run_Ghost_DVR_Pi.sh
```

For a headless Pi or browser-based control:

```bash
~/GhostDVR/Run_Ghost_DVR_API_Pi.sh
```

Then open this from another device on the same network:

```text
http://PI_IP_ADDRESS:8080
```

Replace `PI_IP_ADDRESS` with the Pi's actual IP address.

The API binds to `0.0.0.0` by default so other devices on your local network can
connect to it. If the browser says the connection was refused, make sure
`Run_Ghost_DVR_API_Pi.sh` is still running on the Pi.

The browser dashboard can view recordings, download recordings, show system
load, edit camera settings, and delete completed recordings. The dashboard is
intended for a trusted local network only. Do not port-forward it or expose it
directly to the internet.

The Recordings tab lets you choose how long a recording session runs: 15, 25,
30, 40, 60 minutes, or infinite. Infinite keeps recording until you stop it or
until the free disk space reaches the configured GB floor. Recordings are still
split into segment files while the session continues. The default segment length
is 15 minutes and can be changed with `recording.segment_minutes` in
`runtime/config.json`.

## Updating

Run the installer again:

```bash
curl -fsSL https://raw.githubusercontent.com/MrIncHQ/GhostDVR/main/install_pi.sh | bash
```

If Ghost DVR is already installed at `$HOME/GhostDVR`, the installer updates the
Git checkout instead of replacing the runtime folder.

If an update stops with a message like `local changes would be overwritten by
merge`, restore the launcher file and pull again:

```bash
cd ~/GhostDVR
git restore -- Run_Ghost_DVR_API_Pi.sh
git pull
chmod +x Run_Ghost_DVR_API_Pi.sh Run_Ghost_DVR_Pi.sh Run_Ghost_DVR_Setup_Pi.sh
```

The camera settings under `~/GhostDVR/runtime/` are ignored by Git and are not
removed by this.

## Raspberry Pi GPIO LED

The default status LED pin is GPIO 18.

On Raspberry Pi hardware, Ghost DVR tries to use the real GPIO LED backend
automatically. If GPIO is unavailable, it falls back to mock GPIO logging instead
of crashing.

To force or disable the GPIO backend, edit `~/GhostDVR/runtime/config.json`:

```json
"hardware": {
  "gpio_led_pin": 18,
  "gpio_led_backend": "auto"
}
```

`gpio_led_backend` accepts:

* `auto`
* `gpio`
* `mock`

## Windows PC

Windows can be used as a full local DVR target. A Windows PC can typically
handle more cameras than a Pi, depending on CPU, disk, and camera stream
settings.

Launch the Windows main screen:

```powershell
.\Run_Ghost_DVR.bat
```

Run first-time setup:

```powershell
.\Run_Ghost_DVR_Setup.bat
```

Run the local API:

```powershell
.\Run_Ghost_DVR_API.bat
```

Then open:

```text
http://127.0.0.1:8080
```

To use the dashboard from another device on your LAN, open the PC's local IP on
port `8080`.

Run tests:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
```

## Manual Pi Install From A Fork

To install from another GitHub repo or branch:

```bash
curl -fsSL https://raw.githubusercontent.com/MrIncHQ/GhostDVR/main/install_pi.sh | GHOST_DVR_REPO_URL=https://github.com/OWNER/REPO.git GHOST_DVR_BRANCH=main bash
```
