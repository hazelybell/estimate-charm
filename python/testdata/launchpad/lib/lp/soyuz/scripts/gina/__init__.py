# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import signal
from subprocess import (
    PIPE,
    Popen,
    STDOUT,
    )

from lp.services.scripts import log


class ExecutionError(Exception):
    """The command executed in a cal() returned a non-zero status"""

def subprocess_setup():
    # Python installs a SIGPIPE handler by default. This is usually not what
    # non-Python subprocesses expect.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

def call(cmd):
    """Run a command, raising a RuntimeError if the command failed"""
    log.debug("Running %s" % cmd)
    p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT,
              preexec_fn=subprocess_setup)
    out, err = p.communicate()
    for line in out.splitlines():
        log.debug("> %s" % line)
    if p.returncode != 0:
        raise ExecutionError("Error %d running %s" % (p.returncode, cmd))
    return p.returncode

