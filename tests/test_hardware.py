from __future__ import annotations

import logging
import unittest

from ghost_dvr.hardware.led import (
    GpioStatusLed,
    LedState,
    MockStatusLed,
    _pattern_for,
    create_status_led,
)
from ghost_dvr.hardware.profile import PI_4_PROFILE, WINDOWS_DEV_PROFILE


class HardwareTests(unittest.TestCase):
    def test_mock_led_tracks_current_state(self):
        led = MockStatusLed(logging.getLogger("test.hardware"), pin=18)

        led.set_state(LedState.ONLINE)
        self.assertEqual(led.state, LedState.ONLINE)

        led.set_state(LedState.RECORDING)
        self.assertEqual(led.state, LedState.RECORDING)

    def test_factory_uses_mock_led_for_windows_auto_backend(self):
        led = create_status_led(
            logger=quiet_logger("test.hardware.factory.windows"),
            hardware_config={"gpio_led_pin": 18, "gpio_led_backend": "auto"},
            hardware_profile=WINDOWS_DEV_PROFILE,
        )

        self.assertIsInstance(led, MockStatusLed)

    def test_factory_falls_back_to_mock_when_gpio_backend_unavailable(self):
        led = create_status_led(
            logger=quiet_logger("test.hardware.factory.fallback"),
            hardware_config={"gpio_led_pin": 18, "gpio_led_backend": "gpio"},
            hardware_profile=PI_4_PROFILE,
        )

        self.assertIsInstance(led, MockStatusLed)

    def test_gpio_led_tracks_state_with_injected_device(self):
        device = FakeOutputDevice()
        led = GpioStatusLed(
            logging.getLogger("test.hardware.gpio"),
            pin=18,
            device_factory=lambda pin: device,
        )
        try:
            led.set_state(LedState.RECORDING)

            self.assertEqual(led.state, LedState.RECORDING)
        finally:
            led.close()
        self.assertTrue(device.closed)

    def test_led_patterns_match_spec_states(self):
        self.assertEqual(_pattern_for(LedState.ONLINE), [(False, 1.0)])
        self.assertEqual(_pattern_for(LedState.BOOTING), [(True, 0.8), (False, 0.8)])
        self.assertEqual(_pattern_for(LedState.CONNECTING), [(True, 0.2), (False, 0.2)])
        self.assertEqual(_pattern_for(LedState.RECORDING), [(True, 1.0), (False, 0.2)])
        self.assertEqual(_pattern_for(LedState.OFFLINE), [(True, 0.1), (False, 0.1)])
        self.assertEqual(
            _pattern_for(LedState.STORAGE_WARNING),
            [(True, 0.15), (False, 0.15), (True, 0.15), (False, 1.0)],
        )
        self.assertEqual(_pattern_for(LedState.FATAL_ERROR), [(True, 0.5), (False, 0.5)])


class FakeOutputDevice:
    def __init__(self) -> None:
        self.closed = False

    def on(self) -> None:
        pass

    def off(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def quiet_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


if __name__ == "__main__":
    unittest.main()
