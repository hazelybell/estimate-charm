# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests.
"""

import os

from lp.services.testing import build_doctest_suite


here = os.path.dirname(os.path.realpath(__file__))


def test_suite():
    return build_doctest_suite(here, '')
