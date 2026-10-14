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

import os
import stat
import tempfile
import unittest

import helpers  # noqa: F401
from lib.session import PENDING_TTL, SessionStore


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self._tmp.name, "eero")      # created on first write
        self.store = SessionStore(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty(self):
        self.assertIsNone(self.store.load())
        self.assertEqual(self.store.info(), {"signed_in": False})

    def test_save_load_private(self):
        self.store.save("tok-1", now=1000)
        self.assertEqual(self.store.load(), "tok-1")
        self.assertEqual(self.store.info(), {"signed_in": True, "since": 1000})
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.dir, "session")).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        self.assertEqual(sorted(os.listdir(self.dir)), ["session"])          # no temporary files left

    def test_info_never_has_token(self):
        self.store.save("tok-1")
        self.assertNotIn("tok-1", repr(self.store.info()))

    def test_overwrite_and_clear(self):
        self.store.save("tok-1")
        self.store.save("tok-2")
        self.assertEqual(self.store.load(), "tok-2")
        self.store.clear()
        self.assertIsNone(self.store.load())
        self.store.clear()                                                   # clearing twice is fine

    def test_pending_expires(self):
        self.store.save_pending("pending-1", now=1000)
        self.assertEqual(self.store.load_pending(now=1000 + PENDING_TTL), "pending-1")
        self.assertIsNone(self.store.load_pending(now=1001 + PENDING_TTL))

    def test_save_drops_pending(self):
        self.store.save_pending("pending-1")
        self.store.save("pending-1")
        self.assertIsNone(self.store.load_pending())

    def test_garbage_is_no_session(self):
        os.makedirs(self.dir)
        for content in ("", "not json", "[]", '{"token": ""}', '{"token": 5}'):
            with open(os.path.join(self.dir, "session"), "w") as f:
                f.write(content)
            self.assertIsNone(self.store.load(), content)


if __name__ == "__main__":
    unittest.main()
