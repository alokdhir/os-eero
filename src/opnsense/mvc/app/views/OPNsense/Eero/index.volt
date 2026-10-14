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
    });
</script>

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
    </div>
</div>

<div class="eero-apply" style="display: none">
    {{ partial('layout_partials/base_apply_button', {'data_endpoint': '/api/eero/service/reconfigure', 'data_service_widget': 'eero', 'data_error_title': 'Error applying eero settings'}) }}
</div>
