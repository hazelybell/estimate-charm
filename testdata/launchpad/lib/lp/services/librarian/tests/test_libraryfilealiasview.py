# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test LibraryFileAliasView."""

__metaclass__ = type

from zope.component import getMultiAdapter
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import GoneError
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadFunctionalLayer


class TestLibraryFileAliasView(TestCaseWithFactory):
    layer = LaunchpadFunctionalLayer

    def test_deleted_lfa(self):
        # When we initialise a LibraryFileAliasView against a deleted LFA,
        # we throw a 410 Gone error.
        lfa = self.factory.makeLibraryFileAlias()
        removeSecurityProxy(lfa).content = None
        self.assertTrue(lfa.deleted)
        request = LaunchpadTestRequest()
        view = getMultiAdapter((lfa, request), name='+index')
        self.assertRaisesWithContent(
            GoneError, "'File deleted.'", view.initialize)
