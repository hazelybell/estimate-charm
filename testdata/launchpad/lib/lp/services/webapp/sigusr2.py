# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A SIGUSR2 handler for the Launchpad Web App.

Sending a SIGUSR2 signal to Launchpad will cause logfiles to be
reopened, allowing a tool like logrotate to rotate them.
"""

__metaclass__ = type
__all__ = ['setup_sigusr2']

import signal

from ZConfig.components.logger.loghandler import reopenFiles


def sigusr2_handler(signum, frame):
    "Rotate logfiles in response to SIGUSR2."""
    reopenFiles()

def setup_sigusr2(event):
    """Configure the SIGUSR2 handler. Called at startup."""
    signal.signal(signal.SIGUSR2, sigusr2_handler)
