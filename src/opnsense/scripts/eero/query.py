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
  network         the Overview tab: the network's settings and health, grouped
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
from lib import config                         # noqa: E402
from lib.history import client_name, readable  # noqa: E402
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
    if mhz == 5935:                             # 6 GHz channel 2 sits below channel 1 (5955)
        return 2
    if 5955 <= mhz <= 7125:
        return (mhz - 5950) // 5
    return None


# names Apple devices give with a private Wi-Fi address instead of their own (as in os-loupe)
PLACEHOLDERS = {'mac', 'iphone', 'ipad', 'watch', 'apple-watch', 'ipod', 'localhost'}


def _no_name(d):
    shown = (readable(d.get('display_name')) or '').strip()
    if not shown or shown.lower() in PLACEHOLDERS:
        return True
    if not readable(d.get('hostname')) and shown == (d.get('manufacturer') or '').strip():
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
            'name': client_name(d),
            'named': bool(d.get('nickname')),           # named in the eero app (else eero's guess)
            # no real name: eero shows the MAC vendor ("Shenzhen Phaten Tech. LTD") or the device calls itself
            # by its MAC ("0005CD000001")
            'vendor_name': not d.get('nickname') and _no_name(d),
            'unit': (d.get('source') or {}).get('location') or '',
            'unit_id': _unit_id((d.get('source') or {}).get('url')),
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


def network(net, thread=None, speedtests=None, units=None):
    """The Overview tab: [{'title': ..., 'rows': [[label, value], ...]}, ...]; values are plain text."""
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
            ('Primary unit', next((u.get('location') for u in units or [] if isinstance(u, dict)
                                   and u.get('is_primary_node')), None)),
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


def max_hours():
    """The history kept, in hours (the "Keep history" setting)."""
    return config.history_days() * 24


def hours_arg(text):
    try:
        hours = float(text)
    except (TypeError, ValueError):
        hours = 24
    return min(max(hours, 1), max_hours())


def _unit_names(udocs):
    """unit id -> its name now."""
    return {_unit_id(u.get('url')): u.get('location') for u in udocs or [] if isinstance(u, dict) and u.get('url')}


def _named(events, names):
    """Moves shown with each unit's current name, looked up by unit id (a unit since removed keeps the name
    recorded with the move)."""
    for e in events:
        for side in ('from', 'to'):
            if e.get(side + '_id') in names:
                e[side + '_unit'] = names[e[side + '_id']]
    return events


def _to(e):
    return e.get('to_id', e.get('to_unit'))


def _from(e):
    return e.get('from_id', e.get('from_unit'))


def time_on_units(events, start, now, location):
    """Seconds on each unit between start and now. `events` ascending (dicts as Store.client_events gives),
    `location` where the client was at `start` (None: not connected). Returns [(unit or None, seconds)]."""
    spent = {}
    t, here = start, location
    for e in events:
        if e['ts'] < start:
            continue
        spent[here] = spent.get(here, 0) + max(0, e['ts'] - t)
        here = None if e['event'] == 'disconnected' else _to(e)
        t = e['ts']
    spent[here] = spent.get(here, 0) + max(0, now - t)
    return sorted(((u, int(sec)) for u, sec in spent.items() if sec > 0), key=lambda x: -x[1])


def where_at(events, start, current):
    """Where the client was at `start`: the last move before it, else what the first move after it left from,
    else (no moves at all) where it is now."""
    before = [e for e in events if e['ts'] < start]
    if before:
        e = before[-1]
        return None if e['event'] == 'disconnected' else _to(e)
    after = [e for e in events if e['ts'] >= start]
    if after:
        e = after[0]
        return None if e['event'] == 'connected' else _from(e)
    return current


def client(mac, hours, db_path=cache.PATH, now=None):
    mac = (mac or '').strip().lower()
    if not MAC.match(mac):
        return {'error': 'invalid MAC address'}
    now = int(now if now is not None else time.time())
    try:
        with cache.Store(db_path, readonly=True) as s:
            docs, udocs = s.get('clients')[1], s.get('units')[1]
            since = s.state().get('history_since')
            events = list(reversed(s.client_events(now - max_hours() * 3600, mac=mac, limit=100000)))
    except Exception:
        docs, udocs, since, events = None, None, None, []
    names = _unit_names(udocs)
    _named(events, names)
    row = next((r for r in clients(docs, include_all=True) if r['mac'] == mac), None)
    start = now - int(hours * 3600)
    if since:
        start = max(start, int(since))
    current = row['unit_id'] or None if row and row['connected'] else None
    spent = time_on_units(events, start, now, where_at(events, start, current)) if since else []
    total = sum(sec for _, sec in spent) or 1
    # what to call each unit in "time on each unit": its name now, else (a unit since removed, or a row from
    # before ids were kept) the name recorded with the move
    labels = dict(names)
    for e in events:
        for side in ('from', 'to'):
            if e[side + '_id']:
                labels.setdefault(e[side + '_id'], e[side + '_unit'])
    if row and row['unit_id']:
        labels.setdefault(row['unit_id'], row['unit'])
    return {
        'client': row,
        'hours': hours,
        'since': start if since else None,
        'history_since': since,
        'time': [{'unit': labels.get(u, u) if u else None, 'seconds': sec, 'share': round(100 * sec / total, 1)}
                 for u, sec in spent],
        'events': list(reversed([e for e in events if e['ts'] >= start]))[:500],
    }


def moves(hours, db_path=cache.PATH, now=None, limit=2000):
    """Roams and band changes across all clients, newest first."""
    now = int(now if now is not None else time.time())
    try:
        with cache.Store(db_path, readonly=True) as s:
            events = s.client_events(now - int(hours * 3600), limit=limit, events=('roamed', 'band'))
            udocs = s.get('units')[1]
    except Exception:
        return []
    return _named(events, _unit_names(udocs))


BANDS = {'band_2_4GHz': '2.4 GHz', 'band_5GHz': '5 GHz', 'band_5GHz_full': '5 GHz', 'band_5GHz_low': '5 GHz (low)',
         'band_5GHz_high': '5 GHz (high)', 'band_6GHz': '6 GHz'}


def _speed(text):
    """eero's port speed ('P1000') as '1 Gbps'."""
    try:
        mbps = int(str(text or '').lstrip('P'))
    except ValueError:
        return ''
    return ('%g Gbps' % (mbps / 1000)) if mbps >= 1000 else ('%d Mbps' % mbps if mbps else '')


def _power(info):
    src = ((info or {}).get('power_source') or '').upper()
    return {'ETHERNET': 'PoE', 'POE': 'PoE', 'USB': 'Power adapter', 'ADAPTER': 'Power adapter'}.get(src, src.capitalize())


def _neighbour(n, by_ip):
    """What an LLDP neighbour is: an eero unit (matched by its address), else the name it gives, else the
    port it reports (a switch port)."""
    if not isinstance(n, dict):
        return None
    loc = by_ip.get(n.get('managementIpv4Address'))
    if loc:
        return loc + ' eero'
    name = readable(n.get('systemName'))
    if name and name != 'eero':
        return name
    port = readable(n.get('portId'))
    return ('port %s' % port) if port and n.get('portIdType') != 'MacAddress' else None


MOVES_HOURS = 24                                # a unit's client moves: the last day only (a busy unit has hundreds)


def unit(uid, db_path=cache.PATH, now=None, keep_hours=None):
    """One unit's page: its details, radios, ports, clients on it now, and its history: status changes over all
    the history kept, client moves over the last day."""
    uid = str(uid or '').strip()
    if not re.match(r'^[0-9A-Za-z_-]{1,40}$', uid):
        return {'error': 'invalid unit'}
    now = int(now if now is not None else time.time())
    keep_hours = keep_hours or max_hours()
    start = now - int(keep_hours * 3600)
    try:
        with cache.Store(db_path, readonly=True) as s:
            udocs, cdocs = s.get('units')[1], s.get('clients')[1]
            since = s.state().get('history_since')
            uevents = s.unit_events(start, limit=5000)
            cevents = s.client_events(now - MOVES_HOURS * 3600, limit=50000)
    except Exception:
        udocs, cdocs, since, uevents, cevents = None, None, None, [], []
    u = next((d for d in udocs or [] if isinstance(d, dict) and _unit_id(d.get('url')) == uid), None)
    if u is None:
        return {'error': 'eero does not know this unit'}
    row = next(r for r in units([u]))
    loc = row['name']
    reboot = u.get('last_reboot') or ''
    row.update({
        'serial': u.get('serial') or '',
        'mac': u.get('mac_address') or '',
        'power': _power(u.get('power_info')),
        'last_reboot': reboot,
        'update_available': bool(u.get('update_available')),
    })
    radios = []
    for key, r in sorted((u.get('radio_channel_stats') or {}).items(), key=lambda kv: list(BANDS).index(kv[0])
                         if kv[0] in BANDS else len(BANDS)):
        if isinstance(r, dict):
            radios.append({'band': BANDS.get(key, key), 'channel': r.get('channel'), 'width': r.get('channel_width'),
                           'clients': r.get('client_count'),
                           'tx_power': r.get('tx_power')})
    by_ip = {d.get('ip_address'): d.get('location') for d in udocs if isinstance(d, dict) and d.get('ip_address')}
    ports = []
    for p in (u.get('ethernet_status') or {}).get('statuses') or []:
        if not isinstance(p, dict):
            continue
        seen = [_neighbour(n, by_ip) for n in (p.get('lldpInfo') or [])]
        ports.append({'port': p.get('port_name') or str(p.get('interfaceNumber', '')), 'link': bool(p.get('hasCarrier')),
                      'speed': _speed(p.get('speed')) if p.get('hasCarrier') else '',
                      'uplink': bool(p.get('isWanPort') or p.get('isLeafWiredToUpstream')),
                      'neighbours': sorted({n for n in seen if n and n != loc + ' eero'})})
    url = u.get('url')
    return {
        'unit': row,
        'radios': radios,
        'ports': ports,
        'clients': [c for c in clients(cdocs) if c['unit_id'] == uid],
        'days': keep_hours // 24,
        'history_since': since,
        'events': [e for e in uevents if e['unit'] == url],
        'moves': [e for e in _named(cevents, _unit_names(udocs)) if uid in (e['from_id'], e['to_id'])][:500],
    }


def widget(db_path=cache.PATH, sessions=None, pidfile=PIDFILE):
    """The dashboard widget: the status line's facts, and each unit with its Wi-Fi clients."""
    st = status(db_path, sessions, pidfile)
    try:
        with cache.Store(db_path, readonly=True) as s:
            udocs, cdocs = s.get('units')[1], s.get('clients')[1]
    except Exception:
        udocs, cdocs = None, None
    rows = sorted(units(udocs), key=lambda r: (not r['primary'], r['name'].lower()))
    return {
        'running': st['running'], 'status': st['status'], 'message': st.get('message'), 'network': st.get('network'),
        'last_ok': st.get('last_ok'), 'next_try': st.get('next_try'),
        'units': [{k: r[k] for k in ('id', 'name', 'online', 'primary', 'clients')} for r in rows],
        'clients': len(clients(cdocs)),
    }


def main(argv):
    what = argv[1] if len(argv) > 1 else 'status'
    if what == 'status':
        result = status()
    elif what == 'units':
        result = units(_cached('units'))
    elif what == 'clients':
        result = clients(_cached('clients'), include_all=len(argv) > 2 and argv[2] == 'all')
    elif what == 'network':
        result = network(_cached('network'), _cached('thread'), _cached('speedtest'), _cached('units'))
    elif what == 'client':
        result = client(argv[2] if len(argv) > 2 else '', hours_arg(argv[3] if len(argv) > 3 else 24))
    elif what == 'moves':
        result = moves(hours_arg(argv[2] if len(argv) > 2 else 24))
    elif what == 'widget':
        result = widget()
    elif what == 'unit':
        result = unit(argv[2] if len(argv) > 2 else '')
    else:
        result = {'error': 'unknown query'}
    print(json.dumps(result))


if __name__ == '__main__':
    main(sys.argv)
