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

"""eero cloud API client: the calls the plugin needs, read-only apart from login.

The API is the private one the eero app uses (see docs/API.md; fulviofreitas/eero-api is the reference).
HTTP goes through a transport (RequestsTransport on the router, a fake in tests), so this module needs
nothing beyond the standard library. The session token is sent as the cookie `s=<token>`; it never
appears in an exception, a log line or a returned document.
"""
import http.cookiejar
import json

API = 'https://api-user.e2ro.com'
VERSION = '/2.2'
USER_AGENT = 'eero-ios/2026.8.1 (iPhone; iOS 18.5)'     # what eero-api sends; the API expects an app-like agent
TIMEOUT = 20
MAX_BODY = 10 * 1024 * 1024
MAX_RETRY_AFTER = 86400

# keys whose values are credentials (Wi-Fi and guest passwords, Thread network keys); removed from every
# document before it is returned, wherever they occur
SECRET_KEYS = frozenset({'password', 'master_key', 'commissioning_credential', 'pan_id', 'xpan_id'})

SESSION_GONE = frozenset({'error.session.invalid', 'error.session.expired', 'error.session.revoked'})
SESSION_REFRESH = 'error.session.refresh'
RATE_LIMIT = 'error.rate.limit'


class EeroError(Exception):
    """Any failure. `code` is eero's meta.error (or a short tag of ours), `status` the HTTP status."""

    def __init__(self, code, status=None):
        super().__init__(code if status is None else '%s (HTTP %s)' % (code, status))
        self.code = code
        self.status = status


class SessionInvalid(EeroError):
    """The session is gone (expired, revoked, never valid): sign in again."""


class LoginFailed(EeroError):
    """Login or code verification refused (wrong code, too many attempts, unknown account...)."""


class RateLimited(EeroError):
    """eero asked us to slow down. `retry_after` is seconds, if eero said."""

    def __init__(self, code, status=None, retry_after=None):
        super().__init__(code, status)
        self.retry_after = retry_after


class NotAvailable(EeroError):
    """Not available to this account or network (403, 404): stop asking for it."""


class TransportError(EeroError):
    """Network trouble, a timeout, a server error or a response we can't read: try again later."""


class _RefreshNeeded(EeroError):
    """Internal: eero wants the session refreshed before it answers (401 error.session.refresh)."""


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = body


class RequestsTransport:
    """HTTP over a requests.Session (keeps connections open between polls). Cookies are never stored by
    the session: the token is passed explicitly on every call."""

    def __init__(self):
        import requests
        self._requests = requests
        self._session = requests.Session()
        self._session.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))

    def __call__(self, method, url, headers, json_body=None, form=None, timeout=TIMEOUT):
        try:
            r = self._session.request(method, url, headers=headers, json=json_body, data=form, timeout=timeout,
                                      stream=True, allow_redirects=False)
            try:
                body = r.raw.read(MAX_BODY + 1, decode_content=True)
            finally:
                r.close()
        except self._requests.RequestException as e:
            raise TransportError('network: %s' % type(e).__name__) from None
        return Response(r.status_code, r.headers, body)

    def close(self):
        self._session.close()


def strip_secrets(doc):
    if isinstance(doc, dict):
        return {k: strip_secrets(v) for k, v in doc.items() if k not in SECRET_KEYS}
    if isinstance(doc, list):
        return [strip_secrets(v) for v in doc]
    return doc


def retry_after(value):
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return min(seconds, MAX_RETRY_AFTER) if seconds >= 0 else None


def path_of(url_or_path):
    """'/2.2/networks/1' or a full URL -> '/2.2/networks/1' (resource URLs come back as paths)."""
    if url_or_path.startswith(API):
        url_or_path = url_or_path[len(API):]
    if not url_or_path.startswith('/'):
        raise ValueError('not an eero API path')
    return url_or_path


class Client:
    def __init__(self, transport, token=None):
        self._transport = transport
        self.token = token

    # --- transport and errors

    def _call(self, method, path, json_body=None, form=None, token=None):
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', 'Accept-Language': 'en-US'}
        token = self.token if token is None else token
        if token:
            headers['Cookie'] = 's=' + token
        r = self._transport(method, API + path_of(path), headers, json_body=json_body, form=form)
        if len(r.body) > MAX_BODY:
            raise TransportError('response too large', r.status)
        try:
            doc = json.loads(r.body) if r.body else {}
        except ValueError:
            doc = None
        meta = doc.get('meta') if isinstance(doc, dict) and isinstance(doc.get('meta'), dict) else {}
        code = meta.get('error') if isinstance(meta.get('error'), str) else None

        if r.status == 429 or code == RATE_LIMIT:
            raise RateLimited(code or 'rate limited', r.status, retry_after(r.headers.get('retry-after')))
        if r.status == 401:
            if code == SESSION_REFRESH:
                raise _RefreshNeeded(code, r.status)
            if code is None or code in SESSION_GONE:
                raise SessionInvalid(code or 'unauthorized', r.status)
            raise LoginFailed(code, r.status)
        if r.status in (403, 404):
            raise NotAvailable(code or 'not available', r.status)
        if r.status >= 500:
            raise TransportError(code or 'server error', r.status)
        if r.status >= 400:
            raise LoginFailed(code or 'refused', r.status)
        if doc is None or not isinstance(doc, dict):
            raise TransportError('unreadable response', r.status)
        return doc.get('data')

    def _request(self, method, path, **kw):
        """A call that needs the session: refresh it once if eero asks, then repeat the call once."""
        if not self.token:
            raise SessionInvalid('no session')
        try:
            return self._call(method, path, **kw)
        except _RefreshNeeded:
            self.refresh()
            try:
                return self._call(method, path, **kw)
            except _RefreshNeeded as e:
                raise SessionInvalid(e.code, e.status) from None

    def get(self, path):
        return strip_secrets(self._request('GET', path))

    # --- login (POST /login -> code by email or text -> POST /login/verify)

    def login(self, identifier):
        """Ask eero to send a code to this email address or phone number. Returns the pending token,
        which only becomes a session once verify() accepts the code."""
        data = self._call('POST', VERSION + '/login', json_body={'login': identifier}, token='')
        pending = data.get('user_token') if isinstance(data, dict) else None
        if not isinstance(pending, str) or not pending:
            raise LoginFailed('no token in login response')
        return pending

    def verify(self, pending, code):
        """Confirm the code; on success the pending token is the session (also set on this client)."""
        try:
            self._call('POST', VERSION + '/login/verify', json_body={'code': code}, token=pending)
        except SessionInvalid as e:
            raise LoginFailed(e.code, e.status) from None    # the pending token expired: start over
        self.token = pending
        return pending

    def refresh(self):
        """Refresh the session. The response carries a token, but the current one stays in use (as in
        eero-api: the API has no separate refresh token)."""
        try:
            self._call('POST', VERSION + '/login/refresh')
        except _RefreshNeeded as e:
            raise SessionInvalid(e.code, e.status) from None

    def logout(self):
        """End the session at eero. The form field is literally named Cookie."""
        try:
            if self.token:
                self._call('POST', VERSION + '/logout', form={'Cookie': 's=' + self.token})
        finally:
            self.token = None

    # --- reads (see docs/API.md for cadence and fields)

    def account(self):
        return self.get(VERSION + '/account')

    def networks(self):
        """[{'url': '/2.2/networks/<id>', 'name': ...}, ...] for the account."""
        nets = (self.account() or {}).get('networks') or {}
        return [n for n in nets.get('data') or [] if isinstance(n, dict) and n.get('url')]

    def network(self, net):
        return self.get(net)

    def units(self, net):
        """The eero units (the API calls them eeros; our GUI calls them devices)."""
        return self.get(net + '/eeros') or []

    def clients(self, net):
        """Every client the network knows, connected or not (the API calls them devices)."""
        return self.get(net + '/devices') or []

    def speedtests(self, net):
        return self.get(net + '/speedtest') or []

    def thread(self, net):
        return self.get(net + '/thread')

    def connections(self, unit):
        """Ports and wireless clients of one unit: unit['resources']['connections']."""
        return self.get(unit)

    # --- changes (the only ones the plugin makes; see docs/API.md)

    def set_location(self, unit, name):
        """Rename a unit: its location, the name the app shows. `unit` is the unit's url (/2.2/eeros/<id>)."""
        return strip_secrets(self._request('PUT', unit, form={'location': name}))
