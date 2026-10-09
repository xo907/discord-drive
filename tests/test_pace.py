"""Talking to Discord gently: requests are spaced out, and a "slow down" makes them slower for a while."""

import time
import unittest

import helpers  # noqa: F401
from discorddrive.discord_api import API_BASE, DiscordAPI, Pacer


class PaceTest(unittest.TestCase):
    def test_spacing(self):
        p = Pacer(per_minute=600)                     # one every 0.1 s
        t = time.monotonic()
        for _ in range(4):
            p.wait()
        self.assertGreaterEqual(time.monotonic() - t, 0.28)

    def test_slows_down_after_rate_limit(self):
        p = Pacer(per_minute=1200)                    # 0.05 s
        p.slow_down()
        p.wait()
        t = time.monotonic()
        p.wait()
        self.assertGreaterEqual(time.monotonic() - t, 0.07)    # 1.5x slower now

    def test_kinds_and_settings(self):
        api = DiscordAPI("token")
        self.assertEqual(api._kind("DELETE", API_BASE + "/channels/1/messages/2"), "delete")
        self.assertEqual(api._kind("POST", API_BASE + "/channels/1/messages"), "post")
        self.assertEqual(api._kind("GET", API_BASE + "/channels/1/messages/2"), "other")
        self.assertIsNone(api._kind("GET", "https://cdn.discordapp.com/attachments/1/2/x.bin"))
        self.assertAlmostEqual(api.pacers["delete"].interval, 4.0)          # gentle by default: 15 a minute
        api.set_pace("fast", deletes=6)
        self.assertAlmostEqual(api.pacers["delete"].interval, 10.0)         # an explicit number wins
        api.set_pace("off")
        self.assertEqual(api.pacers["post"].interval, 0)


if __name__ == "__main__":
    unittest.main()
