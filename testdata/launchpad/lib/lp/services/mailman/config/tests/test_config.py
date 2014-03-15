# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from doctest import (
    DocTestSuite,
    ELLIPSIS,
    NORMALIZE_WHITESPACE,
    )


def test_suite():
    suite = DocTestSuite(
            'lp.services.mailman.config',
            optionflags=NORMALIZE_WHITESPACE | ELLIPSIS)
    return suite
