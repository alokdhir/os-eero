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

        /* tabs <-> address: #units, #clients, #network, #settings, the Units tab's #unit=<id>, and the Clients
           tab's views #moves and #client=<mac>. Apply only belongs to Settings. */
        let clientView = {view: 'list', mac: null};
        let unitView = null;                        /* a unit's id while its page is shown */
        function tabOf(hash) {
            if (hash.startsWith('#unit=')) {
                unitView = decodeURIComponent(hash.slice(6));
                return '#units';
            }
            if (hash === '#units') {
                unitView = null;
            }
            if (hash.startsWith('#client=')) {
                clientView = {view: 'client', mac: decodeURIComponent(hash.slice(8)).toLowerCase()};
                return '#clients';
            }
            if (hash === '#moves') {
                clientView = {view: 'moves', mac: null};
                return '#clients';
            }
            if (hash === '#clients') {
                clientView = {view: 'list', mac: null};
            }
            return $('#maintabs a[href="' + hash + '"]').length ? hash : '#units';
        }
        function show(hash) {
            const tab = tabOf(hash || '');
            $('.eero-apply').toggle(tab === '#settings');
            if ($('#maintabs li.active a').attr('href') === tab) {
                load(tab);                      /* already showing: no 'shown' event, so load the view here */
            } else {
                $('#maintabs a[href="' + tab + '"]').tab('show');
            }
        }
        $('#maintabs a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
            const hash = window.location.hash;
            if (tabOf(hash) !== e.target.hash) {
                if (e.target.hash === '#clients') clientView = {view: 'list', mac: null};
                if (e.target.hash === '#units') unitView = null;
                history.replaceState(null, null, e.target.hash);
            }
            $('.eero-apply').toggle(e.target.hash === '#settings');
        });
        $(window).on('hashchange', function () { show(window.location.hash); });

        /* --- Devices, Clients, Network: all from eerod's cache. Grid cells are not escaped by the core grid's
           default formatter, so every column with eero- or device-supplied text uses one that escapes. */

        const dash = '<span class="text-muted">–</span>';
        function unitLabel(row, name) {
            return name + (row.primary ? ' <span class="text-muted">({{ lang._('primary') }})</span>' : '')
                + (row.online ? '' : ' <span class="label label-danger">{{ lang._('Offline') }}</span>');
        }
        const formatters = {
            text: function (column, row) {
                const v = row[column.id];
                return v === null || v === undefined || v === '' ? dash : esc(v);
            },
            unit: function (column, row) {
                return unitLabel(row, '<a href="#unit=' + encodeURIComponent(plain(row.id)) + '">' + esc(row.name) + '</a>');
            },
            client: function (column, row) {
                /* icon: a Font Awesome class from Loupe (when installed); only fa-* class names are used */
                const icon = /^[a-z0-9 -]+$/.test(row.icon || '') ? '<i class="' + row.icon + ' fa-fw text-muted"></i> ' : '<i class="fa fa-fw"></i> ';
                const tip = row.mac + (row.private_mac ? ' {{ lang._('(private address)') }}' : '');
                return icon + '<a href="#client=' + encodeURIComponent(plain(row.mac)) + '" title="' + esc(tip) + '">' + esc(row.name) + '</a>';
            },
            bars: function (column, row) {
                /* a 0-5 rating from eero (mesh quality, client connection quality) as a signal meter: five
                   rising bars, filled ones coloured by level */
                const n = parseInt(row[column.id]);
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
                /* how well the eero hears the client: -67 or better is good for anything; to -80 is fine for
                   devices that send little (shades, fans, plugs); below -80 is poor */
                const cls = v >= -67 ? 'text-success' : (v >= -80 ? 'text-warning' : 'text-danger');
                const tip = v >= -67 ? '{{ lang._('Good') }}' : (v >= -80 ? '{{ lang._('Fair: fine for devices that send little') }}' : '{{ lang._('Poor') }}');
                return '<span title="' + tip + '"><i class="fa fa-circle ' + cls + '"></i>&nbsp; ' + v + ' dBm</span>';
            },
            when: function (column, row) {
                return esc(when(row.ts));
            },
            move: function (column, row) {
                return row.event === 'band' ? esc(row.to_unit) : esc(row.from_unit) + ' → ' + esc(row.to_unit);
            },
            bands: function (column, row) {
                return row.band_from === row.band_to ? esc(ghz(row.band_to)) : esc(ghz(row.band_from)) + ' → ' + esc(ghz(row.band_to));
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
        let hours = 24;
        $('#clients_show button').on('click', function () {
            const show = $(this).data('show');
            if (show === 'moves') {
                window.location.hash = '#moves';
                return;
            }
            clientsShow = show;
            if (window.location.hash !== '#clients') {
                window.location.hash = '#clients';         /* the hashchange shows the list */
            } else {
                showClients();
            }
        });
        $('.eero-period button').on('click', function () {
            hours = parseInt($(this).data('hours'));
            load($('#maintabs li.active a').attr('href'));
        });

        function when(ts) {
            const d = new Date(ts * 1000);
            const today = new Date().toDateString() === d.toDateString();
            return today ? d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
                : d.toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
        }
        function ghz(band) {
            return band ? plain(band) + ' GHz' : '';
        }
        function duration(sec) {
            const h = Math.floor(sec / 3600), m = Math.round(sec % 3600 / 60);
            return h ? h + 'h ' + m + 'm' : m + 'm';
        }
        function views(view) {
            $('#clients_list').toggle(view === 'list');
            $('#clients_moves').toggle(view === 'moves');
            $('#client_detail').toggle(view === 'client');
            $('#clients_bar').toggle(view !== 'client');
            $('#clients_show button').removeClass('active');
            $('#clients_show button[data-show="' + (view === 'moves' ? 'moves' : clientsShow) + '"]').addClass('active');
            $('#clients_bar .eero-period').toggle(view !== 'list');
            $('.eero-period button').removeClass('active').filter('[data-hours="' + hours + '"]').addClass('active');
        }
        function showClients() {
            views('list');
            grid('grid_clients', '/api/eero/report/search_clients', () => ({show: clientsShow}));
        }
        function showMoves() {
            views('moves');
            grid('grid_moves', '/api/eero/report/search_moves', () => ({hours: hours}));
        }

        const MOVE = {
            roamed: e => esc(e.from_unit) + ' → <strong>' + esc(e.to_unit) + '</strong>',
            band: e => esc(e.to_unit) + ': ' + esc(ghz(e.band_from)) + ' → ' + esc(ghz(e.band_to)),
            connected: e => '{{ lang._('joined') }} <strong>' + esc(e.to_unit) + '</strong>',
            disconnected: e => '{{ lang._('left') }} ' + esc(e.from_unit)
        };
        function moveText(e) {
            const band = e.event === 'roamed' && e.band_from !== e.band_to ? ' <span class="text-muted">(' + esc(ghz(e.band_from)) + ' → ' + esc(ghz(e.band_to)) + ')</span>' : '';
            return (MOVE[e.event] ? MOVE[e.event](e) : esc(e.event)) + band;
        }
        const BAR = ['progress-bar-success', 'progress-bar-info', 'progress-bar-warning', 'progress-bar-danger', ''];
        function showClient(mac) {
            views('client');
            ajaxGet('/api/eero/report/client/' + encodeURIComponent(mac) + '/' + hours, {}, function (page) {
                const $d = $('#client_detail_body').empty();
                if (!page || page.error || !page.client) {
                    $d.text(page && page.error ? plain(page.error) : '{{ lang._('eero does not know this client.') }}');
                    return;
                }
                const c = page.client;
                const icon = /^[a-z0-9 -]+$/.test(c.icon || '') ? '<i class="' + c.icon + ' fa-fw text-muted"></i> ' : '';
                const now = c.connected
                    ? '{{ lang._('Now on') }} <strong>' + esc(c.unit) + '</strong>' + (c.band ? ' · ' + esc(c.band) : '')
                      + (c.signal !== null ? ' · ' + esc(c.signal) + ' dBm' : '') + (c.quality !== null ? ' · {{ lang._('quality') }} ' + esc(c.quality) + '/5' : '')
                    : '{{ lang._('Not connected') }}' + (c.last_seen ? ', {{ lang._('last seen') }} ' + esc(new Date(Date.parse(plain(c.last_seen))).toLocaleString()) : '');
                $d.append($('<h3 style="margin-top: 0"/>').html(icon + esc(c.name)),
                    $('<p class="text-muted"/>').text([plain(c.type), plain(c.mac) + (c.private_mac ? ' {{ lang._('(private address)') }}' : ''), plain(c.ip)].filter(Boolean).join(' · ')),
                    $('<p/>').html(now));

                if (!page.history_since) {
                    $d.append($('<p class="text-muted"/>').text('{{ lang._('No history yet: it starts a minute after the first update from eero.') }}'));
                    return;
                }
                const $bar = $('<div class="progress" style="margin-bottom: 6px"/>');
                const $legend = $('<p/>');
                const colours = {};
                page.time.forEach(function (t, i) {
                    const away = t.unit === null;
                    const cls = away ? '' : (colours[t.unit] = BAR[Object.keys(colours).length % BAR.length]);
                    const label = away ? '{{ lang._('Not connected') }}' : plain(t.unit);
                    $bar.append($('<div class="progress-bar ' + cls + '"/>').css({width: t.share + '%'})
                        .css(away ? {background: '#ddd'} : {}).attr('title', label + ': ' + duration(t.seconds)));
                    $legend.append(i ? ' · ' : '', $('<span/>').text(label + ' ' + Math.round(t.share) + '%'));
                });
                const since = page.since > Date.now() / 1000 - page.hours * 3600 + 120
                    ? ' ({{ lang._('history starts') }} ' + when(page.since) + ')' : '';
                $d.append($('<h4/>').text('{{ lang._('Time on each unit') }}' + since), $bar, $legend);

                const $t = $('<tbody/>');
                page.events.forEach(function (e) {
                    $t.append($('<tr/>').append($('<td style="width: 9em"/>').text(when(e.ts)), $('<td/>').html(moveText(e))));
                });
                $d.append($('<h4/>').text('{{ lang._('Moves') }}'), page.events.length
                    ? $('<table class="table table-condensed table-striped"/>').append($t)
                    : $('<p class="text-muted"/>').text('{{ lang._('No moves in this period.') }}'));
            });
        }
        function table(head, rows) {
            /* rows: arrays of HTML cells (already escaped) */
            const $t = $('<table class="table table-condensed table-striped" style="margin-bottom: 20px"/>');
            if (head) $t.append($('<thead/>').append($('<tr/>').append(head.map(h => $('<th/>').text(h)))));
            const $b = $('<tbody/>');
            rows.forEach(r => $b.append($('<tr/>').append(r.map(c => $('<td/>').html(c)))));
            return $t.append($b);
        }
        function showUnits() {
            $('#units_list').show();
            $('#unit_detail').hide();
            grid('grid_units', '/api/eero/report/search_units');
        }
        function showUnit(id) {
            $('#units_list').hide();
            $('#unit_detail').show();
            $('.eero-period button').removeClass('active').filter('[data-hours="' + hours + '"]').addClass('active');
            ajaxGet('/api/eero/report/unit/' + encodeURIComponent(id) + '/' + hours, {}, function (page) {
                const $d = $('#unit_detail_body').empty();
                if (!page || page.error || !page.unit) {
                    $d.text(page && page.error ? plain(page.error) : '{{ lang._('eero does not know this unit.') }}');
                    return;
                }
                const u = page.unit;
                $d.append($('<h3 style="margin-top: 0"/>').html(unitLabel(u, esc(u.name))),
                    $('<p class="text-muted"/>').text([plain(u.model), plain(u.ip)].filter(Boolean).join(' · ')));

                const reboot = Date.parse(plain(u.last_reboot));
                $d.append(table(null, [
                    ['{{ lang._('Backhaul') }}', esc(u.backhaul) + (u.mesh !== null ? ' &nbsp;' + formatters.bars({id: 'mesh'}, u) : '')],
                    ['{{ lang._('Up for') }}', formatters.uptime(null, u) + (isNaN(reboot) ? '' : ' <span class="text-muted">({{ lang._('since') }} ' + esc(new Date(reboot).toLocaleString()) + ')</span>')],
                    ['{{ lang._('Firmware') }}', esc(u.firmware) || dash],
                    ['{{ lang._('Power') }}', esc(u.power) || dash],
                    ['{{ lang._('Serial number') }}', esc(u.serial) || dash],
                    ['{{ lang._('MAC address') }}', esc(u.mac) || dash]
                ]).find('td:first-child').css('width', '30%').end());

                $d.append($('<h4/>').text('{{ lang._('Clients on this unit now') }} (' + page.clients.length + ')'));
                $d.append(page.clients.length
                    ? table(['{{ lang._('Name') }}', '{{ lang._('Band') }}', '{{ lang._('Signal') }}', '{{ lang._('Quality') }}', '{{ lang._('Type') }}'],
                        page.clients.map(c => [formatters.client(null, c), formatters.text({id: 'band'}, c), formatters.signal(null, c),
                            formatters.bars({id: 'quality'}, c), formatters.text({id: 'type'}, c)]))
                    : $('<p class="text-muted"/>').text('{{ lang._('No Wi-Fi clients.') }}'));

                if (page.radios.length) {
                    $d.append($('<h4/>').text('{{ lang._('Radios') }}'),
                        $('<p class="text-muted"/>').text('{{ lang._('Busy: how much of the time the channel is in use, by this unit, its clients and any other network on the same channel.') }}'),
                        table(['{{ lang._('Band') }}', '{{ lang._('Channel') }}', '{{ lang._('Width') }}', '{{ lang._('Busy') }}', '{{ lang._('Clients') }}', '{{ lang._('Transmit power') }}'],
                            page.radios.map(r => [esc(r.band), r.channel != null ? esc(r.channel) : dash, r.width ? esc(r.width) + ' MHz' : dash,
                                r.busy != null ? esc(r.busy) + ' %' : dash, r.clients != null ? esc(r.clients) : dash,
                                r.tx_power ? esc(r.tx_power) + ' dBm' : dash])));
                }
                if (page.ports.length) {
                    $d.append($('<h4/>').text('{{ lang._('Ports') }}'),
                        $('<p class="text-muted"/>').text('{{ lang._('Seen on the port: devices that announce themselves (LLDP) on the network behind it.') }}'),
                        table(['{{ lang._('Port') }}', '{{ lang._('Link') }}', '{{ lang._('Role') }}', '{{ lang._('Seen on the port') }}'],
                            page.ports.map(p => [esc(p.port),
                                p.link ? '<i class="fa fa-circle text-success"></i>&nbsp; ' + (esc(p.speed) || '{{ lang._('up') }}') : '<span class="text-muted">{{ lang._('no link') }}</span>',
                                p.uplink ? '{{ lang._('Uplink') }}' : dash,
                                p.neighbours.length ? p.neighbours.map(esc).join(', ') : dash])));
                }

                if (!page.history_since) {
                    $d.append($('<p class="text-muted"/>').text('{{ lang._('No history yet: it starts a minute after the first update from eero.') }}'));
                    return;
                }
                $d.append($('<h4/>').text('{{ lang._('Online and offline') }}'), page.events.length
                    ? table(null, page.events.map(e => [esc(when(e.ts)), e.event === 'offline'
                        ? '<span class="label label-danger">{{ lang._('Went offline') }}</span>' : '<span class="label label-success">{{ lang._('Back online') }}</span>']))
                        .find('td:first-child').css('width', '9em').end()
                    : $('<p class="text-muted"/>').text('{{ lang._('Online throughout this period.') }}'));
                $d.append($('<h4/>').text('{{ lang._('Client moves on and off this unit') }}'), page.moves.length
                    ? table(null, page.moves.map(e => [esc(when(e.ts)), formatters.client(null, e), moveText(e)]))
                        .find('td:first-child').css('width', '9em').end()
                    : $('<p class="text-muted"/>').text('{{ lang._('No moves in this period.') }}'));
            });
        }
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
            if (tab === '#units') unitView ? showUnit(unitView) : showUnits();
            else if (tab === '#clients') ({list: showClients, moves: showMoves, client: () => showClient(clientView.mac)})[clientView.view]();
            else if (tab === '#network') showNetwork();
        }
        $('#maintabs a[data-toggle="tab"]').on('shown.bs.tab', function (e) { load(e.target.hash); });
        show(window.location.hash);
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
        <div id="unit_detail" style="display: none; padding: 10px">
            <p><a href="#units">← {{ lang._('All units') }}</a></p>
            <div class="btn-group eero-period" style="margin-bottom: 15px">
                <button type="button" class="btn btn-default" data-hours="24">{{ lang._('1 day') }}</button>
                <button type="button" class="btn btn-default" data-hours="168">{{ lang._('7 days') }}</button>
                <button type="button" class="btn btn-default" data-hours="720">{{ lang._('30 days') }}</button>
            </div>
            <div id="unit_detail_body">{{ lang._('Loading…') }}</div>
        </div>
        <div id="units_list">
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
    </div>
    <div id="clients" class="tab-pane fade in">
        <div style="padding: 10px 10px 0" id="clients_bar">
            <div class="btn-group" id="clients_show">
                <button type="button" class="btn btn-default active" data-show="">{{ lang._('Connected now') }}</button>
                <button type="button" class="btn btn-default" data-show="all">{{ lang._('All known') }}</button>
                <button type="button" class="btn btn-default" data-show="moves">{{ lang._('Recent moves') }}</button>
            </div>
            <div class="btn-group eero-period" style="margin-left: 10px; display: none">
                <button type="button" class="btn btn-default" data-hours="24">{{ lang._('1 day') }}</button>
                <button type="button" class="btn btn-default" data-hours="168">{{ lang._('7 days') }}</button>
                <button type="button" class="btn btn-default" data-hours="720">{{ lang._('30 days') }}</button>
            </div>
        </div>
        <div id="clients_list">
        <table id="grid_clients" class="table table-condensed table-hover table-striped table-responsive">
            <thead><tr>
                <th data-column-id="mac" data-identifier="true" data-visible="false" data-formatter="text">{{ lang._('MAC address') }}</th>
                <th data-column-id="name" data-formatter="client">{{ lang._('Name') }}</th>
                <th data-column-id="unit" data-formatter="text">{{ lang._('Unit') }}</th>
                <th data-column-id="band" data-formatter="text" data-min-width="90" data-max-width="130">{{ lang._('Band') }}</th>
                <th data-column-id="signal" data-formatter="signal" data-min-width="80" data-max-width="110">{{ lang._('Signal') }}</th>
                <th data-column-id="quality" data-formatter="bars" data-min-width="60" data-max-width="80">{{ lang._('Quality') }}</th>
                <th data-column-id="ip" data-formatter="text" data-width="10em">{{ lang._('Address') }}</th>
                <th data-column-id="type" data-formatter="text">{{ lang._('Type') }}</th>
                <th data-column-id="maker" data-formatter="text" data-visible="false">{{ lang._('Maker') }}</th>
                <th data-column-id="last_seen" data-formatter="seen" data-width="9em">{{ lang._('Last seen') }}</th>
            </tr></thead>
            <tbody></tbody>
        </table>
        </div>
        <div id="clients_moves" style="display: none">
            <table id="grid_moves" class="table table-condensed table-hover table-striped table-responsive">
                <thead><tr>
                    <th data-column-id="id" data-identifier="true" data-visible="false">ID</th>
                    <th data-column-id="ts" data-formatter="when" data-width="10em">{{ lang._('When') }}</th>
                    <th data-column-id="name" data-formatter="client">{{ lang._('Client') }}</th>
                    <th data-column-id="to_unit" data-formatter="move" data-sortable="false">{{ lang._('Moved') }}</th>
                    <th data-column-id="band_to" data-formatter="bands" data-sortable="false" data-width="10em">{{ lang._('Band') }}</th>
                    <th data-column-id="type" data-formatter="text" data-visible="false">{{ lang._('Type') }}</th>
                </tr></thead>
                <tbody></tbody>
            </table>
        </div>
        <div id="client_detail" style="display: none; padding: 10px">
            <p><a href="#clients">← {{ lang._('All clients') }}</a></p>
            <div class="btn-group eero-period" style="margin-bottom: 15px">
                <button type="button" class="btn btn-default" data-hours="24">{{ lang._('1 day') }}</button>
                <button type="button" class="btn btn-default" data-hours="168">{{ lang._('7 days') }}</button>
                <button type="button" class="btn btn-default" data-hours="720">{{ lang._('30 days') }}</button>
            </div>
            <div id="client_detail_body">{{ lang._('Loading…') }}</div>
        </div>
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
