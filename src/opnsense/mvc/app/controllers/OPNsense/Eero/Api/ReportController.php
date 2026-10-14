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
        'moves' => ['name', 'from_unit', 'to_unit', 'type'],
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

    /** Loupe's icon, type, name (where eero has none) and vendor on client rows, in place. */
    private function decorate(array &$rows)
    {
        $known = $this->loupeIdentities(array_values(array_unique(array_column($rows, 'mac'))));
        foreach ($rows as &$row) {
            $id = $known[$row['mac']] ?? [];
            $row['icon'] = (string)($id['icon'] ?? '');
            if (!empty($id['type'])) {
                $row['type'] = (string)$id['type'];             // Loupe's type is more specific than eero's guess
            }
            /* names, best first: set in the eero app; the device's own (eero's host name); Loupe's; Loupe's type.
               Loupe's name only replaces eero's when eero has nothing but the Wi-Fi chip maker. */
            if (empty($row['named']) && !empty($row['vendor_name'])) {
                if (!empty($id['name'])) {
                    $row['name'] = (string)$id['name'];
                } elseif (!empty($id['type'])) {
                    $row['name'] = (string)$id['type'];         // "Ceiling fan (fanSync)", not the chip maker
                }
            }
            if (!empty($id['vendor'])) {
                $row['maker'] = (string)$id['vendor'];          // Loupe's vendor ("Fanimation", not its Wi-Fi module)
            }
        }
    }

    private function hours($hours)
    {
        $hours = (float)$hours;
        return ($hours >= 1 && $hours <= 720) ? (string)$hours : '24';
    }

    public function searchClientsAction()
    {
        $all = $this->request->getPost('show', null, '') === 'all';
        $rows = $this->query($all ? ['clients', 'all'] : ['clients']);
        $this->decorate($rows);
        return $this->searchRecordsetBase($rows, self::SEARCH['clients'], 'name');
    }

    /** One client's page: now, time on each eero, its moves. */
    public function clientAction($mac = '', $hours = 24)
    {
        $mac = strtolower(rawurldecode($mac));
        if (!preg_match('/^[0-9a-f]{2}(:[0-9a-f]{2}){5}$/', $mac)) {
            return ['error' => 'invalid MAC address'];
        }
        $page = $this->query(['client', $mac, $this->hours($hours)]);
        if (!empty($page['client'])) {
            $rows = [$page['client']];
            $this->decorate($rows);
            $page['client'] = $rows[0];
        }
        return $page;
    }

    /** Recent moves across all clients, named and iconed like the Clients grid. */
    public function searchMovesAction()
    {
        $events = $this->query(['moves', $this->hours($this->request->getPost('hours', null, 24))]);
        $current = [];
        foreach ($this->query(['clients', 'all']) as $c) {
            $current[$c['mac']] = $c;
        }
        $rows = [];
        foreach ($events as $i => $e) {
            $c = $current[$e['mac']] ?? [];
            $rows[] = $e + ['id' => $i, 'named' => $c['named'] ?? false, 'vendor_name' => $c['vendor_name'] ?? false,
                            'type' => $c['type'] ?? '', 'maker' => $c['maker'] ?? '',
                            'name' => $c['name'] ?? ($e['name'] ?? $e['mac'])];
        }
        $this->decorate($rows);
        return $this->searchRecordsetBase($rows, self::SEARCH['moves'], 'ts', null, SORT_NUMERIC);
    }

    public function networkAction()
    {
        return $this->query(['network']);
    }
}
