# Copyright (C) 2026 Alok K. Dhir
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
# OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import copy
import os
import tempfile
import unittest

from helpers import fixture_doc
from lib import client as api
from lib.poller import BACKOFF_MIN, MAX_PER_MINUTE, Poller
from lib.session import SessionStore
from lib.store import Store

NET = "/2.2/networks/1000001"


class FakeClient:
    """Answers like lib.client.Client from the fixtures; `fail` maps a method name to exceptions to raise
    on its next calls."""

    def __init__(self, token):
        self.token = token
        self.calls = []
        self.fail = {}
        self.clients_doc = copy.deepcopy(fixture_doc("devices")["data"])

    def _call(self, name, value):
        self.calls.append(name)
        if self.fail.get(name):
            raise self.fail[name].pop(0)
        return copy.deepcopy(value)

    def networks(self):
        return self._call("networks", fixture_doc("account")["data"]["networks"]["data"])

    def network(self, net):
        return self._call("network", {"name": "Example", "url": net})

    def units(self, net):
        return self._call("units", fixture_doc("eeros")["data"])

    def clients(self, net):
        return self._call("clients", self.clients_doc)

    def speedtests(self, net):
        return self._call("speedtests", fixture_doc("speedtest")["data"])

    def thread(self, net):
        return self._call("thread", {"enabled": False})


class TestPoller(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self._tmp.name, "eero.db"))
        self.sessions = SessionStore(os.path.join(self._tmp.name, "s"))
        self.made = []
        self.poller = Poller(self.store, self.sessions, self.make, rand=lambda: 0.5)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def make(self, token):
        c = FakeClient(token)
        self.made.append(c)
        return c

    def run_for(self, start, seconds):
        return [self.poller.step(start + t) for t in range(seconds)]

    def test_prunes_to_the_setting(self):
        day = 86400
        now = 100 * day
        self.store.add_client_events([(now - 3 * day, "02:00:00:00:03:01", "a", "roamed", "x", "y", "5", "5"),
                                      (now - 1 * day, "02:00:00:00:03:01", "a", "roamed", "y", "x", "5", "5")])
        self.poller.keep_days = lambda: 2
        self.poller.step(now)
        self.assertEqual([e["ts"] for e in self.store.client_events(0)], [now - day])

    def test_signed_out_does_nothing(self):
        self.assertEqual(self.poller.step(0), "signed out")
        self.assertEqual(self.store.state()["status"], "needs_login")
        self.assertEqual(self.made, [])

    def test_first_round_and_schedule(self):
        self.sessions.save("tok")
        steps = self.run_for(0, 10)
        self.assertEqual(steps[:6], ["fetched networks", "fetched units", "fetched clients", "fetched network",
                                     "fetched speedtest", "fetched thread"])
        self.assertEqual(set(steps[6:]), {"idle"})
        st = self.store.state()
        self.assertEqual((st["status"], st["network"]["url"], st["last_ok"]), ("ok", NET, 5))
        # a minute later: units and clients again, nothing else
        self.assertEqual(self.run_for(61, 3), ["fetched units", "fetched clients", "idle"])
        # five minutes: the network too
        later = [s for s in self.run_for(300, 10) if s.startswith("fetched")]
        self.assertEqual(later, ["fetched units", "fetched clients", "fetched network"])

    def test_requests_per_minute_capped(self):
        self.sessions.save("tok")
        self.poller.sent = [0.0] * MAX_PER_MINUTE
        self.assertEqual(self.poller.step(1), "pacing")
        self.assertEqual(self.poller.step(60), "fetched networks")

    def test_roams_become_history(self):
        self.sessions.save("tok")
        self.run_for(0, 10)
        c = self.made[0]
        phone = next(d for d in c.clients_doc if d["mac"] == "02:00:00:00:03:02")
        hall = fixture_doc("eeros")["data"][0]
        phone["source"].update(url=hall["url"], location=hall["location"])
        self.run_for(61, 3)
        ev = self.store.client_events(0)
        self.assertEqual([(e["mac"], e["event"], e["from_unit"], e["to_unit"]) for e in ev],
                         [("02:00:00:00:03:02", "roamed", "Garage", "Hallway")])

    def test_history_start_recorded_once(self):
        self.sessions.save("tok")
        self.run_for(0, 10)
        self.assertNotIn("history_since", self.store.state())                  # nothing compared yet
        self.run_for(61, 3)
        self.assertEqual(self.store.state()["history_since"], 2)               # the first clients snapshot
        self.run_for(122, 3)
        self.assertEqual(self.store.state()["history_since"], 2)

    def test_no_history_across_a_long_gap(self):
        self.sessions.save("tok")
        self.run_for(0, 10)
        self.made[0].clients_doc[0]["connected"] = False
        self.run_for(5000, 3)                 # e.g. the daemon was stopped for an hour
        self.assertEqual(self.store.client_events(0), [])

    def test_session_ended_by_eero(self):
        self.sessions.save("tok")
        self.run_for(0, 10)
        self.made[0].fail["units"] = [api.SessionInvalid("error.session.invalid", 401)]
        self.assertEqual(self.run_for(61, 1), ["signed out by eero"])
        self.assertIsNone(self.sessions.load())
        self.assertEqual(self.store.fetched(), {})
        self.assertEqual(self.store.state()["status"], "needs_login")
        self.assertEqual(self.poller.step(62), "signed out")

    def test_new_session_picked_up(self):
        self.assertEqual(self.poller.step(0), "signed out")
        self.sessions.save("tok")
        self.assertEqual(self.poller.step(1), "fetched networks")

    def test_rate_limited_backs_off(self):
        self.sessions.save("tok")
        self.made_client = None
        self.poller.step(0)                                       # makes the client, fetches networks
        self.made[0].fail["units"] = [api.RateLimited("error.rate.limit", 429, retry_after=120)]
        self.assertEqual(self.poller.step(1), "rate limited")
        st = self.store.state()
        self.assertEqual((st["status"], st["next_try"]), ("rate_limited", 121))
        self.assertEqual(set(self.run_for(2, 119)), {"backing off"})
        self.assertEqual(self.poller.step(121), "fetched units")

    def test_errors_back_off_exponentially(self):
        self.sessions.save("tok")
        self.poller.step(0)
        c = self.made[0]
        c.fail["units"] = [api.TransportError("network: ConnectTimeout")] * 3
        self.assertEqual(self.poller.step(1), "error")
        self.assertEqual(self.store.state()["next_try"], 1 + BACKOFF_MIN)
        self.assertEqual(self.poller.step(1 + BACKOFF_MIN), "error")
        self.assertEqual(self.store.state()["next_try"], 1 + 3 * BACKOFF_MIN)
        self.assertIn("ConnectTimeout", self.store.state()["message"])
        self.assertEqual(self.poller.step(1 + 3 * BACKOFF_MIN), "error")
        c.fail.clear()
        self.assertEqual(self.poller.step(1 + 7 * BACKOFF_MIN), "fetched units")
        self.assertEqual(self.poller.failures, 0)

    def test_unavailable_kind_skipped(self):
        self.sessions.save("tok")
        self.poller.step(0)
        self.made[0].fail["thread"] = [api.NotAvailable("not available", 404)]
        steps = self.run_for(1, 10)
        self.assertIn("thread not available", steps)
        self.assertEqual(self.run_for(3600, 10).count("fetched thread"), 0)

    def test_status_not_rewritten_every_second(self):
        writes = []
        real = self.store.set_state
        self.store.set_state = lambda **kv: (writes.append(kv), real(**kv))
        self.run_for(0, 30)
        self.assertEqual(len(writes), 1)


if __name__ == "__main__":
    unittest.main()
