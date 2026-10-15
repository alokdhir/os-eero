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
 * The eero account: status, and the two-step sign-in (email or phone, then the code eero sends).
 * Everything goes through configd to scripts that run as root; the browser never talks to eero.
 */
class AccountController extends ApiControllerBase
{
    private function run($action, $params = [])
    {
        $out = trim((new Backend())->configdpRun($action, $params) ?? '');
        $result = json_decode($out, true);
        return is_array($result) ? $result : ['result' => 'failed', 'message' => gettext('No answer from the eero service.')];
    }

    /** What the status line shows (from eerod's cache; never calls eero). */
    public function statusAction()
    {
        return $this->run('eero query', ['status']);
    }

    public function signinAction()
    {
        if (!$this->request->isPost()) {
            return ['result' => 'failed'];
        }
        $who = trim((string)$this->request->getPost('identifier', null, ''));
        if ($who === '' || strlen($who) > 254) {
            return ['result' => 'failed', 'message' => gettext('Enter the email address or phone number of your eero account.')];
        }
        return $this->run('eero signin', [$who]);
    }

    public function verifyAction()
    {
        if (!$this->request->isPost()) {
            return ['result' => 'failed'];
        }
        $code = preg_replace('/\s+/', '', (string)$this->request->getPost('code', null, ''));
        if (!preg_match('/^[0-9]{4,8}$/', $code)) {
            return ['result' => 'failed', 'message' => gettext('Enter the code from eero\'s email or text message.')];
        }
        return $this->run('eero verify', [$code]);
    }

    public function signoutAction()
    {
        if (!$this->request->isPost()) {
            return ['result' => 'failed'];
        }
        return $this->run('eero signout');
    }
}
