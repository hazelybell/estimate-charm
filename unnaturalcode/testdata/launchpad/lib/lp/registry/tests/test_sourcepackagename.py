# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for SourcePackageName"""

__metaclass__ = type

from testtools.testcase import ExpectedException

from lp.registry.errors import InvalidName
from lp.registry.model.sourcepackagename import SourcePackageNameSet
from lp.testing import TestCase
from lp.testing.layers import DatabaseLayer


class TestSourcePackageNameSet(TestCase):

    layer = DatabaseLayer

    def test_invalid_name(self):
        with ExpectedException(
            InvalidName,
            'invalid%20name is not a valid name for a source package.'):
            SourcePackageNameSet().new('invalid%20name')
