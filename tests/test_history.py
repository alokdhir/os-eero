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
import unittest

from helpers import fixture_doc
from lib.history import client_events, unit_events

T = 1000


def clients():
    return copy.deepcopy(fixture_doc("devices")["data"])


def units():
    return copy.deepcopy(fixture_doc("eeros")["data"])


def by_mac(lst, mac):
    return next(d for d in lst if d["mac"] == mac)


class TestClientEvents(unittest.TestCase):
    def test_nothing_changed(self):
        self.assertEqual(client_events(clients(), clients(), T), [])

    def test_roam(self):
        before, after = clients(), clients()
        phone = by_mac(after, "02:00:00:00:03:02")                 # on Garage, 2.4 GHz
        hall = units()[0]
        phone["source"].update(url=hall["url"], location=hall["location"])
        phone["interface"]["frequency"] = "5"
        self.assertEqual(client_events(before, after, T),
                         [(T, "02:00:00:00:03:02", "phone-1", "roamed", "Garage", "Hallway", "2.4", "5")])

    def test_band_change_same_unit(self):
        before, after = clients(), clients()
        by_mac(after, "02:00:00:00:03:01")["interface"]["frequency"] = "2.4"
        ev = client_events(before, after, T)
        self.assertEqual([(e[3], e[4], e[5], e[6], e[7]) for e in ev], [("band", "Hallway", "Hallway", "5", "2.4")])

    def test_connect_and_disconnect(self):
        before, after = clients(), clients()
        by_mac(after, "02:00:00:00:03:04")["connected"] = True      # the tablet comes back
        by_mac(after, "02:00:00:00:03:03")["connected"] = False     # the printer leaves
        ev = sorted((e[1], e[3]) for e in client_events(before, after, T))
        self.assertEqual(ev, [("02:00:00:00:03:03", "disconnected"), ("02:00:00:00:03:04", "connected")])

    def test_wired_has_no_band(self):
        ev = client_events([], clients(), T)
        printer = next(e for e in ev if e[1] == "02:00:00:00:03:03")
        self.assertEqual(printer[7], "wired")

    def test_name_prefers_nickname(self):
        ev = client_events([], clients(), T)
        self.assertEqual(next(e for e in ev if e[1] == "02:00:00:00:03:01")[2], "Work laptop")

    def test_mac_case_ignored(self):
        before, after = clients(), clients()
        for d in after:
            d["mac"] = d["mac"].upper()
        self.assertEqual(client_events(before, after, T), [])


class TestUnitEvents(unittest.TestCase):
    def test_first_list_is_quiet(self):
        self.assertEqual(unit_events([], units(), T), [])

    def test_offline_and_back(self):
        before, after = units(), units()
        after[1]["state"] = "OFFLINE"
        after[1]["heartbeat_ok"] = False
        self.assertEqual(unit_events(before, after, T), [(T, after[1]["url"], "Garage", "offline")])
        self.assertEqual(unit_events(after, before, T + 60), [(T + 60, after[1]["url"], "Garage", "online")])

    def test_unit_removed_or_added(self):
        before, after = units(), units()
        gone = after.pop(2)
        self.assertEqual(unit_events(before, after, T), [(T, gone["url"], "Patio", "offline")])
        self.assertEqual(unit_events(after, before, T), [(T, gone["url"], "Patio", "online")])


if __name__ == "__main__":
    unittest.main()
