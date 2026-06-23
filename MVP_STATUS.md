# Ghost DVR MVP Status

## Implemented

* Project structure
* Config creation and migration
* Persistent device identity
* Event logging
* Headless `status.json`
* Mock source
* RTSP source validation
* Source interface and factory
* Engine-owned source monitoring
* Tkinter main screen
* Single start/stop recording toggle
* FFmpeg recording command generation
* MKV segment recording for live-source stop/interruption safety
* Recording metadata creation and completion
* Storage monitoring
* Storage path selection with preferred external paths
* Mock GPIO status LED through HAL
* Raspberry Pi GPIO status LED backend through HAL
* Health monitor and recording recovery hook
* Internal API
* Local web interface
* Local timezone-aware status timestamps
* Hardware profile detection
* Console first-time source setup
* Windows click launchers
* Raspberry Pi launch scripts
* Raspberry Pi GitHub installer script
* Reolink RTSP preview and MKV recording validation on Windows

## Launchers

* `Run_Ghost_DVR.bat`
* `Run_Ghost_DVR_Setup.bat`
* `Uninstall_FFmpeg.bat`
* `Run_Ghost_DVR_Pi.sh`
* `Run_Ghost_DVR_Setup_Pi.sh`
* `Run_Ghost_DVR_API_Pi.sh`
* `install_pi.sh`

## Remaining Before Hardware Validation

* Decide whether to add MP4 remux/export after robust MKV capture.
* Validate storage behavior with real USB or SSD media.
* Run Raspberry Pi deployment testing.
* Validate real GPIO LED behavior on Raspberry Pi hardware.

## Deferred By Spec

* Plugins
* Playback
* Automatic camera discovery
* AI/object/facial detection
* Cloud features
* User accounts
* Mobile applications
