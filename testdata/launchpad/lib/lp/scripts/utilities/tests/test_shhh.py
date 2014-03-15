# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from doctest import DocTestSuite
import os
import sys
import unittest


sys.path.insert(0, os.path.join(
    os.path.dirname(__file__),
    os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, 'utilities'))


def test_suite():
    return DocTestSuite('shhh')


if __name__ == '__main__':
    default = test_suite()
    unittest.main(defaultTest='default')
