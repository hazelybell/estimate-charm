# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Run the doc string tests."""

import doctest
from doctest import (
    NORMALIZE_WHITESPACE,
    ELLIPSIS,
    )

from lp import testing
from lp.testing.layers import BaseLayer
from lp.testing.systemdocs import LayeredDocFileSuite


def test_suite():
    suite = LayeredDocFileSuite(
        [],
        layer=BaseLayer)
    suite.addTest(doctest.DocTestSuite(
        testing, optionflags=NORMALIZE_WHITESPACE|ELLIPSIS))
    return suite
