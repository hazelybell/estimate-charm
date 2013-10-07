# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite
import unittest


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(DocTestSuite('lp.services.database.sort_sql'))
    return suite
