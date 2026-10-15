# Copyright (C) 2026 Alok K. Dhir
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
# OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import os
import tempfile
import unittest

import helpers  # noqa: F401
from lib import config


class TestConfig(unittest.TestCase):
    def days(self, text):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "eero.json")
            if text is not None:
                with open(path, "w") as f:
                    f.write(text)
            return config.history_days(path)

    def test_history_days(self):
        self.assertEqual(self.days('{"history_days": 14}'), 14)
        self.assertEqual(self.days('{"history_days": 500}'), 90)        # clamped
        self.assertEqual(self.days('{"history_days": 0}'), 1)
        for text in (None, "", "not json", "[]", '{"history_days": "x"}'):
            self.assertEqual(self.days(text), config.HISTORY_DAYS, text)


if __name__ == "__main__":
    unittest.main()
