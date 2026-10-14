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
        self.assertEqual((laptop["name"], laptop["unit"], laptop["band"], laptop["signal"], laptop["quality"]),
                         ("Work laptop", "Hallway", "5 GHz · ch 36", -52, 5))
        self.assertEqual(next(r for r in now if r["mac"] == "02:00:00:00:03:02")["band"], "2.4 GHz · ch 6")
        self.assertEqual([query._channel(f) for f in (2412, 2484, 5745, 5975, 1234, None)], [1, 14, 149, 5, None, None])
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
        receiver = docs[4]
        receiver.update(hostname="020000000305", display_name="020000000305")   # calls itself by its MAC
        self.assertTrue({r["mac"]: r for r in query.clients(docs)}[receiver["mac"]]["vendor_name"])
        docs[0].update(nickname=None, hostname="Mac", display_name="Mac")       # Apple's placeholder
        self.assertTrue({r["mac"]: r for r in query.clients(docs)}[docs[0]["mac"]]["vendor_name"])

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



def ev(ts, event, frm, to, mac="02:00:00:00:03:02"):
    return {"ts": ts, "mac": mac, "name": "phone-1", "event": event, "from_unit": frm, "to_unit": to,
            "band_from": "5", "band_to": "5"}


class TestHistory(unittest.TestCase):
    def test_time_on_units(self):
        events = [ev(1100, "roamed", "Garage", "Hallway"), ev(1400, "disconnected", "Hallway", None),
                  ev(1500, "connected", None, "Patio")]
        self.assertEqual(query.time_on_units(events, 1000, 1600, "Garage"),
                         [("Hallway", 300), ("Garage", 100), (None, 100), ("Patio", 100)])

    def test_where_at(self):
        events = [ev(1100, "roamed", "Garage", "Hallway"), ev(1400, "disconnected", "Hallway", None)]
        self.assertEqual(query.where_at(events, 1000, "Patio"), "Garage")         # what the first move left
        self.assertEqual(query.where_at(events, 1200, "Patio"), "Hallway")        # after the roam
        self.assertIsNone(query.where_at(events, 1500, "Patio"))                  # after it left
        self.assertEqual(query.where_at([], 1000, "Patio"), "Patio")              # never moved
        self.assertIsNone(query.where_at([ev(1100, "connected", None, "Hallway")], 1000, "Patio"))

    def test_client_and_moves(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "eero.db")
            with Store(db) as s:
                s.put("clients", fixture_doc("devices")["data"], 5000)
                s.set_state(history_since=1000)
                s.add_client_events([(2000, "02:00:00:00:03:02", "phone-1", "roamed", "Hallway", "Garage", "5", "2.4"),
                                     (3000, "02:00:00:00:03:01", "laptop-1", "band", "Hallway", "Hallway", "5", "2.4"),
                                     (4000, "02:00:00:00:03:01", "laptop-1", "disconnected", "Hallway", None, "2.4", None)])
            page = query.client("02:00:00:00:03:02", 24, db_path=db, now=5000)
            self.assertEqual(page["client"]["name"], "phone-1")
            self.assertEqual(page["since"], 1000)                                  # not before history began
            self.assertEqual([(t["unit"], t["seconds"]) for t in page["time"]], [("Garage", 3000), ("Hallway", 1000)])
            self.assertEqual(sum(t["share"] for t in page["time"]), 100.0)
            self.assertEqual([e["event"] for e in page["events"]], ["roamed"])
            self.assertEqual(query.client("nope", 24, db_path=db), {"error": "invalid MAC address"})
            self.assertEqual([(m["mac"], m["event"]) for m in query.moves(24, db_path=db, now=5000)],
                             [("02:00:00:00:03:01", "band"), ("02:00:00:00:03:02", "roamed")])

    def test_no_history_yet(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "eero.db")
            with Store(db) as s:
                s.put("clients", fixture_doc("devices")["data"], 5000)
            page = query.client("02:00:00:00:03:02", 24, db_path=db, now=5000)
            self.assertEqual((page["time"], page["events"], page["since"]), ([], [], None))

    def test_hours_arg(self):
        self.assertEqual(query.hours_arg("168"), 168)
        self.assertEqual(query.hours_arg("99999"), query.MAX_HOURS)
        self.assertEqual(query.hours_arg("x"), 24)


if __name__ == "__main__":
    unittest.main()
