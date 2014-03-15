#! /usr/bin/python -S
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Perform simple librarian operations to verify the current configuration.
"""

import _pythonpath

import sys

from zope.component import getUtility

from lp.services.librarian.interfaces.client import (
    ILibrarianClient,
    IRestrictedLibrarianClient,
    )
from lp.services.librarian.smoketest import do_smoketest
from lp.services.scripts import execute_zcml_for_scripts


if __name__ == '__main__':
    execute_zcml_for_scripts()
    restricted_client = getUtility(IRestrictedLibrarianClient)
    regular_client = getUtility(ILibrarianClient)
    sys.exit(do_smoketest(restricted_client, regular_client))
