# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import signal

from meliae import scanner


SIGDUMPMEM = signal.SIGRTMIN + 10
DUMP_FILE = '/tmp/launchpad-memory.dump'


def sigdumpmem_handler(signum, frame):
    scanner.dump_all_objects(DUMP_FILE)


def setup_sigdumpmem(event):
    signal.signal(SIGDUMPMEM, sigdumpmem_handler)
