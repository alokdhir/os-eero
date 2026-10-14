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

"""Sign in to eero from the GUI, through configd:

  login.py signin <email or phone>   eero sends a code; the pending token is kept for 15 minutes
  login.py verify <code>             the code turns the pending token into the session eerod uses
  login.py signout                   end the session at eero and forget it here

Always prints one JSON object ({"result": "ok"} or {"result": "failed", "message": ...}) and exits 0 with
nothing on stderr: configd logs a failing command line (which holds the email address) and any stderr.
The email address or phone number is used for the one request and not kept.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import client as api                  # noqa: E402
from lib.session import SessionStore           # noqa: E402
from lib.store import Store                    # noqa: E402

MESSAGES = {
    'error.verification.invalid': 'That code is not right. Check it and try again.',
    'error.verification.expired': 'That code has expired. Start again to get a new one.',
    'error.verification.failure': 'eero could not check that code. Start again to get a new one.',
    'error.verification.blocked': 'Too many attempts. Wait a while, then start again.',
    'error.too.many.resends': 'Too many codes requested. Wait a while, then start again.',
    'error.login.blocked': 'eero has blocked sign-in for this account for now. Try again later.',
    'error.login.unknown': 'eero has no account with that email address or phone number.',
    'error.form.email.malformed': 'Enter a valid email address.',
    'error.form.phone.malformed': 'Enter a phone number with its country code, e.g. +1 555 555 0100.',
}


def failed(message):
    return {'result': 'failed', 'message': message}


def explain(e):
    if isinstance(e, api.RateLimited):
        return 'eero is limiting requests. Wait a few minutes and try again.'
    if isinstance(e, api.TransportError):
        return 'Could not reach eero. Check the router\'s internet connection and try again.'
    return MESSAGES.get(e.code, 'eero refused the sign-in (%s).' % e.code)


def identifier(text):
    """An email address as typed, or a phone number reduced to + and digits; None if neither."""
    text = text.strip()
    if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', text):
        return text
    phone = re.sub(r'[\s().-]', '', text)
    if re.fullmatch(r'\+?[0-9]{7,15}', phone):
        return phone
    return None


def signin(client, sessions, text):
    who = identifier(text)
    if who is None:
        return failed('Enter the email address or phone number of your eero account.')
    try:
        pending = client.login(who)
    except api.EeroError as e:
        return failed(explain(e))
    sessions.save_pending(pending)
    return {'result': 'ok'}


def verify(client, sessions, text):
    code = re.sub(r'\s', '', text)
    if not re.fullmatch(r'[0-9]{4,8}', code):
        return failed('Enter the code from eero\'s email or text message.')
    pending = sessions.load_pending()
    if pending is None:
        return failed('The sign-in has expired. Start again to get a new code.')
    try:
        token = client.verify(pending, code)
    except api.EeroError as e:
        return failed(explain(e))
    sessions.save(token)
    return {'result': 'ok'}


def signout(client, sessions, store):
    token = sessions.load()
    if token:
        client.token = token
        try:
            client.logout()
        except api.EeroError:
            pass                                    # forget it here even if eero can't be told
    sessions.clear()
    if store is not None:
        store.forget()
    return {'result': 'ok'}


def main(argv):
    what = argv[1] if len(argv) > 1 else ''
    arg = argv[2] if len(argv) > 2 else ''
    sessions = SessionStore()
    transport = None
    try:
        transport = api.RequestsTransport()
        client = api.Client(transport)
        if what == 'signin':
            result = signin(client, sessions, arg)
        elif what == 'verify':
            result = verify(client, sessions, arg)
        elif what == 'signout':
            with Store() as store:
                result = signout(client, sessions, store)
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
