# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test initializing a distroseries using
IDistroSeries.initDerivedDistroSeries."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.distroseries import DerivationError
from lp.soyuz.interfaces.distributionjob import (
    IInitializeDistroSeriesJobSource,
    )
from lp.soyuz.scripts.tests.test_initialize_distroseries import (
    InitializationHelperTestCase,
    )
from lp.testing import (
    ANONYMOUS,
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestDeriveDistroSeries(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestDeriveDistroSeries, self).setUp()
        self.parent = self.factory.makeDistroSeries()
        arch = self.factory.makeDistroArchSeries(distroseries=self.parent)
        removeSecurityProxy(self.parent).nominatedarchindep = arch
        self.child = self.factory.makeDistroSeries()
        removeSecurityProxy(self.child).driver = self.factory.makePerson()
        login_person(self.child.driver)

    def test_no_permission_to_call(self):
        login(ANONYMOUS)
        self.assertRaises(
            Unauthorized, getattr, self.child, "initDerivedDistroSeries")

    def test_parent_is_not_set(self):
        # When the series already has a parent series, it means that the
        # distroseries has already been derived, and it is forbidden to
        # derive more than once.
        self.factory.makeDistroSeriesParent(
            derived_series=self.child, parent_series=self.parent)
        self.assertRaisesWithContent(
            DerivationError,
            ("DistroSeries {self.child.name} already has parent "
             "series.".format(self=self)),
            self.child.initDerivedDistroSeries, self.child.driver,
            [self.parent.id])

    def test_init_creates_new_job(self):
        self.child.initDerivedDistroSeries(
            self.child.driver, [self.parent.id])
        [job] = list(
            getUtility(IInitializeDistroSeriesJobSource).iterReady())
        self.assertEqual(job.distroseries, self.child)


class TestDeriveDistroSeriesMultipleParents(InitializationHelperTestCase):

    layer = LaunchpadZopelessLayer

    def setUpParents(self, packages1, packages2):
        parent1, unused = self.setupParent(packages=packages1)
        parent2, unused = self.setupParent(packages=packages2)
        return parent1, parent2

    def assertBinPackagesAndVersions(self, series, pack_versions):
        # Helper to assert that series contains the required binaries
        # pack_version should be of the form [(packagname1, version1), ...]
        # e.g. [(u'p1', u'0.1-1'), (u'p2', u'2.1')])
        pub_sources = series.main_archive.getPublishedSources(
            distroseries=series)
        binaries = sorted(
            [(p.getBuiltBinaries()[0].binarypackagerelease.sourcepackagename,
              p.getBuiltBinaries()[0].binarypackagerelease.version)
                 for p in pub_sources])

        self.assertEquals(pack_versions, binaries)

    def test_multiple_parents_binary_packages(self):
        # An initialization from many parents (using the package copier)
        # can happen using the same the db user the job will use
        # ('initializedistroseries').
        parent1, parent2 = self.setUpParents(
            packages1={'p1': '0.1-1'}, packages2={'p2': '2.1'})
        child = self.factory.makeDistroSeries()
        switch_dbuser('initializedistroseries')

        child = self._fullInitialize(
            [parent1, parent2], child=child)
        self.assertBinPackagesAndVersions(
            child,
            [(u'p1', u'0.1-1'), (u'p2', u'2.1')])

    def test_multiple_parents_do_not_close_bugs(self):
        # The initialization does not close the bugs on the copied
        # publications (and thus does not try to access the bug table).
        parent1, parent2 = self.setUpParents(
            packages1={'p1': '0.1-1'}, packages2={'p2': '2.1'})
        child = self.factory.makeDistroSeries()
        switch_dbuser('initializedistroseries')

        # Patch close_bugs_for_sourcepublication to be able to record if
        # the method has been called.
        fakeCloseBugs = FakeMethod()
        from lp.soyuz.scripts import packagecopier as packagecopier_module
        self.patch(
            packagecopier_module,
            'close_bugs_for_sourcepublication',
            fakeCloseBugs)

        child = self._fullInitialize(
            [parent1, parent2], child=child)
        # Make sure the initialization was successful.
        self.assertBinPackagesAndVersions(
            child,
            [(u'p1', u'0.1-1'), (u'p2', u'2.1')])
        # Assert that close_bugs_for_sourcepublication has not been
        # called.
        self.assertEqual(
            0,
            fakeCloseBugs.call_count)
        # Switch back to launchpad_main to be able to cleanup the
        # feature flags.
        switch_dbuser('launchpad_main')

    def test_packageset_check_performed(self):
        # Packagesets passed to initDerivedDistroSeries are passed down
        # to InitializeDistroSeries to check for any pending builds.
        parent, parent_das = self.setupParent()
        # Create packageset p1 with a build.
        p1, packageset1, unsed = self.createPackageInPackageset(
            parent, u'p1', u'packageset1', True)
        # Create packageset p2 without a build.
        p2, packageset2, unsed = self.createPackageInPackageset(
            parent, u'p2', u'packageset2', False)
        child = self.factory.makeDistroSeries(
            distribution=parent.distribution, previous_series=parent)

        # Packageset p2 has no build so no exception should be raised.
        child.initDerivedDistroSeries(
            child.driver, [parent.id], (), None, (str(packageset2.id),))

    def test_arch_check_performed(self):
        # Architectures passed to initDerivedDistroSeries are passed down
        # to InitializeDistroSeries to check for any pending builds.
        res = self.create2archParentAndSource(packages={'p1': '1.1'})
        parent, parent_das, parent_das2, source = res
        # Create builds for the architecture of parent_das2.
        source.createMissingBuilds(architectures_available=[parent_das])
        child = self.factory.makeDistroSeries(
            distribution=parent.distribution, previous_series=parent)

        # Initialize only with parent_das2's architecture. The build is
        # in the other architecture so no exception should be raised.
        child.initDerivedDistroSeries(
            child.driver, [parent.id], (parent_das2.architecturetag, ))
