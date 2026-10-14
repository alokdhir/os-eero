#!/usr/local/bin/python3
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

"""Answers for the GUI, from eerod's cache (never calls eero). Run by configd: `eero query <what>`.

  status          the status line: signed in or not, polling or not, last update, network name
  units           rows for the Units tab
  clients [all]   rows for the Clients tab: Wi-Fi clients connected now, or all the network remembers
  network         the Network tab: settings and health, grouped
  client <mac> <hours>   one client's page: now, time on each eero, its moves
  moves <hours>          recent moves (roams and band changes) across all clients
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import store as cache                 # noqa: E402
from lib.session import SessionStore           # noqa: E402

PIDFILE = '/var/run/eero.pid'


def running(pidfile=PIDFILE):
    try:
        with open(pidfile) as f:
            os.kill(int(f.read().strip()), 0)
    except (OSError, ValueError):
        return False
    return True


def status(db_path=cache.PATH, sessions=None, pidfile=PIDFILE):
    sessions = sessions or SessionStore()
    out = {'running': running(pidfile), 'session': sessions.info()}
    try:
        with cache.Store(db_path, readonly=True) as s:
            state = s.state()
            out['fetched'] = s.fetched()
    except Exception:                           # no cache yet (never started), or unreadable
        state, out['fetched'] = {}, {}
    out['status'] = state.get('status', 'stopped') if out['running'] else 'stopped'
    for key in ('message', 'last_ok', 'next_try'):
        out[key] = state.get(key)
    out['network'] = (state.get('network') or {}).get('name')
    return out


def _cached(kind, db_path=cache.PATH):
    try:
        with cache.Store(db_path, readonly=True) as s:
            return s.get(kind)[1]
    except Exception:
        return None


def _unit_id(url):
    return (url or '').rstrip('/').rsplit('/', 1)[-1]


BACKHAUL = {'WIRED': 'Wired', 'WIRED_POE': 'Wired (PoE)', 'WIRELESS': 'Wireless'}


def units(docs):
    """One row per eero unit."""
    rows = []
    for u in docs or []:
        if not isinstance(u, dict):
            continue
        up = u.get('wireless_upstream_node') or {}
        backhaul = BACKHAUL.get(u.get('connection_type'), u.get('connection_type') or '')
        if up:
            backhaul += ' via %s' % up.get('name', '?') + (' (%s)' % up['primary_mesh_radio'].replace('GHz', ' GHz')
                                                          if up.get('primary_mesh_radio') else '')
        rows.append({
            'id': _unit_id(u.get('url')),
            'name': u.get('location') or u.get('serial') or '?',
            'model': u.get('model') or '',
            'online': u.get('state') == 'ONLINE' and u.get('heartbeat_ok') is not False,
            'ip': u.get('ip_address') or '',
            'backhaul': backhaul,
            'mesh': u.get('mesh_quality_bars'),
            'clients': u.get('connected_wireless_clients_count'),     # wired counts include switch devices
            'firmware': (u.get('os_version') or '') + (' (update available)' if u.get('update_available') else ''),
            'uptime': (u.get('uptime') or {}).get('since_last_reboot_s'),
            'primary': bool(u.get('is_primary_node')),
        })
    return rows


def _dbm(text):
    m = re.match(r'\s*(-?[0-9]+)', str(text or ''))
    return int(m.group(1)) if m else None


def _channel(mhz):
    """Wi-Fi channel number from the frequency in MHz (2.4, 5 and 6 GHz), or None."""
    if not isinstance(mhz, int):
        return None
    if mhz == 2484:
        return 14
    if 2412 <= mhz < 2484:
        return (mhz - 2407) // 5
    if 5150 <= mhz < 5900:
        return (mhz - 5000) // 5
    if 5925 <= mhz <= 7125:
        return (mhz - 5950) // 5
    return None


# names Apple devices give with a private Wi-Fi address instead of their own (as in os-loupe)
PLACEHOLDERS = {'mac', 'iphone', 'ipad', 'watch', 'apple-watch', 'ipod', 'localhost'}


def _no_name(d):
    shown = (d.get('display_name') or '').strip()
    if shown.lower() in PLACEHOLDERS:
        return True
    if not d.get('hostname') and shown == (d.get('manufacturer') or '').strip():
        return True
    return re.sub(r'[^0-9a-f]', '', shown.lower()) == re.sub(r'[^0-9a-f]', '', d['mac'].lower())


def clients(docs, include_all=False):
    """One row per Wi-Fi client: by default only those connected now.

    Wired clients are left out: in bridge mode eero attributes every device it sees on the wired network
    (switches included) to the nearest unit, so its wired list is mostly devices that aren't on an eero."""
    rows = []
    for d in docs or []:
        if not isinstance(d, dict) or not d.get('mac') or not d.get('wireless') \
                or (not include_all and not d.get('connected')):
            continue
        conn = d.get('connectivity') or {}
        freq = (d.get('interface') or {}).get('frequency')
        channel = _channel(conn.get('frequency'))
        rows.append({
            'mac': d['mac'].lower(),
            'name': d.get('nickname') or d.get('display_name') or d.get('hostname') or d['mac'],
            'named': bool(d.get('nickname')),           # named in the eero app (else eero's guess)
            # no real name: eero shows the MAC vendor ("Shenzhen Phaten Tech. LTD") or the device calls itself
            # by its MAC ("0005CD000001")
            'vendor_name': not d.get('nickname') and _no_name(d),
            'unit': (d.get('source') or {}).get('location') or '',
            'band': (('%s GHz' % freq) if freq else '') + (' · ch %d' % channel if channel else ''),
            'signal': _dbm(conn.get('signal')),
            # eero's own 0-5 connection quality (the bars in the app). Not the link rate: that is the rate of
            # the last frame eero received, so an idle phone reads 6 Mbps; a snapshot of it is noise.
            'quality': conn.get('score_bars') if isinstance(conn.get('score_bars'), int) else None,
            'ip': d.get('ip') or '',
            'type': (d.get('device_type') or '').replace('_', ' '),
            'maker': d.get('manufacturer') or '',
            'connected': bool(d.get('connected')),
            'last_seen': d.get('last_active') or '',
            'private_mac': bool(d.get('is_private')),
        })
    return rows


def _yes(v):
    return None if v is None else ('Yes' if v else 'No')


def network(net, thread=None, speedtests=None):
    """The Network tab: [{'title': ..., 'rows': [[label, value], ...]}, ...]; values are plain text."""
    if not isinstance(net, dict):
        return []
    health = net.get('health') or {}
    internet = health.get('internet') or {}
    guest = net.get('guest_network') or {}
    updates = net.get('updates') or {}
    speed = net.get('speed') or {}
    thread = thread if isinstance(thread, dict) else {}

    def speed_text(v):
        return '%s %s' % (v.get('value'), v.get('units') or 'Mbps') if isinstance(v, dict) and v.get('value') is not None else None

    groups = [
        ('Network', [
            ('Name', net.get('name')),
            ('Status', net.get('status')),
            ('Internet', internet.get('status')),
            ('Mode', 'Bridge (the router does DHCP and routing)' if net.get('gateway') == 'bridged'
             or (net.get('connection') or {}).get('mode') == 'bridged' else (net.get('connection') or {}).get('mode')),
            ('DHCP', (net.get('dhcp') or {}).get('mode')),
            ('DNS', (net.get('dns') or {}).get('mode')),
            ('DNS caching', _yes((net.get('dns') or {}).get('caching'))),
            ('Public IP (as eero sees it)', (net.get('ip_settings') or {}).get('public_ip')),
            ('Double NAT', _yes((net.get('ip_settings') or {}).get('double_nat'))),
            ('UPnP', _yes(net.get('upnp'))),
        ]),
        ('Wi-Fi', [
            ('Band steering', _yes(net.get('band_steering'))),
            ('WPA3', _yes(net.get('wpa3'))),
            ('Wireless mode', net.get('wireless_mode')),
            ('Multi-link (MLO)', net.get('mlo_mode')),
            ('Guest network', ('%s (on)' % (guest.get('name') or 'unnamed') if guest.get('enabled') else 'Off') if guest else None),
            ('Thread', ('%s, channel %s' % (thread.get('name'), thread.get('channel')) if thread.get('enabled')
                        else 'Off') if thread else _yes(net.get('thread'))),
            ('HomeKit', _yes((net.get('homekit') or {}).get('enabled'))),
        ]),
        ('Units and clients', [
            ('Units online', net.get('online_eeros_count')),
            ('Units offline', net.get('offline_eeros_count')),
            ('Clients', (net.get('clients') or {}).get('count')),
        ]),
        ('Updates', [
            ('Firmware', updates.get('target_firmware')),
            ('Update available', _yes(updates.get('has_update'))),
            ('Preferred update hour', ('%02d:00' % updates['preferred_update_hour'])
             if isinstance(updates.get('preferred_update_hour'), int) else None),
            ('Last update started', updates.get('last_update_started')),
            ('Automatic updates', net.get('auto_setup_mode')),
        ]),
        ('Speed test (eero)', [
            ('Last test', speed.get('date')),
            ('Download', speed_text(speed.get('down'))),
            ('Upload', speed_text(speed.get('up'))),
        ] + [('%s' % t.get('date'), '%s down / %s up Mbps' % (t.get('down_mbps'), t.get('up_mbps')))
             for t in (speedtests or [])[1:6] if isinstance(t, dict)]),
    ]
    out = []
    for title, rows in groups:
        rows = [[label, str(value)] for label, value in rows if value not in (None, '')]
        if rows:
            out.append({'title': title, 'rows': rows})
    return out


MAC = re.compile(r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$')
MAX_HOURS = 24 * 30                             # history is kept for 30 days


def hours_arg(text):
    try:
        hours = float(text)
    except (TypeError, ValueError):
        hours = 24
    return min(max(hours, 1), MAX_HOURS)


def time_on_units(events, start, now, location):
    """Seconds on each unit between start and now. `events` ascending (dicts as Store.client_events gives),
    `location` where the client was at `start` (None: not connected). Returns [(unit or None, seconds)]."""
    spent = {}
    t, here = start, location
    for e in events:
        if e['ts'] < start:
            continue
        spent[here] = spent.get(here, 0) + max(0, e['ts'] - t)
        here = None if e['event'] == 'disconnected' else e['to_unit']
        t = e['ts']
    spent[here] = spent.get(here, 0) + max(0, now - t)
    return sorted(((u, int(sec)) for u, sec in spent.items() if sec > 0), key=lambda x: -x[1])


def where_at(events, start, current):
    """Where the client was at `start`: the last move before it, else what the first move after it left from,
    else (no moves at all) where it is now."""
    before = [e for e in events if e['ts'] < start]
    if before:
        e = before[-1]
        return None if e['event'] == 'disconnected' else e['to_unit']
    after = [e for e in events if e['ts'] >= start]
    if after:
        e = after[0]
        return None if e['event'] == 'connected' else e['from_unit']
    return current


def client(mac, hours, db_path=cache.PATH, now=None):
    mac = (mac or '').strip().lower()
    if not MAC.match(mac):
        return {'error': 'invalid MAC address'}
    now = int(now if now is not None else time.time())
    try:
        with cache.Store(db_path, readonly=True) as s:
            docs = s.get('clients')[1]
            since = s.state().get('history_since')
            events = list(reversed(s.client_events(now - MAX_HOURS * 3600, mac=mac, limit=100000)))
    except Exception:
        docs, since, events = None, None, []
    row = next((r for r in clients(docs, include_all=True) if r['mac'] == mac), None)
    start = now - int(hours * 3600)
    if since:
        start = max(start, int(since))
    current = row['unit'] if row and row['connected'] else None
    spent = time_on_units(events, start, now, where_at(events, start, current)) if since else []
    total = sum(sec for _, sec in spent) or 1
    return {
        'client': row,
        'hours': hours,
        'since': start if since else None,
        'history_since': since,
        'time': [{'unit': u, 'seconds': sec, 'share': round(100 * sec / total, 1)} for u, sec in spent],
        'events': list(reversed([e for e in events if e['ts'] >= start]))[:500],
    }


def moves(hours, db_path=cache.PATH, now=None, limit=2000):
    """Roams and band changes across all clients, newest first."""
    now = int(now if now is not None else time.time())
    try:
        with cache.Store(db_path, readonly=True) as s:
            events = s.client_events(now - int(hours * 3600), limit=limit * 4)
    except Exception:
        return []
    return [e for e in events if e['event'] in ('roamed', 'band')][:limit]


def main(argv):
    what = argv[1] if len(argv) > 1 else 'status'
    if what == 'status':
        result = status()
    elif what == 'units':
        result = units(_cached('units'))
    elif what == 'clients':
        result = clients(_cached('clients'), include_all=len(argv) > 2 and argv[2] == 'all')
    elif what == 'network':
        result = network(_cached('network'), _cached('thread'), _cached('speedtest'))
    elif what == 'client':
        result = client(argv[2] if len(argv) > 2 else '', hours_arg(argv[3] if len(argv) > 3 else 24))
    elif what == 'moves':
        result = moves(hours_arg(argv[2] if len(argv) > 2 else 24))
    else:
        result = {'error': 'unknown query'}
    print(json.dumps(result))


if __name__ == '__main__':
    main(sys.argv)
