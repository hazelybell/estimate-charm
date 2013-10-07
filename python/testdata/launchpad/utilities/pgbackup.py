#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Backup one or more PostgreSQL databases.

Suitable for use in crontab for daily backups.
"""

__metaclass__ = type
__all__ = []

from datetime import datetime
import logging
from optparse import OptionParser
import os
import os.path
import stat
import subprocess
import sys


MB = float(1024*1024)

return_code = 0 # Return code of this script. Set to the most recent failed
                # system call's return code

def call(cmd, **kw):
    log.debug(' '.join(cmd))
    rv = subprocess.call(cmd, **kw)
    if rv != 0:
        global return_code
        return_code = rv
    return rv

def main(options, databases):
    global return_code
    #Need longer file names if this is used more than daily
    #today = datetime.now().strftime('%Y%m%d_%H:%M:%S')
    today = datetime.now().strftime('%Y%m%d')

    backup_dir = options.backup_dir

    # Check for existing files now. Also check later just in case
    # there are two copies of this script running or something crazy.
    # Better to bomb out now rather than to bomb out later, as later might
    # be several hours away.
    for database in databases:
        dest =  os.path.join(backup_dir, '%s.%s.dump' % (database, today))
        if os.path.exists(dest):
            log.fatal("%s already exists." % dest)
            return 1
 
    exit_code = 0
    for database in databases:
        dest =  os.path.join(backup_dir, '%s.%s.dump' % (database, today))

        if os.path.exists(dest):
            log.fatal("%s already exists." % dest)
            return 1

        cmd = [
            "/usr/bin/pg_dump",
            "-U", "postgres",
            "--format=c",
            "--compress=9",
            "--blobs",
            "--file=%s" % dest,
            database,
            ]

        rv = call(cmd, stdin=subprocess.PIPE) # Sets return_code on failure.
        if rv != 0:
            log.critical("Failed to backup %s (%d)" % (database, rv))
            continue
        size = os.stat(dest)[stat.ST_SIZE]

        log.info("Backed up %s (%0.2fMB)" % (database, size/MB))

    return return_code

if __name__ == '__main__':
    parser = OptionParser(
            usage="usage: %prog [options] database [database ..]"
            )
    parser.add_option("-v", "--verbose", dest="verbose", default=0,
            action="count")
    parser.add_option("-q", "--quiet", dest="quiet", default=0,
            action="count")
    parser.add_option("-d", "--dir", dest="backup_dir",
            default="/var/lib/postgres/backups")
    (options, databases) = parser.parse_args()
    if len(databases) == 0:
        parser.error("must specify at least one database")
    if not os.path.isdir(options.backup_dir):
        parser.error(
                "Incorrect --dir. %s does not exist or is not a directory" % (
                    options.backup_dir
                    )
                )

    # Setup our log
    log = logging.getLogger('pgbackup')
    hdlr = logging.StreamHandler(strm=sys.stderr)
    hdlr.setFormatter(logging.Formatter(
            fmt='%(asctime)s %(levelname)s %(message)s'
            ))
    log.addHandler(hdlr)
    verbosity = options.verbose - options.quiet
    if verbosity > 0:
        log.setLevel(logging.DEBUG)
    elif verbosity == 0: # Default
        log.setLevel(logging.INFO)
    elif verbosity == -1:
        log.setLevel(logging.WARN)
    elif verbosity < -1:
        log.setLevel(logging.ERROR)

    sys.exit(main(options, databases))
