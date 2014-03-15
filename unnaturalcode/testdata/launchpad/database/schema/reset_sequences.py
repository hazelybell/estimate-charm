#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
The sampledata does not update the current values of all the sequences
used to populate the primary keys (this was removed to aid in merging changes
to the sampledata).

This script resets all of these sequences to the correct value based on the
maximum value currently found in the corresponding table.
"""

__metaclass__ = type

import _pythonpath

from optparse import OptionParser

from lp.services.database.postgresql import resetSequences
from lp.services.database.sqlbase import connect
from lp.services.scripts import db_options


if __name__ == '__main__':
    parser = OptionParser()
    db_options(parser)
    (options, args) = parser.parse_args()
    if args:
        parser.error("Too many options given")
    if not options.dbname:
        parser.error("Required option --dbname not given")
    con = connect()
    resetSequences(con.cursor())
    con.commit()
