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

import json
import unittest

from helpers import fixture, fixture_doc
from lib import client
from lib.client import Client, Response

TOKEN = "tok-0123456789abcdef"
NET = "/2.2/networks/1000001"


class FakeTransport:
    """Answers from a script: {(method, path): [Response, ...]} (each call takes the next answer)."""

    def __init__(self, answers):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.calls = []

    def __call__(self, method, url, headers, json_body=None, form=None, timeout=None):
        assert url.startswith(client.API), url
        path = url[len(client.API):]
        self.calls.append({"method": method, "path": path, "headers": headers, "json": json_body, "form": form})
        answers = self.answers.get((method, path))
        if not answers:
            raise AssertionError("unexpected call %s %s" % (method, path))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def ok(name):
    return Response(200, {"Content-Type": "application/json"}, fixture(name))


def err(name, status, headers=None):
    return Response(status, headers or {}, fixture(name))


class TestReads(unittest.TestCase):
    def test_sends_cookie_and_agent(self):
        t = FakeTransport({("GET", "/2.2/account"): [ok("account")]})
        Client(t, TOKEN).account()
        h = t.calls[0]["headers"]
        self.assertEqual(h["Cookie"], "s=" + TOKEN)
        self.assertEqual(h["User-Agent"], client.USER_AGENT)

    def test_networks(self):
        t = FakeTransport({("GET", "/2.2/account"): [ok("account")]})
        self.assertEqual([n["url"] for n in Client(t, TOKEN).networks()], [NET])

    def test_units_and_clients(self):
        t = FakeTransport({("GET", NET + "/eeros"): [ok("eeros")], ("GET", NET + "/devices"): [ok("devices")]})
        c = Client(t, TOKEN)
        units = c.units(NET)
        self.assertEqual(len(units), 3)
        self.assertEqual(units[2]["wireless_upstream_node"]["name"], units[0]["location"])
        clients = c.clients(NET)
        self.assertEqual({d["source"]["url"] for d in clients} <= {u["url"] for u in units}, True)

    def test_full_urls_and_paths_both_work(self):
        t = FakeTransport({("GET", NET): [ok("network"), ok("network")]})
        c = Client(t, TOKEN)
        c.network(NET)
        c.network(client.API + NET)
        self.assertEqual(len(t.calls), 2)

    def test_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            Client(FakeTransport({}), TOKEN).get("https://example.com/2.2/account")

    def test_no_session_no_call(self):
        t = FakeTransport({})
        with self.assertRaises(client.SessionInvalid):
            Client(t, None).account()
        self.assertEqual(t.calls, [])


class TestSecrets(unittest.TestCase):
    def test_network_passwords_removed(self):
        t = FakeTransport({("GET", NET): [ok("network")]})
        net = Client(t, TOKEN).network(NET)
        text = json.dumps(net)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("password", net)
        self.assertNotIn("password", net["guest_network"])
        self.assertEqual(net["guest_network"]["name"], "Example Guest")      # the rest is kept

    def test_thread_keys_removed(self):
        t = FakeTransport({("GET", NET + "/thread"): [ok("thread")]})
        thread = Client(t, TOKEN).thread(NET)
        self.assertNotIn("SECRET", json.dumps(thread))
        self.assertEqual(thread["channel"], 15)

    def test_token_never_in_errors(self):
        for name, status in (("error_session_invalid", 401), ("error_access_denied", 403),
                             ("error_rate_limit", 429), ("error_not_found", 404)):
            t = FakeTransport({("GET", "/2.2/account"): [err(name, status)]})
            with self.assertRaises(client.EeroError) as cm:
                Client(t, TOKEN).account()
            self.assertNotIn(TOKEN, str(cm.exception))
            self.assertNotIn(TOKEN, repr(cm.exception.args))


class TestErrors(unittest.TestCase):
    def call(self, *answers):
        t = FakeTransport({("GET", "/2.2/account"): list(answers)})
        return Client(t, TOKEN).account()

    def test_session_invalid(self):
        with self.assertRaises(client.SessionInvalid) as cm:
            self.call(err("error_session_invalid", 401))
        self.assertEqual(cm.exception.code, "error.session.invalid")

    def test_rate_limited_with_retry_after(self):
        with self.assertRaises(client.RateLimited) as cm:
            self.call(err("error_rate_limit", 429, {"Retry-After": "30"}))
        self.assertEqual(cm.exception.retry_after, 30)

    def test_rate_limited_code_on_other_status(self):
        body = json.dumps({"meta": {"code": 400, "error": "error.rate.limit"}}).encode()
        with self.assertRaises(client.RateLimited) as cm:
            self.call(Response(400, {}, body))
        self.assertIsNone(cm.exception.retry_after)

    def test_retry_after_bounds(self):
        self.assertEqual(client.retry_after("999999"), client.MAX_RETRY_AFTER)
        self.assertIsNone(client.retry_after("Wed, 21 Oct 2015 07:28:00 GMT"))
        self.assertIsNone(client.retry_after("-1"))

    def test_not_available(self):
        with self.assertRaises(client.NotAvailable):
            self.call(err("error_access_denied", 403))
        with self.assertRaises(client.NotAvailable):
            self.call(err("error_not_found", 404))     # no meta at all

    def test_server_error_and_garbage(self):
        with self.assertRaises(client.TransportError):
            self.call(Response(502, {}, b"<html>bad gateway</html>"))
        with self.assertRaises(client.TransportError):
            self.call(Response(200, {}, b"not json"))
        with self.assertRaises(client.TransportError):
            self.call(Response(200, {}, b"[1, 2]"))

    def test_too_large(self):
        with self.assertRaises(client.TransportError):
            self.call(Response(200, {}, b" " * (client.MAX_BODY + 1)))

    def test_transport_failure_passes_through(self):
        with self.assertRaises(client.TransportError):
            self.call(client.TransportError("network: ConnectTimeout"))


class TestRefresh(unittest.TestCase):
    def test_refresh_then_retry_once(self):
        t = FakeTransport({("GET", "/2.2/account"): [err("error_session_refresh", 401), ok("account")],
                           ("POST", "/2.2/login/refresh"): [Response(200, {}, b'{"meta": {"code": 200}, "data": {}}')]})
        c = Client(t, TOKEN)
        self.assertEqual(c.account()["name"], "Example User")
        self.assertEqual([x["path"] for x in t.calls], ["/2.2/account", "/2.2/login/refresh", "/2.2/account"])
        self.assertEqual(c.token, TOKEN)

    def test_refresh_asked_twice_means_signed_out(self):
        t = FakeTransport({("GET", "/2.2/account"): [err("error_session_refresh", 401)] * 2,
                           ("POST", "/2.2/login/refresh"): [Response(200, {}, b'{"meta": {"code": 200}, "data": {}}')]})
        with self.assertRaises(client.SessionInvalid):
            Client(t, TOKEN).account()
        self.assertEqual(len(t.calls), 3)

    def test_refresh_refused(self):
        t = FakeTransport({("GET", "/2.2/account"): [err("error_session_refresh", 401)],
                           ("POST", "/2.2/login/refresh"): [err("error_session_invalid", 401)]})
        with self.assertRaises(client.SessionInvalid):
            Client(t, TOKEN).account()


class TestLogin(unittest.TestCase):
    def test_login_and_verify(self):
        t = FakeTransport({
            ("POST", "/2.2/login"): [Response(200, {}, b'{"meta": {"code": 200}, "data": {"user_token": "pending-1"}}')],
            ("POST", "/2.2/login/verify"): [Response(200, {}, b'{"meta": {"code": 200}, "data": {"name": "x"}}')]})
        c = Client(t)
        pending = c.login("user@example.com")
        self.assertEqual(pending, "pending-1")
        self.assertNotIn("Cookie", t.calls[0]["headers"])
        self.assertEqual(t.calls[0]["json"], {"login": "user@example.com"})
        c.verify(pending, "123456")
        self.assertEqual(t.calls[1]["headers"]["Cookie"], "s=pending-1")
        self.assertEqual(t.calls[1]["json"], {"code": "123456"})
        self.assertEqual(c.token, "pending-1")

    def test_wrong_code(self):
        body = b'{"meta": {"code": 401, "error": "error.verification.invalid"}}'
        t = FakeTransport({("POST", "/2.2/login/verify"): [Response(401, {}, body)]})
        c = Client(t)
        with self.assertRaises(client.LoginFailed) as cm:
            c.verify("pending-1", "000000")
        self.assertEqual(cm.exception.code, "error.verification.invalid")
        self.assertIsNone(c.token)

    def test_expired_pending_token(self):
        t = FakeTransport({("POST", "/2.2/login/verify"): [err("error_session_invalid", 401)]})
        with self.assertRaises(client.LoginFailed):
            Client(t).verify("pending-1", "123456")

    def test_bad_identifier(self):
        body = b'{"meta": {"code": 400, "error": "error.form.email.malformed"}}'
        t = FakeTransport({("POST", "/2.2/login"): [Response(400, {}, body)]})
        with self.assertRaises(client.LoginFailed) as cm:
            Client(t).login("not an address")
        self.assertEqual(cm.exception.code, "error.form.email.malformed")

    def test_logout_form_and_clears_token(self):
        t = FakeTransport({("POST", "/2.2/logout"): [err("error_session_invalid", 401)]})
        c = Client(t, TOKEN)
        with self.assertRaises(client.SessionInvalid):
            c.logout()
        self.assertEqual(t.calls[0]["form"], {"Cookie": "s=" + TOKEN})
        self.assertIsNone(c.token)


if __name__ == "__main__":
    unittest.main()
