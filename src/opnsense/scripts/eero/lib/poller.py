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

"""What eerod does each second: decide what is due, ask eero (gently), keep the answers and the history.

Everything is driven by step(now), so tests can run it with a made-up clock and a fake client.
"""
import random
import time

from . import client as api
from .history import client_events, unit_events

# seconds between fetches of each kind, in the order they are fetched (see docs/API.md)
SCHEDULE = (('networks', 3600), ('units', 60), ('clients', 60), ('network', 300), ('speedtest', 3600),
            ('thread', 3600))
MAX_PER_MINUTE = 12          # all requests together
BACKOFF_MIN = 30
BACKOFF_MAX = 1800
SKIP_UNAVAILABLE = 86400     # a kind eero refuses (403/404) is not asked for again for a day
EVENT_GAP = 600              # no events across a gap longer than this (the daemon was stopped)
PRUNE_EVERY = 3600
KEEP_DAYS = 30


class Poller:
    def __init__(self, store, sessions, make_client, rand=random.random):
        self.store = store
        self.sessions = sessions
        self.make_client = make_client      # token -> api.Client
        self.rand = rand
        self.client = None
        self.token = None
        self.net = None
        self.last = {}                      # kind -> time of the last attempt that got an answer
        self.skip_until = {}
        self.sent = []                      # times of recent requests
        self.failures = 0
        self.backoff_until = 0
        self.pruned = 0
        self._said = None
        self._history_since = None

    # --- status

    def _status(self, status, message=None, **extra):
        values = dict(status=status, message=message, **extra)
        if values != self._said:                    # signed out, it would otherwise write every second
            self.store.set_state(**values)
            self._said = values

    # --- session

    def _session(self, now):
        """The current client, or None when signed out (then the status says so)."""
        token = self.sessions.load()
        if token != self.token:
            self.token, self.net, self.last, self.skip_until = token, None, {}, {}
            self.failures, self.backoff_until = 0, 0
            self.client = self.make_client(token) if token else None
            if token:
                self._status('starting')
        if not token:
            self._status('needs_login', 'Not signed in to eero')
        return self.client

    def _signed_out(self, e):
        self.sessions.clear()
        self.store.forget()
        self.token, self.client, self.net = None, None, None
        self._status('needs_login', 'eero ended the session (%s); sign in again' % e.code)

    # --- pacing

    def _room(self, now):
        self.sent = [t for t in self.sent if now - t < 60]
        return len(self.sent) < MAX_PER_MINUTE

    def _back_off(self, now, retry_after=None):
        self.failures += 1
        delay = min(BACKOFF_MAX, BACKOFF_MIN * 2 ** (self.failures - 1))
        delay = delay * (0.8 + 0.4 * self.rand())           # jitter, so restarts don't line up
        if retry_after:
            delay = max(delay, retry_after)
        self.backoff_until = now + delay
        return int(self.backoff_until)

    # --- one fetch

    def _fetch(self, kind):
        c = self.client
        if kind == 'networks':
            nets = c.networks()
            return [{'url': n['url'], 'name': n.get('name')} for n in nets]
        if kind == 'network':
            return c.network(self.net['url'])
        return {'units': c.units, 'clients': c.clients, 'speedtest': c.speedtests,
                'thread': c.thread}[kind](self.net['url'])

    def _keep(self, kind, doc, now):
        if kind in ('units', 'clients'):
            prev_at, prev = self.store.get(kind)
            if prev is not None and prev_at is not None and now - prev_at <= EVENT_GAP:
                if kind == 'clients':
                    self._mark_history_start(prev_at)
                    self.store.add_client_events(client_events(prev, doc, int(now)))
                else:
                    self.store.add_unit_events(unit_events(prev, doc, int(now)))
        self.store.put(kind, doc, now)
        if kind == 'networks':
            if not doc:
                self.net = None
                self._status('error', 'This eero account has no network')
                return
            self.net = doc[0]                                    # one network per account for now
            self.store.set_state(network=self.net)

    def _mark_history_start(self, prev_at):
        """Remember when client history began (the first snapshot compared), once: the client page doesn't
        count time before it."""
        if self._history_since is None:
            self._history_since = self.store.state().get('history_since')
            if self._history_since is None:
                first = self.store.earliest_client_event()
                self._history_since = int(min(prev_at, first - 60) if first is not None else prev_at)
                self.store.set_state(history_since=self._history_since)

    def _due(self, now):
        for kind, every in SCHEDULE:
            if kind != 'networks' and self.net is None:
                continue
            if now < self.skip_until.get(kind, 0):
                continue
            if kind not in self.last or now - self.last[kind] >= every:
                return kind
        return None

    def step(self, now=None):
        """Do at most one request. Returns what happened (for tests and the log)."""
        now = time.time() if now is None else now
        if now - self.pruned >= PRUNE_EVERY:
            self.store.prune(now, KEEP_DAYS)
            self.pruned = now
        if self._session(now) is None:
            return 'signed out'
        if now < self.backoff_until:
            return 'backing off'
        kind = self._due(now)
        if kind is None:
            return 'idle'
        if not self._room(now):
            return 'pacing'
        self.sent.append(now)
        try:
            doc = self._fetch(kind)
        except api.SessionInvalid as e:
            self._signed_out(e)
            return 'signed out by eero'
        except api.RateLimited as e:
            until = self._back_off(now, e.retry_after)
            self._status('rate_limited', 'eero asked us to slow down', next_try=until)
            return 'rate limited'
        except api.NotAvailable:
            self.skip_until[kind] = now + SKIP_UNAVAILABLE
            self.last[kind] = now
            return '%s not available' % kind
        except (api.TransportError, api.LoginFailed) as e:
            until = self._back_off(now)
            self._status('error', 'Cannot reach eero (%s)' % e.code, next_try=until)
            return 'error'
        self.last[kind] = now
        self.failures = 0
        self._keep(kind, doc, now)
        if self.net is not None:
            self._status('ok', None, last_ok=int(now), next_try=None)
        return 'fetched %s' % kind
