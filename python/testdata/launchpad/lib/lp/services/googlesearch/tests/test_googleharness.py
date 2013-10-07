# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import doctest


def test_suite():
    return doctest.DocTestSuite(
            'lp.services.googlesearch.tests.googleserviceharness',
            optionflags=doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS)
