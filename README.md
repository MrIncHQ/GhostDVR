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

After install, you can run the setup launcher to create the first local camera
config:

```text
Run_Ghost_DVR_Setup_Pi.sh
```

This is optional if you plan to use the browser dashboard. The web dashboard has
a Cameras tab where you can add, remove, test, discover, and save cameras after
the API is running.

The setup launcher is still useful for local-only installs, quick first camera
setup, or systems where you do not want to use the browser dashboard.

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

## Launch Ghost DVR

Use the included launch files instead of typing Python commands. On Raspberry
Pi, use:

```text
Run_Ghost_DVR_Pi.sh        local lightweight DVR window
Run_Ghost_DVR_API_Pi.sh    web dashboard/API
Run_Ghost_DVR_Setup_Pi.sh  optional first setup
```

If the Pi has a desktop, the installer also creates desktop launchers when a
Desktop folder exists. If you are in a terminal, run the same files from
`~/GhostDVR/`.

The local window is intentionally lightweight. It can start and stop recording,
show preview/status, and change only the recording time and save folder.
It also shows the current version and has update controls. Stop recording before
running an update. Ghost DVR restarts itself after an update is applied when it
is started from the included launcher.

For a headless Pi or browser-based control, run `Run_Ghost_DVR_API_Pi.sh`, then
open this from another device on the same network. Replace `DEVICE_IP_ADDRESS`
with the IP address of the Pi or PC running Ghost DVR:

```text
http://DEVICE_IP_ADDRESS:8080
```

The API binds to `0.0.0.0` by default so other devices on your local network can
connect to it. If the browser says the connection was refused, make sure
`Run_Ghost_DVR_API_Pi.sh` is still running on the Pi.

The browser dashboard can view recordings, download recordings, show system
load, edit camera settings, discover cameras, switch light/dark mode, and delete
completed recordings. The dashboard is intended for a trusted local network
only. Do not port-forward it or expose it directly to the internet.

The Cameras tab can discover ONVIF cameras on the local network and suggest
common RTSP URLs. Some cameras still require entering the correct username,
password, or vendor-specific stream path before saving.

Recording downloads offer the original MKV and an MP4 export. Use MKV for the
original field recording. Use MP4 when a Windows player has trouble opening the
MKV file.

The Status tab shows the current version. Use **Check Updates** to check
immediately; if an update is found, Ghost DVR can apply it from that same prompt.
Stop recording before updating. Ghost DVR restarts itself after an update is
applied when it is started from the included launcher.

The Recordings tab lets you choose how long a recording session runs: 15, 25,
30, 40, 60 minutes, or infinite. Infinite keeps recording until you stop it or
until the free disk space reaches the configured GB floor. Recordings are still
split into segment files while the session continues. The default segment length
is 15 minutes and can be changed with `recording.segment_minutes` in
`runtime/config.json`.

When more than one camera is configured, **Start Recording** records every
online camera. Each camera gets its own recording files with the camera name in
the filename, for example:

```text
Camera_1_2026-06-28_19-22-02_000.mkv
Camera_2_2026-06-28_19-22-02_000.mkv
```

The Recordings tab also shows the active recording folder and lets you set a
preferred save folder. Leave it blank to use the default `runtime/recordings`
folder. Stop recording before changing the save folder.

## Updating

Run the installer again:

```bash
curl -fsSL https://raw.githubusercontent.com/MrIncHQ/GhostDVR/main/install_pi.sh | bash
```

If Ghost DVR is already installed at `$HOME/GhostDVR`, the installer updates the
Git checkout instead of replacing the runtime folder.

The camera settings under `~/GhostDVR/runtime/` are ignored by Git and are not
removed by this.

The dashboard updater can automatically restore known launcher-file drift before
pulling updates. If it reports other local changes, review those files manually
before updating.

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

Use the included Windows launch files:

```text
Run_Ghost_DVR.bat        local lightweight DVR window
Run_Ghost_DVR_API.bat    web dashboard/API
Run_Ghost_DVR_Setup.bat  optional first setup
```

After starting `Run_Ghost_DVR_API.bat`, open:

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

## License

Ghost DVR is released under the MIT License.
