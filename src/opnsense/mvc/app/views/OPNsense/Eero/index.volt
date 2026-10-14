{#
Copyright (C) 2026 Alok K. Dhir
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
#}

<script>
    $(document).ready(function () {
        mapDataToFormUI({'frm_settings': '/api/eero/settings/get'}).done(function () {
            updateServiceControlUI('eero');
        });

        $('#reconfigureAct').SimpleActionButton({
            onPreAction: function () {
                const dfObj = new $.Deferred();
                saveFormToEndpoint('/api/eero/settings/set', 'frm_settings', function () { dfObj.resolve(); });
                return dfObj;
            },
            onAction: function () {
                updateServiceControlUI('eero');
            }
        });

        /* tabs <-> address (#devices, #clients, #network, #settings); Apply only belongs to Settings */
        function show(hash) {
            const tab = $('#maintabs a[href="' + hash + '"]').length ? hash : '#devices';
            $('#maintabs a[href="' + tab + '"]').tab('show');
            $('.eero-apply').toggle(tab === '#settings');
        }
        $('#maintabs a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
            history.replaceState(null, null, e.target.hash);
            $('.eero-apply').toggle(e.target.hash === '#settings');
        });
        $(window).on('hashchange', function () { show(window.location.hash); });
        show(window.location.hash);

        /* --- status line and the eero account (all from eerod's cache: the page never calls eero) */

        function esc(s) {
            return String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
        }
        function clock(ts) {
            return new Date(ts * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
        }
        function ago(ts) {
            const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
            return s < 90 ? s + ' s' : Math.round(s / 60) + ' min';
        }

        const SIGNIN = '<a href="#" class="eero-signin">{{ lang._('Sign in') }}</a>';
        function statusLine(st) {
            const net = st.network ? ' <strong>' + esc(st.network) + '</strong>' : '';
            if (!st.running) {
                return ['text-muted', '{{ lang._('Service stopped. Enable it on the Settings tab.') }}'];
            }
            switch (st.status) {
                case 'ok':
                    return ['text-success', '{{ lang._('Connected to') }}' + net + ' · {{ lang._('updated') }} ' + ago(st.last_ok) + ' {{ lang._('ago') }}'];
                case 'starting':
                    return ['text-info', '{{ lang._('Signed in, fetching from eero…') }}'];
                case 'needs_login':
                    return ['text-warning', esc(st.message || '{{ lang._('Not signed in to eero') }}') + '. ' + SIGNIN];
                case 'rate_limited':
                    return ['text-warning', '{{ lang._('eero is limiting requests; trying again at') }} ' + clock(st.next_try)];
                default:
                    return ['text-danger', esc(st.message || '{{ lang._('Cannot reach eero') }}') +
                        (st.next_try ? '; {{ lang._('trying again at') }} ' + clock(st.next_try) : '')];
            }
        }
        function refreshStatus() {
            ajaxGet('/api/eero/account/status', {}, function (st) {
                if (!st || st.status === undefined) {
                    return;
                }
                const [cls, html] = statusLine(st);
                $('#eero_status').removeClass('text-success text-info text-warning text-danger text-muted').addClass(cls);
                $('#eero_status_text').html(html);
                const s = st.session || {};
                $('#eero_account_text').html(s.signed_in
                    ? '{{ lang._('Signed in') }}' + (st.network ? ' {{ lang._('to') }} <strong>' + esc(st.network) + '</strong>' : '') +
                      (s.since ? ' {{ lang._('since') }} ' + esc(new Date(s.since * 1000).toLocaleString()) : '') + '.'
                    : '{{ lang._('Not signed in.') }}');
                $('#eero_signin').text(s.signed_in ? '{{ lang._('Sign in again') }}' : '{{ lang._('Sign in') }}');
                $('#eero_signout').toggle(!!s.signed_in);
            });
        }
        refreshStatus();
        setInterval(refreshStatus, 15000);

        /* --- sign in: 1) email or phone, eero sends a code; 2) the code */

        function askDialog(title, label, help, button, inputType, send) {
            const input = $('<input class="form-control"/>').attr('type', inputType);
            const error = $('<div class="text-danger" style="margin-top: 8px"/>');
            const body = $('<div/>').append($('<label/>').text(label), input,
                $('<p class="help-block"/>').text(help), error);
            BootstrapDialog.show({
                title: title,
                message: body,
                type: BootstrapDialog.TYPE_DEFAULT,
                onshown: function () { input.focus(); },
                buttons: [{
                    label: '{{ lang._('Cancel') }}',
                    action: function (dlg) { dlg.close(); }
                }, {
                    id: 'eero_dialog_go',
                    label: button,
                    cssClass: 'btn-primary',
                    hotkey: 13,
                    action: function (dlg) {
                        const btn = dlg.getButton('eero_dialog_go');
                        btn.disable(); btn.spin(); error.text('');
                        send(input.val(), function (message) {          // message: null on success
                            btn.enable(); btn.stopSpin();
                            if (message) {
                                error.text(message);
                            } else {
                                dlg.close();
                            }
                        });
                    }
                }]
            });
        }
        function post(url, data, done) {
            ajaxCall(url, data, function (r) {
                done(r && r.result === 'ok' ? null : ((r && r.message) || '{{ lang._('Something went wrong. Try again.') }}'));
            });
        }
        function signIn() {
            askDialog('{{ lang._('Sign in to eero') }}', '{{ lang._('Email address or phone number') }}',
                '{{ lang._('The one your eero account uses. eero will email or text you a code. It is not stored.') }}',
                '{{ lang._('Send code') }}', 'text',
                function (who, done) {
                    post('/api/eero/account/signin', {identifier: who}, function (message) {
                        done(message);
                        if (!message) {
                            askDialog('{{ lang._('Sign in to eero') }}', '{{ lang._('Code') }}',
                                '{{ lang._('The code eero just sent you. It works for 15 minutes.') }}',
                                '{{ lang._('Sign in') }}', 'text',
                                function (code, done2) {
                                    post('/api/eero/account/verify', {code: code}, function (message2) {
                                        done2(message2);
                                        if (!message2) {
                                            refreshStatus();
                                        }
                                    });
                                });
                        }
                    });
                });
        }
        $(document).on('click', '#eero_signin, .eero-signin', function (e) {
            e.preventDefault();
            signIn();
        });
        $('#eero_signout').on('click', function () {
            BootstrapDialog.confirm({
                title: '{{ lang._('Sign out of eero') }}',
                message: '{{ lang._('The router stops reading your eero network until you sign in again. History is kept.') }}',
                type: BootstrapDialog.TYPE_WARNING,
                btnOKLabel: '{{ lang._('Sign out') }}',
                callback: function (yes) {
                    if (yes) {
                        post('/api/eero/account/signout', {}, function () { refreshStatus(); });
                    }
                }
            });
        });
    });
</script>

<p id="eero_status" class="text-muted" style="margin: 0 0 10px 2px">
    <i class="fa fa-circle"></i>&nbsp; <span id="eero_status_text">{{ lang._('Checking…') }}</span>
</p>

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li><a data-toggle="tab" href="#devices">{{ lang._('Devices') }}</a></li>
    <li><a data-toggle="tab" href="#clients">{{ lang._('Clients') }}</a></li>
    <li><a data-toggle="tab" href="#network">{{ lang._('Network') }}</a></li>
    <li><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
</ul>
<div class="tab-content content-box">
    <div id="devices" class="tab-pane fade in">
        <p style="padding: 10px">{{ lang._('Your eero units will be listed here.') }}</p>
    </div>
    <div id="clients" class="tab-pane fade in">
        <p style="padding: 10px">{{ lang._('Every client, and which eero it is on, will be listed here.') }}</p>
    </div>
    <div id="network" class="tab-pane fade in">
        <p style="padding: 10px">{{ lang._('Your eero network settings will be shown here.') }}</p>
    </div>
    <div id="settings" class="tab-pane fade in">
        {{ partial('layout_partials/base_form', ['fields': formSettings, 'id': 'frm_settings']) }}
        <div class="table-responsive">
            <table class="table table-striped table-condensed">
                <colgroup><col class="col-md-3"/><col class="col-md-9"/></colgroup>
                <tbody>
                    <tr>
                        <td><div class="control-label"><b>{{ lang._('eero account') }}</b></div></td>
                        <td>
                            <span id="eero_account_text">{{ lang._('Checking…') }}</span>
                            <div style="margin-top: 6px">
                                <button type="button" class="btn btn-default btn-xs" id="eero_signin">{{ lang._('Sign in') }}</button>
                                <button type="button" class="btn btn-default btn-xs" id="eero_signout" style="display: none">{{ lang._('Sign out') }}</button>
                            </div>
                            <div class="help-block">{{ lang._('Signing in or out takes effect right away; no need to Apply. The router signs in to eero like the app does. The session is kept on the router, readable by root only, and not in the configuration or its backups.') }}</div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>

<div class="eero-apply" style="display: none">
    {{ partial('layout_partials/base_apply_button', {'data_endpoint': '/api/eero/service/reconfigure', 'data_service_widget': 'eero', 'data_error_title': 'Error applying eero settings'}) }}
</div>
