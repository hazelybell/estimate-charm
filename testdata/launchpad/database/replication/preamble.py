#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generate a preamble for slonik(1) scripts based on the current LPCONFIG.
"""

__metaclass__ = type
__all__ = []

import _pythonpath

from optparse import OptionParser
import time

from lp.services import scripts
from lp.services.config import config
from lp.services.database.sqlbase import connect
import replication.helpers


if __name__ == '__main__':
    parser = OptionParser()
    scripts.db_options(parser)
    (options, args) = parser.parse_args()
    if args:
        parser.error("Too many arguments")
    scripts.execute_zcml_for_scripts(use_web_security=False)

    con = connect()
    print '# slonik(1) preamble generated %s' % time.ctime()
    print '# LPCONFIG=%s' % config.instance_name
    print
    print replication.helpers.preamble(con)
