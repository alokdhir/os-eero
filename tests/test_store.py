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
import stat
import tempfile
import unittest

import helpers  # noqa: F401
from lib.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "eero", "eero.db")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_private(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(self.path)).st_mode), 0o700)

    def test_snapshots(self):
        self.assertEqual(self.store.get("units"), (None, None))
        self.store.put("units", [{"url": "/2.2/eeros/1"}], 100)
        self.store.put("units", [{"url": "/2.2/eeros/2"}], 160)
        self.assertEqual(self.store.get("units"), (160, [{"url": "/2.2/eeros/2"}]))
        self.assertEqual(self.store.fetched(), {"units": 160})
        self.store.forget()
        self.assertEqual(self.store.fetched(), {})

    def test_state(self):
        self.store.set_state(status="ok", message=None, network={"name": "Example"})
        self.store.set_state(status="error", message="Cannot reach eero")
        self.assertEqual(self.store.state(), {"status": "error", "message": "Cannot reach eero",
                                              "network": {"name": "Example"}})

    def test_events_and_prune(self):
        day = 86400
        self.store.add_client_events([(1 * day, "02:00:00:00:03:02", "phone-1", "roamed", "A", "B", "5", "5"),
                                      (40 * day, "02:00:00:00:03:02", "phone-1", "roamed", "B", "A", "5", "2.4"),
                                      (40 * day, "02:00:00:00:03:01", "laptop-1", "connected", None, "A", None, "5")])
        self.store.add_unit_events([(1 * day, "/2.2/eeros/1", "A", "offline"), (40 * day, "/2.2/eeros/1", "A", "online")])
        self.assertEqual(len(self.store.client_events(0)), 3)
        self.assertEqual([e["to_unit"] for e in self.store.client_events(0, mac="02:00:00:00:03:02")], ["A", "B"])
        self.store.prune(41 * day, days=30)
        self.assertEqual(len(self.store.client_events(0)), 2)
        self.assertEqual([e["event"] for e in self.store.unit_events(0)], ["online"])

    def test_readonly_reader(self):
        self.store.set_state(status="ok")
        with Store(self.path, readonly=True) as r:
            self.assertEqual(r.state(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
