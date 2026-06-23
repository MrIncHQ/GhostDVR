# PortaDVR Continuation Note

Date: 2026-06-23

## Where We Left Off

Ghost DVR MVP scaffold is implemented and tests pass. Windows development
validation has moved from mock video to a real Reolink RTSP stream.

Latest verification:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
```

Result:

```text
Ran 72 tests ... OK
```

## Current Working Features

* Mock video preview works after installing FFmpeg through winget.
* FFmpeg package installed: `Gyan.FFmpeg 8.1.1`.
* `Uninstall_FFmpeg.bat` exists so FFmpeg can be removed after testing.
* Mock recording bug was fixed with `-re -stream_loop -1`, so MP4 behaves like a live source.
* Recording duration now updates in the UI.
* Preview frame grabbing runs in a background thread so the UI timer does not freeze.
* Setup validation only accepts `mock` or `rtsp`.
* Reolink RTSP preview works with the H.264 substream.
* Reolink recording now saves valid MKV segments.
* Recording/report/cleanup tools exist as internal CLI flags.
* Raspberry Pi GPIO LED backend is implemented behind the HAL with mock fallback.

## Important Current State

The active camera config uses the Reolink H.264 substream. Do not paste raw
`runtime/config.json` into chat because it contains camera credentials.

The user explicitly said not to auto-correct `rtps`. Invalid source types should
remain invalid and setup should reject them.

## Next Step

Validate the remaining hardware items:

* Real USB or SSD recording path behavior.
* Raspberry Pi deployment.
* Real GPIO LED behavior on Raspberry Pi hardware.
* Decide whether MP4 remux/export is worth adding after robust MKV capture.

## Useful Files

* `src/ghost_dvr/ui/main_window.py`
* `src/ghost_dvr/recording.py`
* `src/ghost_dvr/ffmpeg.py`
* `src/ghost_dvr/setup_wizard.py`
* `runtime/config.json`
* `runtime/logs/events.log`
