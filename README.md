# Ghost DVR

Ghost DVR is an offline-first, hardware-agnostic portable DVR platform.

## Development

Windows is the primary development target. Raspberry Pi hardware is a deployment
and validation target, not a requirement for normal development.

Run the Phase 1 bootstrap:

```powershell
$env:PYTHONPATH = "src"
python -m ghost_dvr.app
```

Launch the local main screen:

```powershell
$env:PYTHONPATH = "src"
python -m ghost_dvr.app --ui
```

On Windows, double-click `Run_Ghost_DVR.bat` to launch the main screen.
Double-click `Run_Ghost_DVR_Setup.bat` to configure the active video source.
Double-click `Uninstall_FFmpeg.bat` to remove the winget-installed FFmpeg after
testing.

Run the local API from a terminal:

```powershell
$env:PYTHONPATH = "src"
python -m ghost_dvr.app --api
```

Then open `http://127.0.0.1:8080` for the local web interface.

This creates local runtime files under `runtime/`:

* `config.json`
* `identity.json`
* `logs/events.log`
* `status.json`

Run tests:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
```

## Raspberry Pi Notes

Raspberry Pi deployment uses the same Python code and config file. The GPIO LED
backend is selected automatically on Raspberry Pi hardware when `gpiozero` is
available.

One-command GitHub install:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/GhostDVR/main/install_pi.sh | GHOST_DVR_REPO_URL=https://github.com/YOUR_USERNAME/GhostDVR.git bash
```

Replace `YOUR_USERNAME/GhostDVR` with the real GitHub owner and repo name. The
installer places the app in `$HOME/GhostDVR`, installs Pi dependencies, marks the
Pi launch files executable, and creates desktop launchers when a Desktop folder
exists.

After `REPO_URL` is set inside `install_pi.sh`, users can use the shorter form:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/GhostDVR/main/install_pi.sh | bash
```

Pi launch files:

* `Run_Ghost_DVR_Pi.sh` starts the main screen.
* `Run_Ghost_DVR_Setup_Pi.sh` opens the first-time setup prompt.
* `Run_Ghost_DVR_API_Pi.sh` starts the local web/API server for headless use.

Install the expected Pi packages:

```bash
sudo apt update
sudo apt install -y python3-gpiozero ffmpeg
```

If the Pi asks for permission to run the launch files, mark them executable once:

```bash
chmod +x Run_Ghost_DVR_Pi.sh Run_Ghost_DVR_Setup_Pi.sh Run_Ghost_DVR_API_Pi.sh
```

The default LED pin is GPIO 18. To force or disable real GPIO manually, edit
`runtime/config.json`:

```json
"hardware": {
  "gpio_led_pin": 18,
  "gpio_led_backend": "auto"
}
```

`gpio_led_backend` accepts `auto`, `gpio`, or `mock`.
