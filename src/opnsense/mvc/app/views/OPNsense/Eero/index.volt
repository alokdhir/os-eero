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

<style>
    .eero-bars { display: inline-flex; align-items: flex-end; gap: 2px; height: 14px; vertical-align: middle; }
    .eero-bars i { display: block; width: 4px; background: currentColor; border-radius: 1px; }
    .eero-bars i.off { opacity: 0.2; }
</style>

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

        /* tabs <-> address (#units, #clients, #network, #settings); Apply only belongs to Settings */
        function show(hash) {
            const tab = $('#maintabs a[href="' + hash + '"]').length ? hash : '#units';
            $('#maintabs a[href="' + tab + '"]').tab('show');
            $('.eero-apply').toggle(tab === '#settings');
        }
        $('#maintabs a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
            history.replaceState(null, null, e.target.hash);
            $('.eero-apply').toggle(e.target.hash === '#settings');
        });
        $(window).on('hashchange', function () { show(window.location.hash); });
        show(window.location.hash);

        /* --- Devices, Clients, Network: all from eerod's cache. Grid cells are not escaped by the core grid's
           default formatter, so every column with eero- or device-supplied text uses one that escapes. */

        const dash = '<span class="text-muted">–</span>';
        const formatters = {
            text: function (column, row) {
                const v = row[column.id];
                return v === null || v === undefined || v === '' ? dash : esc(v);
            },
            unit: function (column, row) {
                return esc(row.name) + (row.primary ? ' <span class="text-muted">({{ lang._('primary') }})</span>' : '')
                    + (row.online ? '' : ' <span class="label label-danger">{{ lang._('Offline') }}</span>');
            },
            client: function (column, row) {
                /* icon: a Font Awesome class from Loupe (when installed); only fa-* class names are used */
                const icon = /^[a-z0-9 -]+$/.test(row.icon || '') ? '<i class="' + row.icon + ' fa-fw text-muted"></i> ' : '<i class="fa fa-fw"></i> ';
                return icon + '<span title="' + esc(row.mac) + '">' + esc(row.name) + '</span>' + (row.private_mac ? ' <i class="fa fa-user-secret text-muted" title="{{ lang._('Private (randomised) MAC address') }}"></i>' : '');
            },
            bars: function (column, row) {
                /* eero's 0-5 mesh quality as a signal meter: five rising bars, filled ones coloured by level */
                const n = parseInt(row.mesh);
                if (isNaN(n)) return dash;
                const cls = n >= 4 ? 'text-success' : (n === 3 ? 'text-warning' : 'text-danger');
                let html = '<span class="eero-bars ' + cls + '" title="' + n + '/5">';
                for (let i = 1; i <= 5; i++) {
                    html += '<i style="height: ' + (i * 20) + '%"' + (i > n ? ' class="off"' : '') + '></i>';
                }
                return html + '</span>';
            },
            uptime: function (column, row) {
                const s = parseInt(row.uptime);
                if (isNaN(s)) return dash;
                const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
                return d ? d + 'd ' + h + 'h' : (h ? h + 'h ' + m + 'm' : m + 'm');
            },
            signal: function (column, row) {
                const v = parseInt(row.signal);
                if (isNaN(v)) return dash;
                const cls = v >= -60 ? 'text-success' : (v >= -70 ? 'text-warning' : 'text-danger');
                return '<i class="fa fa-circle ' + cls + '"></i>&nbsp; ' + v + ' dBm';
            },
            rate: function (column, row) {
                const v = parseInt(row.rate);
                return isNaN(v) ? dash : v + ' Mbps';
            },
            seen: function (column, row) {
                if (row.connected) return '{{ lang._('now') }}';
                const t = Date.parse(row.last_seen);
                return isNaN(t) ? dash : esc(new Date(t).toLocaleString());
            }
        };
        const grids = {};

        /* a clear (×) button at the end of each grid's search field (as in os-loupe): shown while there is
           text; the grid searches on keyup, so clearing is passed on as one */
        function clearable(id) {
            const $f = $('#' + id + '-search-field');
            if (!$f.length || $f.next('.eero-clear').length) return;
            const $x = $('<span class="input-group-btn eero-clear"><button class="btn btn-default" type="button" title="{{ lang._("Clear") }}"><i class="fa fa-times"></i></button></span>');
            $f.after($x);
            const sync = () => $x.toggle($f.val() !== '');
            $f.on('input keyup', sync);
            $x.find('button').on('click', function () {
                $f.val('').trigger('keyup').focus();
                sync();
            });
            sync();
        }

        function grid(id, endpoint, extra) {
            if (grids[id]) {
                $('#' + id).bootgrid('reload');
                return;
            }
            grids[id] = $('#' + id).UIBootgrid({
                search: endpoint,
                options: {
                    selection: false,
                    multiSelect: false,
                    rowCount: [-1, 25, 50],
                    requestHandler: function (request) { return Object.assign(request, extra ? extra() : {}); },
                    formatters: formatters
                }
            });
            clearable(id);
        }
        let clientsShow = '';
        $('#clients_show button').on('click', function () {
            $('#clients_show button').removeClass('active');
            $(this).addClass('active');
            clientsShow = $(this).data('show');
            grid('grid_clients', '/api/eero/report/search_clients', () => ({show: clientsShow}));
        });
        function showNetwork() {
            ajaxGet('/api/eero/report/network', {}, function (groups) {
                if (!Array.isArray(groups) || !groups.length) {
                    $('#network_body').text('{{ lang._('Nothing from eero yet. Sign in on the Settings tab; the first update takes a few seconds.') }}');
                    return;
                }
                const box = $('<div/>');
                groups.forEach(function (g) {
                    const tbody = $('<tbody/>');
                    g.rows.forEach(function (r) {
                        tbody.append($('<tr/>').append($('<td style="width: 30%"/>').text(plain(r[0])), $('<td/>').text(plain(r[1]))));
                    });
                    box.append($('<h4/>').text(plain(g.title)),
                        $('<table class="table table-striped table-condensed" style="margin-bottom: 20px"/>').append(tbody));
                });
                $('#network_body').empty().append(box);
            });
        }
        function load(tab) {
            if (tab === '#units') grid('grid_units', '/api/eero/report/search_units');
            else if (tab === '#clients') grid('grid_clients', '/api/eero/report/search_clients', () => ({show: clientsShow}));
            else if (tab === '#network') showNetwork();
        }
        $('#maintabs a[data-toggle="tab"]').on('shown.bs.tab', function (e) { load(e.target.hash); });
        load($('#maintabs li.active a').attr('href'));
        setInterval(function () { load($('#maintabs li.active a').attr('href')); }, 60000);

        /* --- status line and the eero account (all from eerod's cache: the page never calls eero) */

        /* API answers reach the browser HTML-escaped by core (htmlspecialchars, ENT_NOQUOTES: & < > only;
           API-key clients get raw JSON). plain() undoes that once; esc() then escapes for HTML, quotes included. */
        function plain(s) {
            s = String(s ?? '');
            return s.includes('&') ? htmlDecode(s) : s;          /* core's helper (opnsense.js), as os-loupe does */
        }
        function esc(s) {
            return plain(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
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
                $('#eero_status_dot').removeClass('text-success text-info text-warning text-danger text-muted').addClass(cls);
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
                                error.text(plain(message));
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

<p id="eero_status" style="margin: 0 0 10px 2px">
    <i id="eero_status_dot" class="fa fa-circle text-muted"></i>&nbsp; <span id="eero_status_text">{{ lang._('Checking…') }}</span>
</p>

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li><a data-toggle="tab" href="#units">{{ lang._('Units') }}</a></li>
    <li><a data-toggle="tab" href="#clients">{{ lang._('Clients') }}</a></li>
    <li><a data-toggle="tab" href="#network">{{ lang._('Network') }}</a></li>
    <li><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
</ul>
<div class="tab-content content-box">
    <div id="units" class="tab-pane fade in">
        <table id="grid_units" class="table table-condensed table-hover table-striped table-responsive">
            <thead><tr>
                <th data-column-id="id" data-identifier="true" data-visible="false">ID</th>
                <th data-column-id="name" data-formatter="unit">{{ lang._('Name') }}</th>
                <th data-column-id="model" data-formatter="text">{{ lang._('Model') }}</th>
                <th data-column-id="ip" data-formatter="text" data-width="10em">{{ lang._('Address') }}</th>
                <th data-column-id="backhaul" data-formatter="text">{{ lang._('Backhaul') }}</th>
                <th data-column-id="mesh" data-formatter="bars" data-min-width="60" data-max-width="80">{{ lang._('Mesh') }}</th>
                <th data-column-id="clients" data-type="numeric" data-min-width="60" data-max-width="80">{{ lang._('Clients') }}</th>
                <th data-column-id="uptime" data-formatter="uptime" data-min-width="70" data-max-width="100">{{ lang._('Up for') }}</th>
                <th data-column-id="firmware" data-formatter="text" data-visible="false">{{ lang._('Firmware') }}</th>
            </tr></thead>
            <tbody></tbody>
        </table>
    </div>
    <div id="clients" class="tab-pane fade in">
        <div style="padding: 10px 10px 0">
            <div class="btn-group" id="clients_show">
                <button type="button" class="btn btn-default active" data-show="">{{ lang._('Connected now') }}</button>
                <button type="button" class="btn btn-default" data-show="all">{{ lang._('All known') }}</button>
            </div>
        </div>
        <table id="grid_clients" class="table table-condensed table-hover table-striped table-responsive">
            <thead><tr>
                <th data-column-id="mac" data-identifier="true" data-visible="false" data-formatter="text">{{ lang._('MAC address') }}</th>
                <th data-column-id="name" data-formatter="client">{{ lang._('Name') }}</th>
                <th data-column-id="unit" data-formatter="text">{{ lang._('On eero') }}</th>
                <th data-column-id="band" data-formatter="text" data-width="7em">{{ lang._('Band') }}</th>
                <th data-column-id="signal" data-formatter="signal" data-width="8em">{{ lang._('Signal') }}</th>
                <th data-column-id="rate" data-formatter="rate" data-width="8em">{{ lang._('Rate') }}</th>
                <th data-column-id="ip" data-formatter="text" data-width="10em">{{ lang._('Address') }}</th>
                <th data-column-id="type" data-formatter="text">{{ lang._('Type') }}</th>
                <th data-column-id="maker" data-formatter="text" data-visible="false">{{ lang._('Maker') }}</th>
                <th data-column-id="last_seen" data-formatter="seen" data-width="9em">{{ lang._('Last seen') }}</th>
            </tr></thead>
            <tbody></tbody>
        </table>
    </div>
    <div id="network" class="tab-pane fade in">
        <div id="network_body" style="padding: 10px">{{ lang._('Loading…') }}</div>
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
