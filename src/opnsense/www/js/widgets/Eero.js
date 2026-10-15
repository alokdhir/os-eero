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
        return {sizeToContent: 300, w: 2, minW: 2};
    }

    getMarkup() {
        return $(`
            <div class="eero-widget" style="padding: 0 10px 10px; text-align: left">
                <style>
                    .eero-widget, .eero-widget * { text-align: left; }
                    .eero-widget .ew-status { margin-top: 5px; font-size: 12px; }
                    .eero-widget .ew-counts { display: flex; gap: 24px; margin: 8px 0 2px; }
                    .eero-widget .ew-num { font-size: 22px; line-height: 1.1; }
                    .eero-widget .ew-label { color: #888; font-size: 11px; }
                </style>
                <div class="ew-status" id="eero-w-status"></div>
                <div class="ew-counts" id="eero-w-counts"></div>
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
            case 'ok':
                return dot('text-success') + `${t.connected} <strong>${Eero.esc(d.network)}</strong>`;
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
        if (!this.dataChanged('eero', d)) {
            return;
        }
        $('#eero-w-status').html(this.status(d));
        const t = this.translations;
        if (!d.units) {
            $('#eero-w-counts').text(t.nodata);
            return;
        }
        const count = (num, label, cls) => `<div><div class="ew-num${cls ? ' ' + cls : ''}">${num}</div>`
            + `<div class="ew-label">${label}</div></div>`;
        $('#eero-w-counts').html(
            count(`${Eero.esc(d.online)} <span class="ew-label">${t.of} ${Eero.esc(d.units)}</span>`, t.unitsonline,
                  d.online < d.units ? 'text-danger' : '')
            + count(Eero.esc(d.clients), t.clients));
    }
}
