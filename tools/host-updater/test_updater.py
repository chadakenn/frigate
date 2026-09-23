"""Checks that the host updater only changes the intended Compose service."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("host_updater", Path(__file__).with_name("updater.py"))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class ComposeReplacementTest(unittest.TestCase):
    def test_only_frigate_service_changes(self):
        original = (
            "services:\n"
            "  frigate:\n"
            "    image: ghcr.io/blakeblackshear/frigate:0.18.0\n"
            "    restart: unless-stopped\n"
            "  portainer:\n"
            "    image: portainer/portainer-ce:latest\n"
        )
        changed = updater.compose_with_image(original, "0.18.1")
        self.assertIn("ghcr.io/chadakenn/frigate:0.18.1", changed)
        self.assertIn("portainer/portainer-ce:latest", changed)
        self.assertEqual(changed, updater.compose_with_image(changed, "0.18.1"))

    def test_unexpected_image_is_rejected(self):
        with self.assertRaises(ValueError):
            updater.compose_with_image("services:\n  frigate:\n    image: attacker/image:tag\n", "0.18.1")

    def test_quoted_image_is_supported(self):
        original = 'services:\n  frigate:\n    image: "ghcr.io/blakeblackshear/frigate:0.18.0"\n'
        updated = updater.compose_with_image(original, "0.18.1")
        self.assertIn('image: "ghcr.io/chadakenn/frigate:0.18.1"', updated)


if __name__ == "__main__":
    unittest.main()
