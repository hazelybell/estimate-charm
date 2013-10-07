# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import hashlib

from lazr.restfulclient.errors import (
    BadRequest,
    Unauthorized,
    )
from zope.security.management import endInteraction

from lp.testing import (
    launchpadlib_for,
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.layers import LaunchpadFunctionalLayer


class TestDistroArchSeriesWebservice(TestCaseWithFactory):
    """Unit Tests for 'DistroArchSeries' Webservice.
    """
    layer = LaunchpadFunctionalLayer

    def _makeDistroArchSeries(self):
        """Create a `DistroSeries` object, that is prefilled with 1
        architecture for testing purposes.

        :return: a `DistroSeries` object.
        """
        distro = self.factory.makeDistribution()
        distroseries = self.factory.makeDistroSeries(
            distribution=distro)
        self.factory.makeDistroArchSeries(
            distroseries=distroseries)

        return distroseries

    def test_distroseries_architectures_anonymous(self):
        """Test anonymous DistroArchSeries API Access."""
        distroseries = self._makeDistroArchSeries()
        endInteraction()
        launchpad = launchpadlib_for('test', person=None, version='devel')
        ws_distroseries = ws_object(launchpad, distroseries)
        # Note, we test the length of architectures.entries, not
        # architectures due to the removal of the entries by lazr
        self.assertEqual(1, len(ws_distroseries.architectures.entries))

    def test_distroseries_architectures_authenticated(self):
        """Test authenticated DistroArchSeries API Access."""
        distroseries = self._makeDistroArchSeries()
        #Create a user to use the authenticated API
        accessor = self.factory.makePerson()
        launchpad = launchpadlib_for('test', accessor.name, version='devel')
        ws_distroseries = ws_object(launchpad, distroseries)
        #See note above regarding testing of length of .entries
        self.assertEqual(1, len(ws_distroseries.architectures.entries))

    def test_setChroot_removeChroot_random_user(self):
        # Random users are not allowed to set or remove chroots.
        das = self.factory.makeDistroArchSeries()
        user = self.factory.makePerson()
        webservice = launchpadlib_for("testing", user, version='devel')
        ws_das = ws_object(webservice, das)
        self.assertRaises(
            Unauthorized, ws_das.setChroot, data='xyz', sha1sum='0')
        self.assertRaises(Unauthorized, ws_das.removeChroot)

    def test_setChroot_wrong_sha1sum(self):
        # If the sha1sum calculated is different, the chroot is not set.
        das = self.factory.makeDistroArchSeries()
        user = das.distroseries.distribution.main_archive.owner
        webservice = launchpadlib_for("testing", user)
        ws_das = ws_object(webservice, das)
        self.assertRaises(
            BadRequest, ws_das.setChroot, data='zyx', sha1sum='x')

    def test_setChroot_removeChroot(self):
        das = self.factory.makeDistroArchSeries()
        user = das.distroseries.distribution.main_archive.owner
        expected_file = 'chroot-%s-%s-%s.tar.bz2' % (
            das.distroseries.distribution.name, das.distroseries.name,
            das.architecturetag)
        webservice = launchpadlib_for("testing", user)
        ws_das = ws_object(webservice, das)
        sha1 = hashlib.sha1('abcxyz').hexdigest()
        ws_das.setChroot(data='abcxyz', sha1sum=sha1)
        self.assertTrue(ws_das.chroot_url.endswith(expected_file))
        ws_das.removeChroot()
        self.assertIsNone(ws_das.chroot_url)
