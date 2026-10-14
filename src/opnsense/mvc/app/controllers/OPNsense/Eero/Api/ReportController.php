<?php

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

namespace OPNsense\Eero\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;

/**
 * The Devices, Clients and Network tabs, from eerod's cache (configd `eero query`; never calls eero).
 */
class ReportController extends ApiControllerBase
{
    /* what each grid's search box matches: the columns it shows */
    private const SEARCH = [
        'units' => ['name', 'model', 'ip', 'backhaul', 'firmware'],
        'clients' => ['name', 'unit', 'band', 'ip', 'mac', 'type', 'maker'],
    ];

    private function query(array $args)
    {
        $data = json_decode((new Backend())->configdpRun('eero query', $args) ?? '', true);
        return is_array($data) ? $data : [];
    }

    public function searchUnitsAction()
    {
        return $this->searchRecordsetBase($this->query(['units']), self::SEARCH['units'], 'name');
    }

    /**
     * Loupe's name, type and icon for these clients, if os-loupe is installed (its `identities` query, contract
     * version 1; see os-loupe's README). Without Loupe the action doesn't exist and this returns [].
     */
    private function loupeIdentities(array $macs)
    {
        if (empty($macs)) {
            return [];
        }
        $data = json_decode((new Backend())->configdpRun('loupe query', ['identities', implode(',', $macs)]) ?? '', true);
        return (is_array($data) && ($data['version'] ?? null) === 1 && is_array($data['devices'] ?? null)) ? $data['devices'] : [];
    }

    public function searchClientsAction()
    {
        $all = $this->request->getPost('show', null, '') === 'all';
        $rows = $this->query($all ? ['clients', 'all'] : ['clients']);
        $known = $this->loupeIdentities(array_column($rows, 'mac'));
        foreach ($rows as &$row) {
            $id = $known[$row['mac']] ?? [];
            $row['icon'] = (string)($id['icon'] ?? '');
            if (!empty($id['type'])) {
                $row['type'] = (string)$id['type'];             // Loupe's type is more specific than eero's guess
            }
            if (empty($row['named']) && !empty($id['name'])) {
                $row['name'] = (string)$id['name'];             // a name set in the eero app wins; else Loupe's
            } elseif (!empty($row['vendor_name']) && !empty($id['type'])) {
                $row['name'] = (string)$id['type'];             // no name anywhere: "Ceiling fan", not the chip maker
            }
            if (!empty($id['vendor'])) {
                $row['maker'] = (string)$id['vendor'];          // Loupe's vendor ("Fanimation", not its Wi-Fi module)
            }
        }
        return $this->searchRecordsetBase($rows, self::SEARCH['clients'], 'name');
    }

    public function networkAction()
    {
        return $this->query(['network']);
    }
}
