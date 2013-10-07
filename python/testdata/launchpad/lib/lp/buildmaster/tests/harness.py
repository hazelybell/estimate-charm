# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""TacHandler for `buildd-manager` daemon."""

__metaclass__ = type

__all__ = [
    'BuilddManagerTestSetup',
    ]


import os

from lp.services.daemons.tachandler import TacTestSetup
from lp.services.osutils import remove_tree


class BuilddManagerTestSetup(TacTestSetup):
    """Setup BuilddManager for use by functional tests."""

    logfilecontent = None

    def precreateLogfile(self, content, repeat=1):
        """Precreate a logfile in the root.

        :param content: A string to use as the content of the file.
        :param repeat: The number of times to repeat the string in the file.
            This is meant to be used to easily create larger files.
        """
        self.logfilecontent = content * repeat

    def setUpRoot(self):
        """Create `TacTestSetup.root` for storing the log and pid files.

        Remove the directory and create a new one if it exists.
        """
        remove_tree(self.root)
        os.makedirs(self.root)
        if self.logfilecontent is not None:
            open(self.logfile, "w").write(self.logfilecontent)

    @property
    def root(self):
        """Directory where log and pid files will be stored."""
        return '/var/tmp/buildd-manager/'

    @property
    def tacfile(self):
        """Absolute path to the 'buildd-manager' tac file."""
        return os.path.join(self.daemon_directory, 'buildd-manager.tac')

    @property
    def pidfile(self):
        """The tac pid file path.

        Will be created when the tac file actually runs.
        """
        return os.path.join(self.root, 'buildd-manager.pid')

    @property
    def logfile(self):
        """The tac log file path.

        Will be created when the tac file actually runs.
        """
        return os.path.join(self.root, 'buildd-manager.log')
