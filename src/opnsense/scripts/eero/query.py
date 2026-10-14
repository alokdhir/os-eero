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

  status    the status line: signed in or not, polling or not, last update, network name
"""

import json
import os
import sys

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


def main(argv):
    what = argv[1] if len(argv) > 1 else 'status'
    if what == 'status':
        result = status()
    else:
        result = {'error': 'unknown query'}
    print(json.dumps(result))


if __name__ == '__main__':
    main(sys.argv)
