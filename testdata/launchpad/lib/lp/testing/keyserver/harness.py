# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import os
import shutil

from lp.services.config import config
from lp.services.daemons.tachandler import TacTestSetup


KEYS_DIR = os.path.join(os.path.dirname(__file__), 'tests/keys')


class KeyServerTac(TacTestSetup):
    """A test key server for use by functional tests."""

    def setUpRoot(self):
        """Recreate root directory and copy needed keys"""
        if os.path.isdir(self.root):
            shutil.rmtree(self.root)
        shutil.copytree(KEYS_DIR, self.root)

    @property
    def root(self):
        return config.testkeyserver.root

    @property
    def tacfile(self):
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'testkeyserver.tac'))

    @property
    def pidfile(self):
        return os.path.join(self.root, 'testkeyserver.pid')

    @property
    def logfile(self):
        return os.path.join(self.root, 'testkeyserver.log')


    @property
    def url(self):
        """The URL that the web server will be running on."""
        return 'http://%s:%d' % (
            config.gpghandler.host, config.gpghandler.port)
