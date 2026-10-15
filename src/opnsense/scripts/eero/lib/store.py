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

"""SQLite cache of what eerod fetched, the daemon's status, and the event history.

snapshots      the latest document per kind (networks, network, units, clients, speedtest, thread), already
               stripped of credentials by the client
state          key -> JSON value: status, message, network, next_try, ...
client_events  clients connecting, leaving, roaming between units, changing band
unit_events    units going offline and coming back
"""
import json
import os
import sqlite3

PATH = '/var/db/eero/eero.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (kind TEXT PRIMARY KEY, fetched_at INTEGER NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS client_events (
    ts INTEGER NOT NULL, mac TEXT NOT NULL, name TEXT, event TEXT NOT NULL,
    from_unit TEXT, to_unit TEXT, band_from TEXT, band_to TEXT, from_id TEXT, to_id TEXT);
CREATE INDEX IF NOT EXISTS client_events_ts ON client_events (ts);
CREATE INDEX IF NOT EXISTS client_events_mac ON client_events (mac, ts);
CREATE TABLE IF NOT EXISTS unit_events (ts INTEGER NOT NULL, unit TEXT NOT NULL, location TEXT, event TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS unit_events_ts ON unit_events (ts);
"""


class Store:
    def __init__(self, path=PATH, readonly=False):
        if readonly:
            self.db = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=5)
        else:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            self.db = sqlite3.connect(path, timeout=5)
            os.chmod(path, 0o600)
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.executescript(SCHEMA)
            self._add_unit_ids()

    def _add_unit_ids(self):
        """Tables from before moves kept unit ids get the two columns; their rows keep only the unit names."""
        cols = {r[1] for r in self.db.execute('PRAGMA table_info(client_events)')}
        if 'from_id' not in cols:
            with self.db:
                self.db.execute('ALTER TABLE client_events ADD COLUMN from_id TEXT')
                self.db.execute('ALTER TABLE client_events ADD COLUMN to_id TEXT')

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- snapshots

    def put(self, kind, doc, now):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?)', (kind, int(now), json.dumps(doc)))

    def get(self, kind):
        """(fetched_at, doc), or (None, None) if never fetched."""
        row = self.db.execute('SELECT fetched_at, doc FROM snapshots WHERE kind = ?', (kind,)).fetchone()
        return (row[0], json.loads(row[1])) if row else (None, None)

    def fetched(self):
        return dict(self.db.execute('SELECT kind, fetched_at FROM snapshots'))

    def forget(self):
        """Drop everything fetched (after signing out): the next session may be another account."""
        with self.db:
            self.db.execute('DELETE FROM snapshots')

    def forget_history(self):
        """Drop the recorded history and where it began (a different eero network: none of it applies)."""
        with self.db:
            self.db.execute('DELETE FROM client_events')
            self.db.execute('DELETE FROM unit_events')
            self.db.execute("DELETE FROM state WHERE key IN ('history_since', 'network')")

    # --- daemon status

    def set_state(self, **values):
        with self.db:
            self.db.executemany('INSERT OR REPLACE INTO state VALUES (?, ?)',
                                [(k, json.dumps(v)) for k, v in values.items()])

    def state(self):
        return {k: json.loads(v) for k, v in self.db.execute('SELECT key, value FROM state')}

    # --- history

    def add_client_events(self, rows):
        """Rows as history.client_events makes them (10 values; 8 without the unit ids)."""
        if rows:
            with self.db:
                self.db.executemany('INSERT INTO client_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                    [tuple(r) + (None,) * (10 - len(r)) for r in rows])

    def add_unit_events(self, rows):
        if rows:
            with self.db:
                self.db.executemany('INSERT INTO unit_events VALUES (?, ?, ?, ?)', rows)

    def client_events(self, since, mac=None, limit=1000, events=None):
        """Newest first. `events`: only these kinds (e.g. ('roamed', 'band')), chosen before the limit applies."""
        cols = ('ts', 'mac', 'name', 'event', 'from_unit', 'to_unit', 'band_from', 'band_to', 'from_id', 'to_id')
        sql = 'SELECT %s FROM client_events WHERE ts >= ?' % ', '.join(cols)
        args = [int(since)]
        if mac:
            sql += ' AND mac = ?'
            args.append(mac.lower())
        if events:
            sql += ' AND event IN (%s)' % ', '.join('?' * len(events))
            args.extend(events)
        sql += ' ORDER BY ts DESC, rowid DESC LIMIT ?'
        args.append(int(limit))
        return [dict(zip(cols, r)) for r in self.db.execute(sql, args)]

    def earliest_client_event(self):
        return self.db.execute('SELECT min(ts) FROM client_events').fetchone()[0]

    def unit_events(self, since, limit=1000):
        cols = ('ts', 'unit', 'location', 'event')
        return [dict(zip(cols, r)) for r in self.db.execute(
            'SELECT ts, unit, location, event FROM unit_events WHERE ts >= ? ORDER BY ts DESC, rowid DESC LIMIT ?',
            (int(since), int(limit)))]

    def prune(self, now, days):
        cut = int(now - days * 86400)
        with self.db:
            self.db.execute('DELETE FROM client_events WHERE ts < ?', (cut,))
            self.db.execute('DELETE FROM unit_events WHERE ts < ?', (cut,))
