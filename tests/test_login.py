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
import tempfile
import unittest

import helpers  # noqa: F401
import login
from lib import client as api
from lib.session import SessionStore


class FakeClient:
    def __init__(self, fail=None):
        self.fail = fail
        self.token = None
        self.calls = []

    def login(self, who):
        self.calls.append(("login", who))
        if self.fail:
            raise self.fail
        return "pending-1"

    def verify(self, pending, code):
        self.calls.append(("verify", pending, code))
        if self.fail:
            raise self.fail
        self.token = pending
        return pending

    def logout(self):
        self.calls.append(("logout", self.token))
        if self.fail:
            raise self.fail
        self.token = None


class FakeStore:
    forgotten = False

    def forget(self):
        self.forgotten = True


class TestLogin(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions = SessionStore(os.path.join(self._tmp.name, "s"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_identifier(self):
        self.assertEqual(login.identifier(" user@example.com "), "user@example.com")
        self.assertEqual(login.identifier("+1 (555) 555-0100"), "+15555550100")
        self.assertIsNone(login.identifier("not an address"))
        self.assertIsNone(login.identifier("12"))
        self.assertIsNone(login.identifier("a@b@c.com"))

    def test_signin_then_verify(self):
        c = FakeClient()
        self.assertEqual(login.signin(c, self.sessions, "user@example.com"), {"result": "ok"})
        self.assertEqual(self.sessions.load_pending(), "pending-1")
        self.assertIsNone(self.sessions.load())
        self.assertEqual(login.verify(c, self.sessions, " 123 456 "), {"result": "ok"})
        self.assertEqual(c.calls[-1], ("verify", "pending-1", "123456"))
        self.assertEqual(self.sessions.load(), "pending-1")
        self.assertIsNone(self.sessions.load_pending())

    def test_bad_input_never_reaches_eero(self):
        c = FakeClient()
        self.assertEqual(login.signin(c, self.sessions, "nope")["result"], "failed")
        self.assertEqual(login.verify(c, self.sessions, "12ab")["result"], "failed")
        self.assertEqual(c.calls, [])

    def test_verify_without_signin(self):
        r = login.verify(FakeClient(), self.sessions, "123456")
        self.assertEqual(r["result"], "failed")
        self.assertIn("expired", r["message"])

    def test_wrong_code_keeps_pending(self):
        login.signin(FakeClient(), self.sessions, "user@example.com")
        r = login.verify(FakeClient(api.LoginFailed("error.verification.invalid", 401)), self.sessions, "000000")
        self.assertEqual(r, {"result": "failed", "message": login.MESSAGES["error.verification.invalid"]})
        self.assertEqual(self.sessions.load_pending(), "pending-1")        # can try the right code
        self.assertIsNone(self.sessions.load())

    def test_messages(self):
        self.assertIn("limiting", login.explain(api.RateLimited("error.rate.limit", 429)))
        self.assertIn("reach eero", login.explain(api.TransportError("network: ConnectTimeout")))
        self.assertIn("error.something.new", login.explain(api.LoginFailed("error.something.new", 400)))

    def test_signout_forgets_even_if_eero_says_no(self):
        self.sessions.save("tok")
        store = FakeStore()
        c = FakeClient(api.SessionInvalid("error.session.invalid", 401))
        self.assertEqual(login.signout(c, self.sessions, store), {"result": "ok"})
        self.assertEqual(c.calls, [("logout", "tok")])
        self.assertIsNone(self.sessions.load())
        self.assertTrue(store.forgotten)

    def test_signout_when_not_signed_in(self):
        c = FakeClient()
        self.assertEqual(login.signout(c, self.sessions, None), {"result": "ok"})
        self.assertEqual(c.calls, [])


if __name__ == "__main__":
    unittest.main()
