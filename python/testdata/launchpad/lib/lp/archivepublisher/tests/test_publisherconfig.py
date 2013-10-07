# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for publisherConfig model class."""

__metaclass__ = type


from storm.exceptions import IntegrityError
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.interfaces import Unauthorized

from lp.archivepublisher.interfaces.publisherconfig import (
    IPublisherConfig,
    IPublisherConfigSet,
    )
from lp.archivepublisher.model.publisherconfig import PublisherConfig
from lp.services.database.interfaces import IStore
from lp.testing import (
    ANONYMOUS,
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.sampledata import LAUNCHPAD_ADMIN


class TestPublisherConfig(TestCaseWithFactory):
    """Test the `PublisherConfig` model."""
    layer = ZopelessDatabaseLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.distribution = self.factory.makeDistribution(name='conftest')

    def test_verify_interface(self):
        # Test the interface for the model.
        pubconf = self.factory.makePublisherConfig()
        verified = verifyObject(IPublisherConfig, pubconf)
        self.assertTrue(verified)

    def test_properties(self):
        # Test the model properties.
        ROOT_DIR = u"rootdir/test"
        BASE_URL = u"http://base.url"
        COPY_BASE_URL = u"http://base.url"
        pubconf = self.factory.makePublisherConfig(
            distribution=self.distribution,
            root_dir=ROOT_DIR,
            base_url=BASE_URL,
            copy_base_url=COPY_BASE_URL,
            )

        self.assertEqual(self.distribution.name, pubconf.distribution.name)
        self.assertEqual(ROOT_DIR, pubconf.root_dir)
        self.assertEqual(BASE_URL, pubconf.base_url)
        self.assertEqual(COPY_BASE_URL, pubconf.copy_base_url)

    def test_one_config_per_distro(self):
        # Only one config for each distro is allowed.

        def make_conflicting_configs():
            for counter in range(2):
                self.factory.makePublisherConfig(self.distribution)
            IStore(PublisherConfig).flush()

        self.assertRaises(IntegrityError, make_conflicting_configs)

    def test_getByDistribution(self):
        # Test that IPublisherConfigSet.getByDistribution works.
        pubconf = getUtility(IPublisherConfigSet).getByDistribution(
            self.distribution)
        self.assertEqual(self.distribution.name, pubconf.distribution.name)


class TestPublisherConfigSecurity(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_only_admin(self):
        # Only admins can see and change the config.
        distro = self.factory.makeDistribution(publish_root_dir=u"foo")
        config = getUtility(IPublisherConfigSet).getByDistribution(distro)

        login(ANONYMOUS)
        self.assertRaises(Unauthorized, getattr, config, "root_dir")
        self.assertRaises(Unauthorized, setattr, config, "root_dir", "test")

        login(LAUNCHPAD_ADMIN)
        self.assertEqual(u"foo", config.root_dir)
        config.root_dir = u"bar"
        self.assertEqual(u"bar", config.root_dir)
