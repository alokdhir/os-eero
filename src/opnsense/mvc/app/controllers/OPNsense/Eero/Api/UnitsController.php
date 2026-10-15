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
 * Changes to eero units: the only changes the plugin makes to eero. Each has a privilege of its own (ACL
 * page-eero-units for renaming, page-eero-reboot for rebooting), so users who may only look at the page can't
 * change anything. The GUI user is passed on, and units.py logs who asked for what.
 */
class UnitsController extends ApiControllerBase
{
    public function renameAction()
    {
        if (!$this->request->isPost()) {
            return ['result' => 'failed'];
        }
        $id = (string)$this->request->getPost('id', null, '');
        $name = trim((string)$this->request->getPost('name', null, ''));
        if (!preg_match('/^[0-9A-Za-z_-]{1,40}$/', $id)) {
            return ['result' => 'failed', 'message' => gettext('Unknown unit.')];
        }
        if ($name === '' || mb_strlen($name) > 40) {
            return ['result' => 'failed', 'message' => gettext('Enter a name of 1 to 40 characters.')];
        }
        return $this->run('eero rename', [$id, $name, $this->getUserName()]);
    }

    /** Reboot one unit (id) or every unit (id "all"). */
    public function rebootAction()
    {
        if (!$this->request->isPost()) {
            return ['result' => 'failed'];
        }
        $id = (string)$this->request->getPost('id', null, '');
        if ($id !== 'all' && !preg_match('/^[0-9A-Za-z_-]{1,40}$/', $id)) {
            return ['result' => 'failed', 'message' => gettext('Unknown unit.')];
        }
        return $this->run('eero reboot', [$id, $this->getUserName()]);
    }

    private function run($action, array $params)
    {
        $result = json_decode(trim((new Backend())->configdpRun($action, $params)), true);
        return is_array($result) ? $result : ['result' => 'failed', 'message' => gettext('No answer from the eero service.')];
    }
}
