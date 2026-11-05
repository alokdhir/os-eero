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

"""Dropping root. configd and rc.d start the scripts as root; everything they do, they do as this user, including the
session token and the database. The rc script and the installers create the user (setup_user.sh)."""
import os
import pwd

USER = 'eero'


def user():
    """The user's passwd entry, or None when it doesn't exist."""
    try:
        return pwd.getpwnam(USER)
    except KeyError:
        return None


def drop(data_dir):
    """Become the user for good. Returns None when done, or why not: without the user, or with a data directory it
    doesn't own (it couldn't read the session), keep working as before."""
    if os.getuid() != 0:
        return 'not running as root'
    pw = user()
    if pw is None:
        return 'no user %s' % USER
    try:
        if os.stat(data_dir).st_uid != pw.pw_uid:
            return "%s doesn't belong to %s" % (data_dir, USER)
    except OSError as e:
        return '%s: %s' % (data_dir, e.strerror)
    os.setgroups([])
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    os.environ['HOME'] = '/nonexistent'
    return None
