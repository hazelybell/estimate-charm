# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper for test_sigusr2.py."""

import logging
import os.path
import signal
import sys

from ZConfig.components.logger.loghandler import FileHandler

from lp.services.webapp.sigusr2 import setup_sigusr2


def notify(step):
    # Quick way of communicating back to the test suite for synchronization.
    open(os.path.join(os.path.dirname(sys.argv[1]), step), 'w').write('')


_counter = 1

def sigusr1_handler(signum, frame):
    """Emit a message"""
    global _counter
    logging.getLogger('').error('Message %d' % _counter)
    notify('emit_%d' % _counter)
    _counter += 1


_installed_handler = None

def sigusr2_handler(signum, frame):
    _installed_handler(signum, frame)
    notify('sigusr2')

if __name__ == '__main__':
    logging.getLogger('').addHandler(FileHandler(sys.argv[1]))
    signal.signal(signal.SIGUSR1, sigusr1_handler)

    # Install the SIGUSR2 handler, and wrap it so there are notifications
    # when it is invoked.
    setup_sigusr2(None)
    _installed_handler = signal.signal(signal.SIGUSR2, sigusr2_handler)

    notify('ready')
    while True:
        signal.pause()
