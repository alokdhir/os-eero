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

namespace OPNsense\Eero;

class IndexController extends \OPNsense\Base\IndexController
{
    /**
     * One page with tabs: Units, Clients, Overview, Settings, under Reporting > Eero.
     */
    public function indexAction()
    {
        $this->view->formSettings = $this->getForm('settings');
        /* period buttons: 1 day, 7 days, 30 days, as far as the "Keep history" setting goes, and that setting itself */
        $keep = max(1, min(90, (int)(string)(new \OPNsense\Eero\Eero())->general->history_days));
        $periods = array_values(array_unique(array_merge(array_filter([1, 7, 30], fn($d) => $d < $keep), [$keep])));
        $this->view->periods = $periods;
        /* the rename pencil, the reboot buttons and the Settings tab only for users with those privileges */
        $acl = new \OPNsense\Core\ACL();
        $this->view->canRename = $acl->isPageAccessible($this->getUserName(), '/api/eero/units/rename');
        $this->view->canReboot = $acl->isPageAccessible($this->getUserName(), '/api/eero/units/reboot');
        $this->view->canSettings = $acl->isPageAccessible($this->getUserName(), '/api/eero/settings/set');
        $this->view->pick('OPNsense/Eero/index');
    }
}
