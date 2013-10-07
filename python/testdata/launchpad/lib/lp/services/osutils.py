# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utilities for doing the sort of thing the os module does."""

__metaclass__ = type
__all__ = [
    'ensure_directory_exists',
    'get_pid_from_file',
    'kill_by_pidfile',
    'get_pid_from_file',
    'open_for_writing',
    'override_environ',
    'remove_if_exists',
    'remove_tree',
    'two_stage_kill',
    'write_file',
    ]

from contextlib import contextmanager
import errno
import os.path
import shutil
from signal import (
    SIGKILL,
    SIGTERM,
    )
import time


def remove_tree(path):
    """Remove the tree at 'path' from disk."""
    if os.path.exists(path):
        shutil.rmtree(path)


def set_environ(new_values):
    """Set the environment variables as specified by new_values.

    :return: a dict of the old values
    """
    old_values = {}
    for name, value in new_values.iteritems():
        old_values[name] = os.environ.get(name)
        if value is None:
            if old_values[name] is not None:
                del os.environ[name]
        else:
            os.environ[name] = value
    return old_values


@contextmanager
def override_environ(**kwargs):
    """Override environment variables with the kwarg values.

    If a value is None, the environment variable is deleted.  Variables are
    restored to their previous state when exiting the context.
    """
    old_values = set_environ(kwargs)
    try:
        yield
    finally:
        set_environ(old_values)


def ensure_directory_exists(directory, mode=0777):
    """Create 'directory' if it doesn't exist.

    :return: True if the directory had to be created, False otherwise.
    """
    try:
        os.makedirs(directory, mode=mode)
    except OSError as e:
        if e.errno == errno.EEXIST:
            return False
        raise
    return True


def open_for_writing(filename, mode, dirmode=0777):
    """Open 'filename' for writing, creating directories if necessary.

    :param filename: The path of the file to open.
    :param mode: The mode to open the filename with. Should be 'w', 'a' or
        something similar. See ``open`` for more details. If you pass in
        a read-only mode (e.g. 'r'), then we'll just accept that and return
        a read-only file-like object.
    :param dirmode: The mode to use to create directories, if necessary.
    :return: A file-like object that can be used to write to 'filename'.
    """
    try:
        return open(filename, mode)
    except IOError as e:
        if e.errno == errno.ENOENT:
            os.makedirs(os.path.dirname(filename), mode=dirmode)
            return open(filename, mode)


def _kill_may_race(pid, signal_number):
    """Kill a pid accepting that it may not exist."""
    try:
        os.kill(pid, signal_number)
    except OSError as e:
        if e.errno in (errno.ESRCH, errno.ECHILD):
            # Process has already been killed.
            return
        # Some other issue (e.g. different user owns it)
        raise


def two_stage_kill(pid, poll_interval=0.1, num_polls=50):
    """Kill process 'pid' with SIGTERM. If it doesn't die, SIGKILL it.

    :param pid: The pid of the process to kill.
    :param poll_interval: The polling interval used to check if the
        process is still around.
    :param num_polls: The number of polls to do before doing a SIGKILL.
    """
    # Kill the process.
    _kill_may_race(pid, SIGTERM)

    # Poll until the process has ended.
    for i in range(num_polls):
        try:
            # Reap the child process and get its return value. If it's not
            # gone yet, continue.
            new_pid, result = os.waitpid(pid, os.WNOHANG)
            if new_pid:
                return result
            time.sleep(poll_interval)
        except OSError as e:
            if e.errno in (errno.ESRCH, errno.ECHILD):
                # Raised if the process is gone by the time we try to get the
                # return value.
                return

    # The process is still around, so terminate it violently.
    _kill_may_race(pid, SIGKILL)


def get_pid_from_file(pidfile_path):
    """Retrieve the PID from the given file, if it exists, None otherwise."""
    if not os.path.exists(pidfile_path):
        return None
    # Get the pid.
    pid = open(pidfile_path, 'r').read().split()[0]
    try:
        pid = int(pid)
    except ValueError:
        # pidfile contains rubbish
        return None
    return pid


def kill_by_pidfile(pidfile_path, poll_interval=0.1, num_polls=50):
    """Kill a process identified by the pid stored in a file.

    The pid file is removed from disk.
    """
    try:
        pid = get_pid_from_file(pidfile_path)
        if pid is None:
            return
        two_stage_kill(pid, poll_interval, num_polls)
    finally:
        remove_if_exists(pidfile_path)


def remove_if_exists(path):
    """Remove the given file if it exists."""
    try:
        os.remove(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def write_file(path, content):
    with open_for_writing(path, 'w') as f:
        f.write(content)
