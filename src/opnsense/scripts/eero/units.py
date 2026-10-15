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

"""Change eero units, through configd. The only changes the plugin makes to eero:

  units.py rename <unit id> <name> [user]   set the unit's location (the name the eero app shows)
  units.py reboot <unit id>|all [user]      reboot one unit, or every unit in the network

Always prints one JSON object ({"result": "ok"} or {"result": "failed", "message": ...}) and exits 0 with
nothing on stderr, like login.py. One call to eero per request, with the session eerod uses. Each request is
logged to syslog with the GUI user who made it (passed by the controller). After a rename the cached unit list
gets the new name at once, so the page shows it before eerod's next poll.
"""

import json
import os
import re
import sys
import syslog
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import client as api                  # noqa: E402
from lib.history import readable               # noqa: E402
from lib.session import SessionStore           # noqa: E402
from lib.store import Store                    # noqa: E402

UNIT_ID = re.compile(r'^[0-9A-Za-z_-]{1,40}$')
MAX_NAME = 40


def failed(message):
    return {'result': 'failed', 'message': message}


def explain(e, refused):
    if isinstance(e, api.SessionInvalid):
        return 'Not signed in to eero. Sign in on the Settings tab and try again.'
    if isinstance(e, api.RateLimited):
        return 'eero is limiting requests. Wait a few minutes and try again.'
    if isinstance(e, api.TransportError):
        return 'Could not reach eero. Check the router\'s internet connection and try again.'
    if isinstance(e, api.NotAvailable):
        return 'eero does not know this unit (any more).'
    return '%s (%s).' % (refused, e.code)


def syslog_line(text):
    syslog.openlog('eero', facility=syslog.LOG_DAEMON)
    syslog.syslog(syslog.LOG_NOTICE, text)


def _unit(units, uid):
    return next((u for u in units or [] if isinstance(u, dict)
                 and (u.get('url') or '').rstrip('/').rsplit('/', 1)[-1] == uid), None)


def _signed_in(client, sessions):
    token = sessions.load()
    if not token:
        return False
    client.token = token
    return True


def rename(client, sessions, store, uid, name, user='', log=syslog_line):
    name = ' '.join((name or '').split())
    if not UNIT_ID.match(uid or ''):
        return failed('Unknown unit.')
    if not name or len(name) > MAX_NAME or not readable(name):
        return failed('Enter a name of 1 to %d characters.' % MAX_NAME)
    fetched, units = store.get('units')
    unit = _unit(units, uid)
    if unit is None:
        return failed('eero does not know this unit.')
    if not _signed_in(client, sessions):
        return failed(explain(api.SessionInvalid('no session'), ''))
    old = unit.get('location')
    try:
        client.set_location(unit['url'], name)
    except api.EeroError as e:
        log('rename of unit "%s" to "%s" by %s failed: %s' % (old, name, user or '?', e.code))
        return failed(explain(e, 'eero refused the new name'))
    log('unit "%s" renamed to "%s" by %s' % (old, name, user or '?'))
    # the new name in the cache now (eerod's next poll replaces the whole list anyway), also where other
    # units name it as the one they hang off (wireless_upstream_node.name is the upstream's location)
    unit['location'] = name
    for u in units:
        up = u.get('wireless_upstream_node') if isinstance(u, dict) else None
        if isinstance(up, dict) and old and up.get('name') == old:
            up['name'] = name
    store.put('units', units, fetched or int(time.time()))
    return {'result': 'ok', 'name': name}


def reboot(client, sessions, store, target, user='', log=syslog_line):
    """Reboot one unit (target = its id) or the whole network (target = 'all')."""
    if target == 'all':
        net = store.state().get('network') or {}
        if not net.get('url'):
            return failed('No eero network yet. Sign in on the Settings tab first.')
        path, what = net['url'].rstrip('/') + '/reboot', 'every unit in "%s"' % (net.get('name') or 'the network')
    else:
        if not UNIT_ID.match(target or ''):
            return failed('Unknown unit.')
        unit = _unit(store.get('units')[1], target)
        if unit is None:
            return failed('eero does not know this unit.')
        path = (unit.get('resources') or {}).get('reboot') or unit['url'].rstrip('/') + '/reboot'
        what = 'unit "%s"' % unit.get('location')
    if not _signed_in(client, sessions):
        return failed(explain(api.SessionInvalid('no session'), ''))
    try:
        client.reboot(path)
    except api.EeroError as e:
        log('reboot of %s by %s failed: %s' % (what, user or '?', e.code))
        return failed(explain(e, 'eero refused the reboot'))
    log('reboot of %s requested by %s' % (what, user or '?'))
    return {'result': 'ok'}


def main(argv):
    what = argv[1] if len(argv) > 1 else ''
    args = argv[2:] + ['', '', '']
    transport = None
    try:
        transport = api.RequestsTransport()
        client = api.Client(transport)
        if what == 'rename':
            with Store() as store:
                result = rename(client, SessionStore(), store, args[0], args[1], args[2])
        elif what == 'reboot':
            with Store() as store:
                result = reboot(client, SessionStore(), store, args[0], args[1])
        else:
            result = failed('unknown action')
    except Exception as e:                          # never a traceback: configd would log it
        result = failed('Internal error (%s).' % type(e).__name__)
    finally:
        if transport is not None:
            transport.close()
    print(json.dumps(result))


if __name__ == '__main__':
    sys.stderr = open(os.devnull, 'w')              # warnings too would reach configd's log
    main(sys.argv)
