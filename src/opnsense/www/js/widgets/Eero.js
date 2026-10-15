/*
 * Copyright (C) 2026 Alok K. Dhir
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 * OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

export default class Eero extends BaseWidget {
    constructor() {
        super();
        this.tickTimeout = 30;
    }

    getGridOptions() {
        return {sizeToContent: 650, w: 2, minW: 2};
    }

    getMarkup() {
        return $(`
            <div class="eero-widget" style="padding: 0 10px 10px; text-align: left">
                <style>
                    .eero-widget, .eero-widget * { text-align: left; }
                    .eero-widget .ew-status { margin-top: 5px; font-size: 12px; }
                    .eero-widget .ew-sum { margin: 4px 0 6px; font-size: 12px; }
                    .eero-widget .ew-row { display: flex; gap: 8px; padding: 3px 0; border-top: 1px solid rgba(128,128,128,0.2); font-size: 12px; }
                    .eero-widget .ew-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                    .eero-widget .ew-val, .eero-widget .ew-val * { white-space: nowrap; text-align: right; }
                    .eero-widget .ew-muted { color: #888; }
                </style>
                <div class="ew-status" id="eero-w-status"></div>
                <div class="ew-sum" id="eero-w-sum"></div>
                <div id="eero-w-units"></div>
            </div>
        `);
    }

    // API answers arrive HTML-escaped by core (& as &amp;): decode once, then escape (quotes too: attributes)
    static esc(s) {
        const plain = s == null ? '' : String(s).includes('&') ? $('<textarea/>').html(String(s)).text() : String(s);
        return plain.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
    }

    status(d) {
        const t = this.translations;
        const dot = cls => `<i class="fa fa-circle ${cls}"></i>&nbsp; `;
        if (!d.running) return dot('text-muted') + `<a href="/ui/eero/#settings">${t.stopped}</a>`;
        switch (d.status) {
            case 'ok': {
                const s = Math.max(0, Math.round(Date.now() / 1000 - (d.last_ok || 0)));
                return dot('text-success') + `${t.connected} <strong>${Eero.esc(d.network)}</strong> · ${t.updated} `
                    + (s < 90 ? s + ' s' : Math.round(s / 60) + ' min') + ` ${t.ago}`;
            }
            case 'starting':
                return dot('text-info') + Eero.esc(d.network || '');
            case 'needs_login':
                return dot('text-warning') + `<a href="/ui/eero/#settings">${t.signin}</a>`;
            case 'rate_limited':
                return dot('text-warning') + t.limited;
            default:
                return dot('text-danger') + Eero.esc(d.message || t.unreachable);
        }
    }

    async onWidgetTick() {
        const d = await this.ajaxCall('/api/eero/report/widget');
        if (!d || d.error) {
            $('#eero-w-status').text(this.translations.nodata);
            return;
        }
        $('#eero-w-status').html(this.status(d));          // its "updated … ago" changes every tick
        if (!this.dataChanged('eero', {units: d.units, clients: d.clients})) {
            return;
        }
        const t = this.translations;
        const units = d.units || [];
        if (!units.length) {
            $('#eero-w-sum').text(t.nodata);
            $('#eero-w-units').empty();
            return;
        }
        const online = units.filter(u => u.online).length;
        $('#eero-w-sum').html(`<strong${online < units.length ? ' class="text-danger"' : ''}>${online} ${t.of} ${units.length}</strong> `
            + `${t.unitsonline} · <strong>${Eero.esc(d.clients)}</strong> ${t.clients}`);
        $('#eero-w-units').html(units.map(u => `<div class="ew-row"><div class="ew-name">`
            + `<a href="/ui/eero/#unit=${encodeURIComponent(Eero.esc(u.id))}">${Eero.esc(u.name)}</a>`
            + (u.primary ? ` <span class="ew-muted">(${t.primary})</span>` : '')
            + (u.online ? '' : ` <span class="label label-danger">${t.offline}</span>`)
            + `</div><div class="ew-val">${u.clients == null ? '' : Eero.esc(u.clients)}</div></div>`).join(''));
    }
}
