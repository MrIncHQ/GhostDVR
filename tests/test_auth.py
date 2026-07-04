from __future__ import annotations

import unittest

from ghost_dvr.auth import (
    auth_required,
    auth_status,
    configure_password,
    disable_auth,
    setup_required,
    verify_password,
)


class AuthTests(unittest.TestCase):
    def test_unset_auth_requires_setup(self):
        config = {"web_auth": {"mode": "unset"}}

        status = auth_status(config)

        self.assertTrue(status.setup_required)
        self.assertFalse(status.auth_enabled)
        self.assertFalse(status.authenticated)
        self.assertTrue(setup_required(config))

    def test_missing_auth_config_is_disabled_for_legacy_configs(self):
        config = {}

        status = auth_status(config)

        self.assertFalse(status.setup_required)
        self.assertFalse(status.auth_enabled)
        self.assertTrue(status.authenticated)

    def test_password_auth_hashes_and_verifies_password(self):
        config = {}

        configure_password(config, "local-pass-123")

        self.assertTrue(auth_required(config))
        self.assertNotIn("local-pass-123", str(config["web_auth"]))
        self.assertTrue(verify_password(config, "local-pass-123"))
        self.assertFalse(verify_password(config, "wrong-pass"))

    def test_password_must_be_at_least_eight_characters(self):
        with self.assertRaisesRegex(ValueError, "at least 8"):
            configure_password({}, "short")

    def test_disable_auth_marks_dashboard_open(self):
        config = {"web_auth": {"mode": "unset"}}

        disable_auth(config)

        self.assertFalse(auth_required(config))
        self.assertFalse(setup_required(config))
        self.assertTrue(auth_status(config).authenticated)


if __name__ == "__main__":
    unittest.main()
