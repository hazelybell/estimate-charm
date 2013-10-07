# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import doctest
from doctest import (
    ELLIPSIS,
    NORMALIZE_WHITESPACE,
    REPORT_NDIFF,
    )
import unittest

from lp.services.database import sqlbase


def test_suite():
    optionflags = ELLIPSIS|NORMALIZE_WHITESPACE|REPORT_NDIFF
    dt_suite = doctest.DocTestSuite(sqlbase, optionflags=optionflags)
    return unittest.TestSuite((dt_suite,))

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(test_suite())
