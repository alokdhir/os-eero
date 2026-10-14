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

import helpers  # noqa: F401
import query
from lib.session import SessionStore
from lib.store import Store


class TestStatus(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "eero.db")
        self.sessions = SessionStore(os.path.join(self._tmp.name, "s"))
        self.pidfile = os.path.join(self._tmp.name, "eero.pid")

    def tearDown(self):
        self._tmp.cleanup()

    def status(self):
        return query.status(self.db, self.sessions, self.pidfile)

    def test_never_started(self):
        st = self.status()
        self.assertEqual((st["status"], st["running"], st["session"]), ("stopped", False, {"signed_in": False}))

    def test_running_and_ok(self):
        with Store(self.db) as s:
            s.set_state(status="ok", last_ok=100, network={"url": "/2.2/networks/1", "name": "Example"})
            s.put("units", [], 100)
        self.sessions.save("tok-secret", now=50)
        with open(self.pidfile, "w") as f:
            f.write(str(os.getpid()))
        st = self.status()
        self.assertEqual((st["status"], st["network"], st["last_ok"], st["fetched"]), ("ok", "Example", 100, {"units": 100}))
        self.assertEqual(st["session"], {"signed_in": True, "since": 50})
        self.assertNotIn("tok-secret", repr(st))

    def test_stale_ok_when_not_running(self):
        with Store(self.db) as s:
            s.set_state(status="ok")
        with open(self.pidfile, "w") as f:
            f.write("999999")
        self.assertEqual(self.status()["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
