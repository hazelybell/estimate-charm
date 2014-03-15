# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import os.path
import subprocess
import unittest

from lp.app.versioninfo import revno
from lp.services.config import TREE_ROOT


class TestVersionInfo(unittest.TestCase):

    def test_out_of_tree_versioninfo_access(self):
        # Our cronscripts are executed with cwd != LP root.
        # Getting version info should still work in them.
        args = [os.path.join(TREE_ROOT, "bin/py"), "-c",
                "from lp.app.versioninfo import revno;"
                "print revno"]
        process = subprocess.Popen(args, cwd='/tmp', stdout=subprocess.PIPE)
        (output, errors) = process.communicate(None)
        self.assertEquals(int(revno), int(output))
