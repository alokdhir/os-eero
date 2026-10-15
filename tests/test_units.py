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


class TestRename(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions = SessionStore(os.path.join(self._tmp.name, "s"))
        self.sessions.save("tok-1")
        self.store = Store(os.path.join(self._tmp.name, "eero.db"))
        self.store.put("units", fixture_doc("eeros")["data"], 1000)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def rename(self, uid, name, client=None):
        return units.rename(client or FakeClient(), self.sessions, self.store, uid, name)

    def test_rename_updates_the_cache(self):
        c = FakeClient()
        self.assertEqual(self.rename("2000001", "  Front   hall ", c), {"result": "ok", "name": "Front hall"})
        self.assertEqual(c.calls, [("/2.2/eeros/2000001", "Front hall", "tok-1")])
        fetched, docs = self.store.get("units")
        self.assertEqual((fetched, docs[0]["location"]), (1000, "Front hall"))
        self.assertEqual(docs[2]["wireless_upstream_node"]["name"], "Front hall")    # Patio hangs off it

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


if __name__ == "__main__":
    unittest.main()
