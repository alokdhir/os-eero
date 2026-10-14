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

"""Events from consecutive snapshots: clients connecting, leaving, moving between eero units or bands, and
units going offline or coming back.

Pure functions over the client and unit lists as the API returns them (see docs/API.md): a client's unit is
source.url, its band interface.frequency; a unit is online when its state is ONLINE and its heartbeat is ok.
"""


def client_name(d):
    return d.get('nickname') or d.get('display_name') or d.get('hostname') or d.get('mac') or '?'


def _where(clients):
    """mac -> (unit url, unit location, band, name) for connected Wi-Fi clients (eero's wired list is mostly
    devices on the house switches, attributed to the nearest unit: no history for those)."""
    out = {}
    for d in clients or []:
        if not isinstance(d, dict) or not d.get('connected') or not d.get('mac') or not d.get('wireless'):
            continue
        src = d.get('source') or {}
        band = (d.get('interface') or {}).get('frequency')
        out[d['mac'].lower()] = (src.get('url'), src.get('location'), band, client_name(d))
    return out


def client_events(prev, cur, now):
    """Events between two client lists. Rows: (ts, mac, name, event, from_unit, to_unit, band_from, band_to);
    units are locations (names), falling back to the unit URL."""
    before, after = _where(prev), _where(cur)
    events = []
    for mac, (url, loc, band, name) in sorted(after.items()):
        old = before.get(mac)
        if old is None:
            events.append((now, mac, name, 'connected', None, loc or url, None, band))
        elif old[0] != url:
            events.append((now, mac, name, 'roamed', old[1] or old[0], loc or url, old[2], band))
        elif old[2] != band:
            events.append((now, mac, name, 'band', loc or url, loc or url, old[2], band))
    for mac, (url, loc, band, name) in sorted(before.items()):
        if mac not in after:
            events.append((now, mac, name, 'disconnected', loc or url, None, band, None))
    return events


def _online(units):
    out = {}
    for u in units or []:
        if isinstance(u, dict) and u.get('url'):
            out[u['url']] = (u.get('state') == 'ONLINE' and u.get('heartbeat_ok') is not False, u.get('location'))
    return out


def unit_events(prev, cur, now):
    """Rows: (ts, unit url, location, 'online'|'offline'). A unit that disappears from the list counts as
    offline; a new unit as online."""
    before, after = _online(prev), _online(cur)
    events = []
    for url, (up, loc) in sorted(after.items()):
        was = before.get(url)
        if was is None or was[0] != up:
            if was is None and not before:
                continue                    # first list ever seen: nothing to compare with
            events.append((now, url, loc, 'online' if up else 'offline'))
    for url, (up, loc) in sorted(before.items()):
        if url not in after and up:
            events.append((now, url, loc, 'offline'))
    return events
