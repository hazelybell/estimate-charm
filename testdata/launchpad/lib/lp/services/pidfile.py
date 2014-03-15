# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import atexit
import os
from signal import (
    signal,
    SIGTERM,
    )
import sys
import tempfile

from lp.services.config import config


def pidfile_path(service_name, use_config=None):
    """Return the full pidfile path for the given service
    """
    if use_config is None:
        use_config = config
    return os.path.join(use_config.canonical.pid_dir, '%s-%s.pid' % (
        use_config.instance_name, service_name
        ))


def make_pidfile(service_name):
    """Write the current process id to a PID file.

    Also installs an atexit handler to remove the file on process termination.

    Also installs a SIGTERM signal handler to remove the file on SIGTERM.
    If you install your own handler, you will want to call remove_pidfile
    inside it.
    """
    pidfile = pidfile_path(service_name)
    if os.path.exists(pidfile):
        raise RuntimeError("PID file %s already exists. Already running?" %
                pidfile)

    atexit.register(remove_pidfile, service_name)
    def remove_pidfile_handler(*ignored):
        sys.exit(-1 * SIGTERM)
    signal(SIGTERM, remove_pidfile_handler)

    fd, tempname = tempfile.mkstemp(dir=os.path.dirname(pidfile))
    outf = os.fdopen(fd, 'w')
    outf.write(str(os.getpid())+'\n')
    outf.flush()
    outf.close()
    os.rename(tempname, pidfile)


def remove_pidfile(service_name, use_config=None):
    """Remove the PID file.

    This should only be needed if you are overriding the default SIGTERM
    signal handler.
    """
    pidfile = pidfile_path(service_name, use_config)
    pid = get_pid(service_name, use_config)
    if pid is None:
        return
    if use_config is not None or pid == os.getpid():
        os.unlink(pidfile)


def get_pid(service_name, use_config=None):
    """Return the PID for the given service as an integer, or None

    May raise a ValueError if the PID file is corrupt.

    This method will only be needed by service or monitoring scripts.

    Currently no checking is done to ensure that the process is actually
    running, is healthy, or died horribly a while ago and its PID being
    used by something else. What we have is probably good enough.
    """
    pidfile = pidfile_path(service_name, use_config)
    try:
        pid = open(pidfile).read()
        return int(pid)
    except IOError:
        return None
    except ValueError:
        raise ValueError("Invalid PID %s" % repr(pid))
