from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable, Protocol

from ghost_dvr.hardware.profile import HardwareProfile


class LedState(str, Enum):
    BOOTING = "booting"
    CONNECTING = "connecting"
    ONLINE = "online"
    RECORDING = "recording"
    OFFLINE = "offline"
    STORAGE_WARNING = "storage_warning"
    FATAL_ERROR = "fatal_error"


class StatusLed(Protocol):
    state: LedState

    def set_state(self, state: LedState) -> None:
        raise NotImplementedError


class GpioOutputDevice(Protocol):
    def on(self) -> None:
        raise NotImplementedError

    def off(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class MockStatusLed:
    def __init__(self, logger: logging.Logger, pin: int = 18) -> None:
        self.logger = logger
        self.pin = pin
        self.state = LedState.BOOTING
        self.logger.info("[MOCK GPIO] LED pin %s initialized", self.pin)

    def set_state(self, state: LedState) -> None:
        if state == self.state:
            return
        self.state = state
        self.logger.info("[MOCK GPIO] LED state: %s", state.value)


class GpioStatusLed:
    def __init__(
        self,
        logger: logging.Logger,
        pin: int = 18,
        device_factory: Callable[[int], GpioOutputDevice] | None = None,
    ) -> None:
        self.logger = logger
        self.pin = pin
        self.state = LedState.BOOTING
        self._state_changed = threading.Event()
        self._stop_requested = threading.Event()
        self._device = (device_factory or _gpiozero_output_device)(pin)
        self._thread = threading.Thread(
            target=self._run,
            name="ghost-dvr-gpio-led",
            daemon=True,
        )
        self._thread.start()
        self.logger.info("[GPIO] LED pin %s initialized", self.pin)

    def set_state(self, state: LedState) -> None:
        if state == self.state:
            return
        self.state = state
        self._state_changed.set()
        self.logger.info("[GPIO] LED state: %s", state.value)

    def close(self) -> None:
        self._stop_requested.set()
        self._state_changed.set()
        self._thread.join(timeout=1)
        self._device.off()
        self._device.close()

    def _run(self) -> None:
        while not self._stop_requested.is_set():
            state = self.state
            if state == LedState.ONLINE:
                self._device.on()
                self._wait_for_change(60)
                continue

            pattern = _pattern_for(state)
            for turn_on, delay in pattern:
                if turn_on:
                    self._device.on()
                else:
                    self._device.off()
                if self._wait_for_change(delay):
                    break

    def _wait_for_change(self, seconds: float) -> bool:
        changed = self._state_changed.wait(seconds)
        if changed:
            self._state_changed.clear()
        return changed


def create_status_led(
    *,
    logger: logging.Logger,
    hardware_config: dict[str, object],
    features_config: dict[str, object] | None = None,
    hardware_profile: HardwareProfile | None = None,
) -> StatusLed:
    pin = int(hardware_config.get("gpio_led_pin", 18))
    features = features_config or {}
    if features.get("gpio_led", True) is False:
        return MockStatusLed(logger, pin=pin)

    backend = str(hardware_config.get("gpio_led_backend", "auto")).lower()
    should_use_gpio = backend == "gpio" or (
        backend == "auto"
        and hardware_profile is not None
        and hardware_profile.is_raspberry_pi
    )
    if not should_use_gpio:
        return MockStatusLed(logger, pin=pin)

    try:
        return GpioStatusLed(logger, pin=pin)
    except Exception as exc:
        logger.warning("GPIO LED unavailable; using mock LED: %s", exc)
        return MockStatusLed(logger, pin=pin)


def _pattern_for(state: LedState) -> list[tuple[bool, float]]:
    if state == LedState.BOOTING:
        return [(True, 0.8), (False, 0.8)]
    if state == LedState.CONNECTING:
        return [(True, 0.2), (False, 0.2)]
    if state == LedState.RECORDING:
        return [(True, 1.0), (False, 0.2)]
    if state == LedState.OFFLINE:
        return [(True, 0.1), (False, 0.1)]
    if state == LedState.STORAGE_WARNING:
        return [(True, 0.15), (False, 0.15), (True, 0.15), (False, 1.0)]
    if state == LedState.FATAL_ERROR:
        return [(True, 0.5), (False, 0.5)]
    return [(False, 1.0)]


def _gpiozero_output_device(pin: int) -> GpioOutputDevice:
    try:
        from gpiozero import OutputDevice
    except ImportError as exc:
        raise RuntimeError(
            "gpiozero is not installed. Install it on Raspberry Pi with: sudo apt install python3-gpiozero"
        ) from exc
    return OutputDevice(pin)
