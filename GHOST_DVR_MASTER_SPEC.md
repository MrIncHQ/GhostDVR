# GHOST_DVR_MASTER_SPEC.md

# Project Name

Ghost DVR

---

# Project Mission

Ghost DVR is an open-source, offline-first, portable DVR platform designed for:

* Ghost hunting
* Paranormal investigations
* Wildlife monitoring
* Temporary surveillance
* Mobile camera deployments
* Remote field recording

Ghost DVR must remain simple, reliable, lightweight, and hardware agnostic.

No cloud services.

No subscriptions.

No vendor lock-in.

No mandatory internet connection.

---

# Primary User Workflow

The primary user experience should remain simple:

Power On

Verify Source

Press Record

Record Footage

Stop Recording

Power Off

Advanced functionality must never interfere with this workflow.

---

# Development Philosophy

Ghost DVR shall be developed primarily on Windows.

The Raspberry Pi is a deployment target.

Windows is the primary development target.

Developers should not require Raspberry Pi hardware for normal development.

Development cycle:

Code
->
Test on Windows
->
Debug on Windows
->
Deploy to Raspberry Pi
->
Validate Hardware

The Raspberry Pi should be the final validation environment.

---

# Mock Development Environment

Ghost DVR must support full development without camera hardware.

Required:

* Mock Video Source
* Mock GPIO
* Simulated Disconnects
* Simulated Reconnects

Developers must be able to test:

* UI
* Recording
* Logging
* Storage Monitoring
* API
* Web Interface

without requiring:

* Raspberry Pi
* Cameras
* PoE Hardware
* GPIO Devices

Example:

test_video.mp4

must function as a source.

---

# Supported Hardware

Minimum:

* Raspberry Pi Zero 2 W

Recommended:

* Raspberry Pi 4
* Raspberry Pi 5

Future:

* Orange Pi
* Rock Pi
* Other Linux SBCs

Avoid unnecessary Raspberry Pi specific dependencies.

---

# Hardware Profiles

Software shall automatically detect hardware.

Example Profiles:

Pi Zero 2 W

* Recommended Sources: 1
* Web UI Optional
* Playback Disabled

Pi 4

* Recommended Sources: 4
* Web UI Enabled

Pi 5

* Recommended Sources: User Defined
* Advanced Features Enabled

These are recommendations only.

Users may override limits through configuration.

---

# Open Source Requirements

Requirements:

* Public Source Code
* Community Contributions
* No Telemetry
* No Tracking
* No Mandatory Accounts
* No Cloud Dependencies

Recommended License:

MIT

---

# Core Architecture

System Layers:

UI Layer

Web Layer

API Layer

Engine Layer

Source Layer

Recording Layer

Hardware Layer

Each layer should be isolated.

The UI should never directly control recording.

The API should communicate with the engine.

The engine should control sources and recording.

---

# Source Based Architecture

Ghost DVR shall be source-driven rather than camera-driven.

The DVR engine must not depend on specific camera hardware.

Examples of Sources:

* RTSP Cameras
* ONVIF Cameras
* USB Cameras
* Pi Cameras
* HDMI Capture Devices
* RTMP Streams
* NDI Streams
* Local Video Files
* Future Plugin Sources

All sources must use a common interface.

---

# Source Interface

Each source must provide:

connect()

disconnect()

is_online()

get_stream()

get_source_name()

get_source_type()

This interface allows future expansion without changing the recorder.

---

# Version 1 Required Sources

Required:

* RTSP Source
* Mock Video Source

Future sources are not required for MVP.

---

# Device Identity System

Generate on first launch only.

Create:

* UUID
* Device ID
* Hostname

Example:

UUID:
2f8d2f2d-9c13-41f0-91db-1ef1c4d6a312

Device ID:
K8F3

Hostname:
ghostdvr-k8f3.local

Store permanently.

Never regenerate automatically.

Only regenerate during factory reset.

---

# Main User Interface

Single Screen Design.

Display:

* Device ID
* Source Status
* Recording Status
* Storage Status
* Recording Duration
* Live Preview

Buttons:

* Start Recording
* Stop Recording
* Exit

No advanced menus required.

---

# First Time Setup

Prompt for:

* Source Type
* Source Name
* Source Address
* Username
* Password
* Stream Path

Generate:

* UUID
* Device ID
* Hostname

Save configuration.

Launch Ghost DVR.

---

# Recording System

Use FFmpeg.

Requirements:

* No Video Re-Encoding
* Preserve Original Stream
* Split Recordings Automatically

Default Segment Length:

15 Minutes

Filename Format:

YYYY-MM-DD_HH-MM-SS.mp4

Create recording directories automatically.

---

# Recording Metadata

Each recording shall generate:

Video File

Metadata File

Example:

2026-06-22_20-00-00.mp4

2026-06-22_20-00-00.json

Metadata:

{
"device_id": "K8F3",
"source_name": "Basement Camera",
"source_type": "rtsp",
"recording_start": "2026-06-22T20:00:00",
"duration_seconds": 900
}

---

# Event Logging

Store logs in:

logs/events.log

Examples:

Source Connected

Source Disconnected

Recording Started

Recording Stopped

Storage Warning

System Boot

System Shutdown

---

# Storage Management

Monitor:

* Total Storage
* Used Storage
* Free Storage

Update every 5 seconds.

Default Warning:

10% Remaining

Storage Modes:

stop

overwrite_oldest

Default:

stop

---

# Automatic Recovery

System must recover from:

* Source Disconnects
* Network Failures
* Recording Process Failures
* Unexpected Shutdowns

System should attempt reconnect every 5 seconds.

---

# Status LED System

Support dedicated GPIO status LED.

Default GPIO:

18

States:

Booting:
Slow Blink

Connecting:
Fast Blink

Online:
Solid On

Recording:
Pulse

Offline:
Rapid Blink

Storage Warning:
Double Blink

Fatal Error:
Continuous Blink

---

# Mock GPIO

Required.

Windows development must not require physical GPIO.

Example:

[MOCK GPIO] LED ON

should appear in logs.

---

# Optional Future Buzzer

Future feature.

Not required for MVP.

Potential alerts:

* Disconnect
* Storage Full
* Recording Failure

Disabled by default.

---

# Local Web Interface

Disabled by default.

Purpose:

Monitor and control Ghost DVR remotely.

Access Examples:

http://ghostdvr-k8f3.local

http://192.168.8.10:8080

No internet required.

No cloud services.

---

# Web Interface Version 1

Display:

* Source Status
* Recording Status
* Storage Status
* Live Preview

Controls:

* Start Recording
* Stop Recording

---

# API Layer

Internal API required.

Examples:

GET /status

GET /sources

POST /record/start

POST /record/stop

GET /events

All future interfaces should communicate through the API.

---

# Multi-Source Future Support

Architecture shall support:

Source 1

Source 2

Source 3

Source N

Even if Version 1 only uses a single source.

Do not hardcode single-source assumptions.

---

# Plugin System

Future feature.

Examples:

* EMF Monitoring
* EVP Recording
* Temperature Sensors
* GPS Logging
* Environmental Sensors

Plugins must not require modification of core DVR code.

Plugins should communicate through APIs.

---

# Configuration Philosophy

Simple Users:

Use UI.

Advanced Users:

Edit JSON.

Developers:

Extend APIs and Plugins.

No feature should require source code modification when configuration is sufficient.

---

# Configuration Example

config.json

{
"device": {
"device_id": "K8F3",
"hostname": "ghostdvr-k8f3"
},

"hardware": {
"auto_detect": true,
"max_sources": 1,
"hardware_profile_override": false
},

"recording": {
"segment_minutes": 15,
"storage_warning_percent": 10,
"storage_mode": "stop",
"auto_reconnect": true
},

"web": {
"enabled": false,
"port": 8080
},

"features": {
"web_ui": false,
"gpio_led": true,
"gpio_buzzer": false,
"multi_source": false,
"plugins": false
}
}

---

# Technology Stack

Language:

Python 3.11+

Recommended Libraries:

* PySide6
* FFmpeg
* python-vlc
* gpiozero
* FastAPI
* JSON
* Logging

---

# MVP IMPLEMENTATION ORDER

Phase 1

* Project Structure
* Config System
* Device Identity Generation
* Logging System

Phase 2

* Source Interface
* Mock Source
* RTSP Source

Phase 3

* Main UI
* Source Status Monitoring

Phase 4

* Recording Engine
* Recording Controls

Phase 5

* Storage Monitoring
* Metadata Generation

Phase 6

* GPIO Status LED
* Mock GPIO

Phase 7

* Internal API

Phase 8

* Optional Local Web Interface

Phase 9

* Raspberry Pi Testing

Only after MVP stability should future features be implemented.

---

# Long-Term Goal

Ghost DVR should scale from:

Single Source Pi Zero Recorder

to

Multi-Source Pi 5 Investigation Hub

while maintaining:

* One Codebase
* One Configuration System
* One User Experience
* Offline First Operation
* Open Source Philosophy

# ADDITIONAL ARCHITECTURE REQUIREMENTS

These requirements are considered part of the core Ghost DVR specification.

---

# Hardware Abstraction Layer (HAL)

All hardware interactions must pass through a Hardware Abstraction Layer.

Purpose:

Allow the same codebase to operate on:

* Windows
* Raspberry Pi
* Future Linux SBCs

Examples:

LED Control

Real GPIO
or
Mock GPIO

Storage Access

Real Device
or
Mock Device

Buzzer Control

Real Hardware
or
Mock Hardware

The DVR engine must never directly communicate with hardware.

All hardware access must occur through HAL interfaces.

---

# Local Storage Priority

Storage should be selected using the following priority:

1. External USB Storage
2. External SSD Storage
3. Internal SD Card Storage

If external storage is available:

Recording should default to external storage.

Operating system storage should be avoided whenever possible.

---

# Source Naming Requirements

Each source must contain:

* Source Name
* Source Type
* Internal Source ID

Examples:

Basement Camera

Attic Camera

USB Webcam

Users should interact with names.

The engine should identify sources by internal IDs.

The engine should never rely on IP addresses as primary identifiers.

---

# Recording Safety Rules

While recording is active:

The following settings must be locked:

* Source Configuration
* Device Identity
* Storage Configuration

Users must stop recording before making these changes.

This prevents accidental corruption and unexpected behavior.

---

# Health Monitor Service

A dedicated background health monitor shall be implemented.

Monitor:

* Source Status
* Recording Status
* Storage Availability
* Memory Availability
* FFmpeg Process Health

If recording unexpectedly stops:

Log Event

Attempt Recovery

Notify User

The recorder should prioritize uninterrupted operation.

---

# Local Time Management

Ghost DVR must operate without internet access.

Users must be able to configure:

* Date
* Time
* Timezone

All logs and recordings must use local device time.

Internet time synchronization should never be required.

---

# Headless Status File

Create:

status.json

Update every 5 seconds.

Example:

{
"device_id": "K8F3",
"hostname": "ghostdvr-k8f3",
"recording": true,
"source_online": true,
"storage_free_gb": 182,
"timestamp": "2026-06-22T20:15:00"
}

Purpose:

Allow troubleshooting without launching the UI.

Useful for headless deployments.

---

# Portable Network Mode

Ghost DVR should support operation behind:

* Travel Routers
* Portable Routers
* Local Ethernet Networks
* Private Investigation Networks

Internet access is never required.

Hostname discovery should use:

mDNS

Examples:

ghostdvr-k8f3.local

ghostdvr-b91k.local

---

# Device Identity and Hostname Requirements

During first setup:

Generate:

* UUID
* Device ID
* Hostname

Example:

UUID:
2f8d2f2d-9c13-41f0-91db-1ef1c4d6a312

Device ID:
K8F3

Hostname:
ghostdvr-k8f3

Local URL:
http://ghostdvr-k8f3.local

Requirements:

Hostname must be randomly generated.

Hostname must be unique.

Hostname must be generated once.

Hostname must be stored permanently.

Hostname must never change automatically.

Hostname may only change if:

* User manually changes it
  or
* Factory reset occurs

This ensures stable local URLs.

Multiple Ghost DVR devices should be able to operate on the same network without conflicts.

---

# Future Recording Profiles

Future versions may support profiles.

Examples:

Ghost Hunt

Wildlife

Surveillance

Custom

Profiles may contain:

* Recording Settings
* Source Settings
* Storage Settings
* Plugin Settings

Profiles are not part of MVP.

---

# Not Part of MVP

The following features are intentionally excluded from MVP:

* AI Detection
* Object Detection
* Facial Recognition
* Cloud Recording
* User Accounts
* Authentication Systems
* Mobile Applications
* Plugin System
* Playback System
* Automatic Camera Discovery
* Internet Connectivity Requirements

These features may be considered after MVP stabilization.

---

# Development Rule

Windows is the primary development platform.

Raspberry Pi is the deployment platform.

All core functionality must be testable on Windows using:

* Mock Sources
* Mock GPIO
* Mock Storage
* Mock Hardware

Developers should not require physical hardware for routine development.

Hardware should only be required for final validation testing.

This requirement is considered mandatory.
