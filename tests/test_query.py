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

import json

from helpers import fixture_doc
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



class TestTabs(unittest.TestCase):
    def test_units(self):
        rows = query.units(fixture_doc("eeros")["data"])
        self.assertEqual([r["name"] for r in rows], ["Hallway", "Garage", "Patio"])
        hall, garage, patio = rows
        self.assertEqual((hall["backhaul"], hall["primary"], hall["online"]), ("Wired", True, True))
        self.assertEqual(garage["backhaul"], "Wired (PoE)")
        self.assertEqual(patio["backhaul"], "Wireless via Hallway (5 GHz)")
        self.assertEqual((patio["mesh"], patio["clients"], patio["uptime"]), (4, 1, 259200))
        self.assertEqual(hall["clients"], 2)                                       # Wi-Fi clients only
        self.assertEqual(hall["id"], "2000001")

    def test_offline_unit(self):
        docs = fixture_doc("eeros")["data"]
        docs[1]["state"] = "OFFLINE"
        self.assertFalse(query.units(docs)[1]["online"])

    def test_clients_connected_and_all(self):
        docs = fixture_doc("devices")["data"]
        now = query.clients(docs)
        self.assertNotIn("02:00:00:00:03:04", [r["mac"] for r in now])            # the tablet is away
        self.assertEqual(len(query.clients(docs, include_all=True)), 4)             # not the wired printer
        laptop = next(r for r in now if r["mac"] == "02:00:00:00:03:01")
        self.assertEqual((laptop["name"], laptop["unit"], laptop["band"], laptop["signal"], laptop["rate"]),
                         ("Work laptop", "Hallway", "5 GHz", -52, 865))
        self.assertNotIn("02:00:00:00:03:03", [r["mac"] for r in now])            # wired: left out
        self.assertTrue(laptop["named"])
        self.assertTrue(next(r for r in now if r["mac"] == "02:00:00:00:03:02")["private_mac"])

    def test_name_that_is_only_the_vendor(self):
        docs = fixture_doc("devices")["data"]
        fan = docs[1]
        fan.update(nickname=None, hostname=None, display_name="Example Wi-Fi Module Co.", manufacturer="Example Wi-Fi Module Co.")
        rows = {r["mac"]: r for r in query.clients(docs)}
        self.assertTrue(rows[fan["mac"]]["vendor_name"])
        self.assertFalse(rows["02:00:00:00:03:01"]["vendor_name"])     # nicknamed
        self.assertFalse(rows["02:00:00:00:03:05"]["vendor_name"])     # has a host name

    def test_names_passed_through_raw(self):
        """Escaping is the page's job (every text column has an escaping formatter); the data stays exact."""
        rows = query.clients(fixture_doc("devices")["data"])
        self.assertIn('tv "den" <b>', [r["name"] for r in rows])

    def test_network(self):
        groups = query.network(fixture_doc("network")["data"], fixture_doc("thread")["data"], fixture_doc("speedtest")["data"])
        flat = {label: value for g in groups for label, value in g["rows"]}
        self.assertTrue(flat["Mode"].startswith("Bridge"))
        self.assertEqual(flat["Guest network"], "Example Guest (on)")
        self.assertEqual(flat["Thread"], "Off")
        self.assertEqual(flat["Preferred update hour"], "03:00")
        self.assertEqual(flat["Download"], "940.5 Mbps")
        self.assertNotIn("SECRET", json.dumps(groups))
        self.assertEqual(query.network(None), [])

    def test_network_guest_without_name(self):
        net = fixture_doc("network")["data"]
        net["guest_network"].pop("name")
        flat = {label: value for g in query.network(net) for label, value in g["rows"]}
        self.assertEqual(flat["Guest network"], "unnamed (on)")


if __name__ == "__main__":
    unittest.main()
