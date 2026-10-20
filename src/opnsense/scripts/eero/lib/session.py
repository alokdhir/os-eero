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

"""The eero session, kept on disk where only root can read it (never in config.xml).

/var/db/eero/session    the session token, once a login is verified
/var/db/eero/pending    the token between "send me a code" and "here is the code"; ignored after PENDING_TTL

Files are written whole (a temporary file in the same directory, created 0600, then renamed), so a reader
never sees half a token.
"""
import json
import os
import time

DIR = '/var/db/eero'
PENDING_TTL = 15 * 60


class SessionStore:
    def __init__(self, directory=DIR):
        self.dir = directory

    def _path(self, name):
        return os.path.join(self.dir, name)

    def _write(self, name, doc):
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        tmp = self._path('.%s.%d' % (name, os.getpid()))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(doc, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path(name))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _read(self, name):
        try:
            with open(self._path(name)) as f:
                doc = json.load(f)
        except (OSError, ValueError):
            return None
        return doc if isinstance(doc, dict) and isinstance(doc.get('token'), str) and doc['token'] else None

    def _remove(self, name):
        try:
            os.unlink(self._path(name))
        except FileNotFoundError:
            pass

    # --- the session

    def load(self):
        """The session token, or None."""
        doc = self._read('session')
        return doc['token'] if doc else None

    def info(self):
        """What the GUI may show about the session (never the token)."""
        doc = self._read('session')
        return {'signed_in': True, 'since': doc.get('since')} if doc else {'signed_in': False}

    def save(self, token, now=None):
        self._write('session', {'token': token, 'since': int(now if now is not None else time.time())})
        self._remove('pending')

    def clear(self):
        self._remove('session')
        self._remove('pending')

    # --- a login in progress

    def save_pending(self, token, now=None):
        self._write('pending', {'token': token, 'since': int(now if now is not None else time.time())})

    def load_pending(self, now=None):
        doc = self._read('pending')
        now = now if now is not None else time.time()
        if not doc or not isinstance(doc.get('since'), int) or now - doc['since'] > PENDING_TTL:
            return None
        return doc['token']
