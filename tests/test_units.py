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

import os
import tempfile
import unittest

from helpers import fixture_doc
import units
from lib import client as api
from lib.session import SessionStore
from lib.store import Store


class FakeClient:
    def __init__(self, fail=None):
        self.fail = fail
        self.token = None
        self.calls = []

    def set_location(self, unit, name):
        self.calls.append((unit, name, self.token))
        if self.fail:
            raise self.fail
        return {"location": name}

    def reboot(self, path):
        self.calls.append(("reboot", path, self.token))
        if self.fail:
            raise self.fail
        return None


class TestRename(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions = SessionStore(os.path.join(self._tmp.name, "s"))
        self.sessions.save("tok-1")
        self.store = Store(os.path.join(self._tmp.name, "eero.db"))
        self.store.put("units", fixture_doc("eeros")["data"], 1000)
        self.logged = []

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def rename(self, uid, name, client=None):
        return units.rename(client or FakeClient(), self.sessions, self.store, uid, name, "admin", self.logged.append)

    def reboot(self, target, client=None):
        return units.reboot(client or FakeClient(), self.sessions, self.store, target, "admin", self.logged.append)

    def test_rename_updates_the_cache(self):
        c = FakeClient()
        self.assertEqual(self.rename("2000001", "  Front   hall ", c), {"result": "ok", "name": "Front hall"})
        self.assertEqual(c.calls, [("/2.2/eeros/2000001", "Front hall", "tok-1")])
        fetched, docs = self.store.get("units")
        self.assertEqual((fetched, docs[0]["location"]), (1000, "Front hall"))
        self.assertEqual(docs[2]["wireless_upstream_node"]["name"], "Front hall")    # Patio hangs off it
        self.assertEqual(self.logged, ['unit "Hallway" renamed to "Front hall" by admin'])

    def test_refused_before_calling_eero(self):
        c = FakeClient()
        for uid, name in (("2000001", ""), ("2000001", "x" * 41), ("2000001", "a\x01b"), ("../x", "Den"),
                          ("9999999", "Den")):
            self.assertEqual(self.rename(uid, name, c)["result"], "failed", (uid, name))
        self.assertEqual(c.calls, [])
        self.sessions.clear()
        self.assertIn("Sign in", self.rename("2000001", "Den", c)["message"])
        self.assertEqual(c.calls, [])

    def test_eero_errors_leave_the_cache(self):
        for e, says in ((api.RateLimited("rate"), "limiting"), (api.TransportError("net"), "reach eero"),
                        (api.SessionInvalid("gone"), "Sign in"), (api.LoginFailed("error.bad"), "error.bad")):
            r = self.rename("2000001", "Den", FakeClient(e))
            self.assertEqual(r["result"], "failed")
            self.assertIn(says, r["message"])
        self.assertEqual(self.store.get("units")[1][0]["location"], "Hallway")
        self.assertTrue(all("failed" in line for line in self.logged))

    def test_reboot_a_unit(self):
        c = FakeClient()
        self.assertEqual(self.reboot("2000002", c), {"result": "ok"})
        self.assertEqual(c.calls, [("reboot", "/2.2/eeros/2000002/reboot", "tok-1")])
        self.assertEqual(self.logged, ['reboot of unit "Garage" requested by admin'])

    def test_reboot_the_network(self):
        c = FakeClient()
        self.assertIn("No eero network", self.reboot("all", c)["message"])          # not fetched yet
        self.store.set_state(network={"url": "/2.2/networks/1000001", "name": "Example"})
        self.assertEqual(self.reboot("all", c), {"result": "ok"})
        self.assertEqual(c.calls, [("reboot", "/2.2/networks/1000001/reboot", "tok-1")])
        self.assertEqual(self.logged, ['reboot of every unit in "Example" requested by admin'])

    def test_reboot_refused(self):
        c = FakeClient()
        for target in ("../x", "9999999", ""):
            self.assertEqual(self.reboot(target, c)["result"], "failed", target)
        self.sessions.clear()
        self.assertIn("Sign in", self.reboot("2000002", c)["message"])
        self.assertEqual(c.calls, [])
        self.sessions.save("tok-2")
        r = self.reboot("2000002", FakeClient(api.LoginFailed("error.eero.offline")))
        self.assertIn("refused the reboot (error.eero.offline)", r["message"])


if __name__ == "__main__":
    unittest.main()
