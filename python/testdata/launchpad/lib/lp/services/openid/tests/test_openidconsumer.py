# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the `IOpenIDConsumerStore` utility."""

__metaclass__ = type

from zope.component import getUtility

from lp.services.openid.interfaces.openidconsumer import IOpenIDConsumerStore
from lp.services.openid.tests.test_baseopenidstore import (
    BaseStormOpenIDStoreTestsMixin,
    )
from lp.testing import TestCase
from lp.testing.layers import DatabaseFunctionalLayer


class OpenIDConsumerStoreTests(BaseStormOpenIDStoreTestsMixin, TestCase):
    """Tests for the `IOpenIDConsumerStore` utility."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(OpenIDConsumerStoreTests, self).setUp()
        self.store = getUtility(IOpenIDConsumerStore)
