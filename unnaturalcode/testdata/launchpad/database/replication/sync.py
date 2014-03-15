#!/usr/bin/python -S
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Block until the replication cluster synchronizes."""

__metaclass__ = type
__all__ = []

import _pythonpath

from optparse import OptionParser

from lp.services.scripts import (
    db_options,
    logger_options,
    )
from replication.helpers import sync


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option(
        "-t", "--timeout", dest="timeout", metavar="SECS", type="int",
        help="Abort if no sync after SECS seconds.", default=0)
    logger_options(parser)
    db_options(parser)
    options, args = parser.parse_args()
    sync(options.timeout)
