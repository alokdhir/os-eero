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

"""eero status poller. Started by rc.d/eero under daemon(8).

The only thing in the plugin that talks to eero: it polls on a fixed, gentle schedule (lib/poller.py), keeps
the answers and the roaming history in /var/db/eero/eero.db, and the GUI reads that.
"""

import os
import signal
import sys
import syslog
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import client as api                  # noqa: E402
from lib.poller import Poller                  # noqa: E402
from lib.session import SessionStore           # noqa: E402
from lib.store import Store                    # noqa: E402


CONDITIONS = {'signed out': 'signed out', 'signed out by eero': 'signed out', 'rate limited': 'rate limited',
              'error': 'error'}


def main():
    syslog.openlog('eero', facility=syslog.LOG_DAEMON)
    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    transport = api.RequestsTransport()
    store = Store()
    store.set_state(status='starting', message=None)    # not the last run's "stopped" until the first step
    poller = Poller(store, SessionStore(), lambda token: api.Client(transport, token))
    syslog.syslog(syslog.LOG_NOTICE, 'started')
    condition = None                            # log changes of condition, not every fetch
    try:
        while running:
            try:
                what = poller.step()
            except Exception as e:                  # keep running; daemon(8) would restart us anyway
                syslog.syslog(syslog.LOG_ERR, 'internal error: %s: %s' % (type(e).__name__, e))
                what = 'error'
                time.sleep(30)
            now = CONDITIONS.get(what, 'ok' if what.startswith('fetched') else condition)
            if now != condition:
                message = store.state().get('message')
                syslog.syslog(syslog.LOG_NOTICE if now == 'ok' else syslog.LOG_WARNING,
                              'polling eero' if now == 'ok' else '%s: %s' % (now, message))
                condition = now
            time.sleep(5 if what == 'signed out' else 1)
    finally:
        store.set_state(status='stopped', message=None)
        store.close()
        transport.close()
        syslog.syslog(syslog.LOG_NOTICE, 'stopped')


if __name__ == '__main__':
    main()
