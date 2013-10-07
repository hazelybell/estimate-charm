# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import unittest

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.person import IPersonSet
from lp.services.webapp.authentication import IPlacelessLoginSource
from lp.services.webapp.interfaces import AccessLevel
from lp.testing import (
    ANONYMOUS,
    login,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class LaunchpadLoginSourceTest(unittest.TestCase):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        login(ANONYMOUS)
        self.login_source = getUtility(IPlacelessLoginSource)
        self.mark = getUtility(IPersonSet).getByName('mark')

    def test_default_access_level(self):
        """By default, if getPrincipal() and getPrincipalByLogin() are given
        no access level, the returned principal will have full access.
        """
        principal = self.login_source.getPrincipal(self.mark.account.id)
        self.assertEqual(principal.access_level, AccessLevel.WRITE_PRIVATE)
        marks_email = removeSecurityProxy(self.mark).preferredemail.email
        principal = self.login_source.getPrincipalByLogin(marks_email)
        self.assertEqual(principal.access_level, AccessLevel.WRITE_PRIVATE)

    def test_given_access_level_is_used(self):
        """If an access level argument is given to getPrincipalByLogin() or
        getPrincipal(), the returned principal will use that.
        """
        principal = self.login_source.getPrincipal(
            self.mark.account.id, access_level=AccessLevel.WRITE_PUBLIC)
        self.assertEqual(principal.access_level, AccessLevel.WRITE_PUBLIC)
        principal = self.login_source.getPrincipalByLogin(
            removeSecurityProxy(self.mark).preferredemail.email, AccessLevel.READ_PUBLIC)
        self.assertEqual(principal.access_level, AccessLevel.READ_PUBLIC)
