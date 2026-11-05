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

import unittest
from types import SimpleNamespace
from unittest import mock

import helpers  # noqa: F401
from lib import privs


class TestDrop(unittest.TestCase):
    def test_not_root_stays_as_is(self):
        with mock.patch.object(privs.os, 'getuid', return_value=1000):
            self.assertEqual(privs.drop('/tmp'), 'not running as root')

    def test_needs_the_user_and_its_directory(self):
        calls = []
        with mock.patch.object(privs.os, 'getuid', return_value=0), \
                mock.patch.object(privs.os, 'setuid', side_effect=lambda u: calls.append(('uid', u))), \
                mock.patch.object(privs.os, 'setgid', side_effect=lambda g: calls.append(('gid', g))), \
                mock.patch.object(privs.os, 'setgroups', side_effect=lambda g: calls.append(('groups', g))):
            with mock.patch.object(privs.pwd, 'getpwnam', side_effect=KeyError):
                self.assertEqual(privs.drop('/x'), 'no user eero')
            with mock.patch.object(privs.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1788, pw_gid=1788)):
                with mock.patch.object(privs.os, 'stat', return_value=SimpleNamespace(st_uid=0)):
                    self.assertIn("doesn't belong", privs.drop('/x'))
                self.assertEqual(calls, [])
                with mock.patch.object(privs.os, 'stat', return_value=SimpleNamespace(st_uid=1788)), \
                        mock.patch.dict(privs.os.environ):
                    self.assertIsNone(privs.drop('/x'))
        self.assertEqual(calls, [('groups', []), ('gid', 1788), ('uid', 1788)])     # the uid last: it ends the rest


if __name__ == '__main__':
    unittest.main()
