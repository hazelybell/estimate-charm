#! /usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run a command and suppress output unless it returns a non-zero exit status
"""

__metaclass__ = type

from subprocess import (
    PIPE,
    Popen,
    )
import sys


def shhh(cmd):
    r"""Run a command and suppress output unless it returns a non-zero exitcode

    If output is generated, stderr will be output before stdout, so output
    order may be messed up if the command attempts to control order by
    flushing stdout at points or setting it to unbuffered.


    To test, we invoke both this method and this script with some commands
    and examine the output and exitvalue

    >>> python = sys.executable

    >>> def shhh_script(cmd):
    ...     from subprocess import Popen, PIPE
    ...     script = '%s %s' % (python, __file__)
    ...     cmd = "%s '%s'" % (script, cmd)
    ...     p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    ...     (out, err) = p.communicate()
    ...     return (out, err, p.returncode)

    >>> cmd = '''%s -c "import sys; sys.exit(%d)"''' % (python, 0)
    >>> shhh(cmd)
    0
    >>> shhh_script(cmd)
    ('', '', 0)

    >>> cmd = '''%s -c "import sys; sys.exit(%d)"''' % (python, 1)
    >>> shhh(cmd)
    1
    >>> shhh_script(cmd)
    ('', '', 1)

    >>> cmd = '''%s -c "import sys; print 666; sys.exit(%d)"''' % (
    ...     python, 42)
    >>> shhh(cmd)
    666
    42
    >>> shhh_script(cmd)
    ('666\n', '', 42)

    >>> cmd = (
    ...     '''%s -c "import sys; print 666; '''
    ...     '''print >> sys.stderr, 667; sys.exit(42)"''' % python
    ...     )
    >>> shhh_script(cmd)
    ('666\n', '667\n', 42)
    """

    process = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
    (out, err) = process.communicate()
    if process.returncode == 0:
        return 0
    else:
        sys.stderr.write(err)
        sys.stdout.write(out)
        return process.returncode


if __name__ == '__main__':
    cmd = ' '.join(sys.argv[1:])
    sys.exit(shhh(cmd))

