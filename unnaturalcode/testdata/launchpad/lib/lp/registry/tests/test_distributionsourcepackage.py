# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for DistributionSourcePackage."""

__metaclass__ = type

from storm.store import Store
from testtools.matchers import Equals
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.model.distributionsourcepackage import (
    DistributionSourcePackage,
    DistributionSourcePackageInDatabase,
    )
from lp.registry.model.karma import KarmaTotalCache
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import flush_database_updates
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.matchers import HasQueryCount


class TestDistributionSourcePackage(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_dsp_with_no_series_summary(self):
        distribution_set = getUtility(IDistributionSet)

        distribution = distribution_set.new(name='wart',
            displayname='wart', title='wart', description='lots of warts',
            summary='lots of warts', domainname='wart.dumb',
            members=self.factory.makeTeam(), owner=self.factory.makePerson(),
            registrant=self.factory.makePerson())
        naked_distribution = removeSecurityProxy(distribution)
        self.factory.makeSourcePackage(distroseries=distribution)
        dsp = naked_distribution.getSourcePackage(name='pmount')
        self.assertEqual(None, dsp.summary)

    def test_binary_names_built(self):
        # The list contains the names of the built binaries.
        bpph = self.factory.makeBinaryPackagePublishingHistory()
        distribution = bpph.distroarchseries.distroseries.distribution
        spn = bpph.binarypackagerelease.build.source_package_release.name
        dsp = distribution.getSourcePackage(spn)
        self.assertEqual([bpph.binarypackagerelease.name], dsp.binary_names)

    def test_binary_names_unbuilt(self):
        # The list is empty where there are no built binaries.
        dsp = self.factory.makeDistributionSourcePackage(with_db=True)
        self.assertEqual([], dsp.binary_names)

    def test_ensure_spph_creates_a_dsp_in_db(self):
        # The DSP.ensure() class method creates a persistent instance
        # if one does not exist.
        spph = self.factory.makeSourcePackagePublishingHistory()
        spph_dsp = spph.sourcepackagerelease.distrosourcepackage
        DistributionSourcePackage.ensure(spph)
        new_dsp = DistributionSourcePackage._get(
            spph_dsp.distribution, spph_dsp.sourcepackagename)
        self.assertIsNot(None, new_dsp)
        self.assertIsNot(spph_dsp, new_dsp)
        self.assertEqual(spph_dsp.distribution, new_dsp.distribution)
        self.assertEqual(
            spph_dsp.sourcepackagename, new_dsp.sourcepackagename)

    def test_ensure_spph_dsp_in_db_exists(self):
        # The DSP.ensure() class method does not create duplicate
        # persistent instances; it skips the query to create the DSP.
        store = IStore(DistributionSourcePackageInDatabase)
        start_count = store.find(DistributionSourcePackageInDatabase).count()
        spph = self.factory.makeSourcePackagePublishingHistory()
        DistributionSourcePackage.ensure(spph)
        new_count = store.find(DistributionSourcePackageInDatabase).count()
        self.assertEqual(start_count + 1, new_count)
        final_count = store.find(DistributionSourcePackageInDatabase).count()
        self.assertEqual(new_count, final_count)

    def test_ensure_spph_does_not_create_dsp_in_db_non_primary_archive(self):
        # The DSP.ensure() class method creates a persistent instance
        # if one does not exist.
        archive = self.factory.makeArchive()
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=archive)
        spph_dsp = spph.sourcepackagerelease.distrosourcepackage
        DistributionSourcePackage.ensure(spph)
        new_dsp = DistributionSourcePackage._get(
            spph_dsp.distribution, spph_dsp.sourcepackagename)
        self.assertIs(None, new_dsp)

    def test_ensure_suitesourcepackage_creates_a_dsp_in_db(self):
        # The DSP.ensure() class method creates a persistent instance
        # if one does not exist.
        sourcepackage = self.factory.makeSourcePackage()
        DistributionSourcePackage.ensure(sourcepackage=sourcepackage)
        new_dsp = DistributionSourcePackage._get(
            sourcepackage.distribution, sourcepackage.sourcepackagename)
        self.assertIsNot(None, new_dsp)
        self.assertEqual(sourcepackage.distribution, new_dsp.distribution)
        self.assertEqual(
            sourcepackage.sourcepackagename, new_dsp.sourcepackagename)

    def test_delete_without_dsp_in_db(self):
        # Calling delete() on a DSP without persistence returns False.
        dsp = self.factory.makeDistributionSourcePackage()
        self.assertFalse(dsp.delete())

    def test_delete_with_dsp_in_db_with_history(self):
        # Calling delete() on a persistent DSP with SPPH returns False.
        # Once a package is uploaded, it cannot be deleted.
        spph = self.factory.makeSourcePackagePublishingHistory()
        dsp = spph.sourcepackagerelease.distrosourcepackage
        DistributionSourcePackage.ensure(spph=spph)
        transaction.commit()
        self.assertFalse(dsp.delete())

    def test_delete_with_dsp_in_db_without_history(self):
        # Calling delete() on a persistent DSP without SPPH returns True.
        # A package without history was a mistake.
        sp = self.factory.makeSourcePackage()
        DistributionSourcePackage.ensure(sourcepackage=sp)
        transaction.commit()
        dsp = sp.distribution_sourcepackage
        self.assertTrue(dsp.delete())

    def test_is_official_with_db_true(self):
        # A DSP is official when it is represented in the database.
        dsp = self.factory.makeDistributionSourcePackage(with_db=True)
        self.assertTrue(dsp.is_official)

    def test_is_official_without_db_false(self):
        # A DSP is not official if it is virtual.
        dsp = self.factory.makeDistributionSourcePackage(with_db=False)
        self.assertFalse(dsp.is_official)

    def test_drivers_are_distributions(self):
        # DSP.drivers returns the drivers for the distribution.
        distribution = self.factory.makeDistribution()
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=distribution)
        self.assertNotEqual([], distribution.drivers)
        self.assertEqual(dsp.drivers, distribution.drivers)

    def test_personHasDriverRights(self):
        # A distribution driver has driver permissions on a DSP.
        distribution = self.factory.makeDistribution()
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=distribution)
        driver = distribution.drivers[0]
        self.assertTrue(dsp.personHasDriverRights(driver))


class TestDistributionSourcePackageFindRelatedArchives(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Publish some gedit sources in main and PPAs."""
        super(TestDistributionSourcePackageFindRelatedArchives, self).setUp()

        self.distribution = getUtility(IDistributionSet)['ubuntutest']

        # Create two PPAs for gedit.
        self.archives = {}
        self.archives['ubuntu-main'] = self.distribution.main_archive
        self.archives['gedit-nightly'] = self.factory.makeArchive(
            name="gedit-nightly", distribution=self.distribution)
        self.archives['gedit-beta'] = self.factory.makeArchive(
            name="gedit-beta", distribution=self.distribution)

        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        # Publish gedit in all three archives.
        self.person_nightly = self.factory.makePerson()
        self.gedit_nightly_src_hist = self.publisher.getPubSource(
            sourcename="gedit", archive=self.archives['gedit-nightly'],
            creator=self.person_nightly,
            status=PackagePublishingStatus.PUBLISHED)

        self.person_beta = self.factory.makePerson()
        self.gedit_beta_src_hist = self.publisher.getPubSource(
            sourcename="gedit", archive=self.archives['gedit-beta'],
            creator=self.person_beta,
            status=PackagePublishingStatus.PUBLISHED)
        self.gedit_main_src_hist = self.publisher.getPubSource(
            sourcename="gedit", archive=self.archives['ubuntu-main'],
            status=PackagePublishingStatus.PUBLISHED)

        # Save the gedit source package for easy access.
        self.source_package = self.distribution.getSourcePackage('gedit')

        # Add slightly more soyuz karma for person_nightly for this package.
        switch_dbuser('karma')
        self.person_beta_karma = KarmaTotalCache(
            person=self.person_beta, karma_total=200)
        self.person_nightly_karma = KarmaTotalCache(
            person=self.person_nightly, karma_total=201)
        switch_dbuser('launchpad')

    def test_order_by_soyuz_package_karma(self):
        # Returned archives are ordered by the soyuz karma of the
        # package uploaders for the particular package

        related_archives = self.source_package.findRelatedArchives()
        related_archive_names = [
            archive.name for archive in related_archives]

        self.assertEqual(related_archive_names, [
            'gedit-nightly',
            'gedit-beta',
            ])

        # Update the soyuz karma for person_beta for this package so that
        # it is greater than person_nightly's.
        switch_dbuser('karma')
        self.person_beta_karma.karma_total = 202
        switch_dbuser('launchpad')

        related_archives = self.source_package.findRelatedArchives()
        related_archive_names = [
            archive.name for archive in related_archives]

        self.assertEqual(related_archive_names, [
            'gedit-beta',
            'gedit-nightly',
            ])

    def test_require_package_karma(self):
        # Only archives where the related package was created by a person
        # with the required soyuz karma for this package.

        related_archives = self.source_package.findRelatedArchives(
            required_karma=201)
        related_archive_names = [
            archive.name for archive in related_archives]

        self.assertEqual(related_archive_names, ['gedit-nightly'])

    def test_development_version(self):
        # IDistributionSourcePackage.development_version is the ISourcePackage
        # for the current series of the distribution.
        dsp = self.factory.makeDistributionSourcePackage()
        series = self.factory.makeDistroSeries(distribution=dsp.distribution)
        self.assertEqual(series, dsp.distribution.currentseries)
        development_version = dsp.distribution.currentseries.getSourcePackage(
            dsp.sourcepackagename)
        self.assertEqual(development_version, dsp.development_version)

    def test_development_version_no_current_series(self):
        # IDistributionSourcePackage.development_version is the ISourcePackage
        # for the current series of the distribution.
        dsp = self.factory.makeDistributionSourcePackage()
        currentseries = dsp.distribution.currentseries
        # The current series is None by default.
        self.assertIs(None, currentseries)
        self.assertEqual(None, dsp.development_version)

    def test_does_not_include_copied_packages(self):
        # Packages that have been copied rather than uploaded are not
        # included when determining related archives.

        # Ensure that the gedit package in gedit-nightly was originally
        # uploaded to gedit-beta (ie. copied from there).
        gedit_release = self.gedit_nightly_src_hist.sourcepackagerelease
        gedit_release.upload_archive = self.archives['gedit-beta']

        related_archives = self.source_package.findRelatedArchives()
        related_archive_names = [
            archive.name for archive in related_archives]

        self.assertEqual(related_archive_names, ['gedit-beta'])


class TestDistributionSourcePackageInDatabase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_mapping_cache_cleared_on_abort(self):
        # DistributionSourcePackageInDatabase._cache is cleared when a
        # transaction is aborted.
        DistributionSourcePackageInDatabase._cache["Frank"] = "Sinatra"
        transaction.abort()
        self.assertEqual(
            {}, DistributionSourcePackageInDatabase._cache.items())

    def test_mapping_cache_cleared_on_commit(self):
        # DistributionSourcePackageInDatabase._cache is cleared when a
        # transaction is committed.
        DistributionSourcePackageInDatabase._cache["Frank"] = "Sinatra"
        transaction.commit()
        self.assertEqual(
            {}, DistributionSourcePackageInDatabase._cache.items())

    def test_new(self):
        # DistributionSourcePackageInDatabase.new() creates a new DSP, adds it
        # to the store, and updates the mapping cache.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        dsp = DistributionSourcePackageInDatabase.new(
            distribution, sourcepackagename)
        self.assertIs(Store.of(distribution), Store.of(dsp))
        self.assertEqual(
            {(distribution.id, sourcepackagename.id): dsp.id},
            DistributionSourcePackageInDatabase._cache.items())

    def test_getDirect_not_found(self):
        # DistributionSourcePackageInDatabase.getDirect() returns None if a
        # DSP does not exist in the database. It does not modify the mapping
        # cache.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp = DistributionSourcePackageInDatabase.getDirect(
                distribution, sourcepackagename)
            self.assertIs(None, dsp)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        self.assertEqual(
            {}, DistributionSourcePackageInDatabase._cache.items())

    def test_getDirect_found(self):
        # DistributionSourcePackageInDatabase.getDirect() returns the
        # DSPInDatabase if one already exists in the database. It also adds
        # the new mapping to the mapping cache.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        dsp = DistributionSourcePackageInDatabase.new(
            distribution, sourcepackagename)
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp_found = DistributionSourcePackageInDatabase.getDirect(
                dsp.distribution, dsp.sourcepackagename)
            self.assertIs(dsp, dsp_found)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        self.assertEqual(
            {(distribution.id, sourcepackagename.id): dsp.id},
            DistributionSourcePackageInDatabase._cache.items())

    def test_get_not_cached_and_not_found(self):
        # DistributionSourcePackageInDatabase.get() returns None if a DSP does
        # not exist in the database and no mapping cache entry exists for
        # it. It does not modify the mapping cache.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp = DistributionSourcePackageInDatabase.get(
                distribution, sourcepackagename)
            self.assertIs(None, dsp)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        self.assertEqual(
            {}, DistributionSourcePackageInDatabase._cache.items())

    def test_get_cached_and_not_found(self):
        # DistributionSourcePackageInDatabase.get() returns None if a DSP does
        # not exist in the database for a stale mapping cache entry.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        # Enter a stale entry in the mapping cache.
        stale_dsp_cache_key = distribution.id, sourcepackagename.id
        DistributionSourcePackageInDatabase._cache[stale_dsp_cache_key] = -123
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp = DistributionSourcePackageInDatabase.get(
                distribution, sourcepackagename)
            self.assertIs(None, dsp)
        # A stale mapping means that we have to issue two queries: the first
        # queries for the stale DSP from the database, the second gets the
        # correct DSP (or None).
        self.assertThat(recorder, HasQueryCount(Equals(2)))

    def test_get_cached_and_not_found_with_bogus_dsp(self):
        # DistributionSourcePackageInDatabase.get() returns None if a DSP does
        # exist in the database for a mapping cache entry, but the DSP
        # discovered does not match the mapping cache key.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        # Put a bogus entry into the mapping cache.
        bogus_dsp = DistributionSourcePackageInDatabase.new(
            distribution, self.factory.makeSourcePackageName())
        bogus_dsp_cache_key = distribution.id, sourcepackagename.id
        DistributionSourcePackageInDatabase._cache[
            bogus_dsp_cache_key] = bogus_dsp.id
        # Invalidate the bogus DSP from Storm's cache.
        Store.of(bogus_dsp).invalidate(bogus_dsp)
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp = DistributionSourcePackageInDatabase.get(
                distribution, sourcepackagename)
            self.assertIs(None, dsp)
        # A stale mapping means that we have to issue two queries: the first
        # gets the bogus DSP from the database, the second gets the correct
        # DSP (or None).
        self.assertThat(recorder, HasQueryCount(Equals(2)))

    def test_get_cached_and_not_found_with_bogus_dsp_in_storm_cache(self):
        # DistributionSourcePackageInDatabase.get() returns None if a DSP does
        # exist in the database for a mapping cache entry, but the DSP
        # discovered does not match the mapping cache key.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        # Put a bogus entry into the mapping cache.
        bogus_dsp = DistributionSourcePackageInDatabase.new(
            distribution, self.factory.makeSourcePackageName())
        bogus_dsp_cache_key = distribution.id, sourcepackagename.id
        DistributionSourcePackageInDatabase._cache[
            bogus_dsp_cache_key] = bogus_dsp.id
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp = DistributionSourcePackageInDatabase.get(
                distribution, sourcepackagename)
            self.assertIs(None, dsp)
        # A stale mapping means that we ordinarily have to issue two queries:
        # the first gets the bogus DSP from the database, the second gets the
        # correct DSP (or None). However, the bogus DSP is already in Storm's
        # cache, so we issue only one query.
        self.assertThat(recorder, HasQueryCount(Equals(1)))

    def test_get_not_cached_and_found(self):
        # DistributionSourcePackageInDatabase.get() returns the DSP if it's
        # found in the database even if no mapping cache entry exists for
        # it. It updates the mapping cache with this discovered information.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        dsp = DistributionSourcePackageInDatabase.new(
            distribution, sourcepackagename)
        # new() updates the mapping cache so we must clear it.
        DistributionSourcePackageInDatabase._cache.clear()
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp_found = DistributionSourcePackageInDatabase.get(
                distribution, sourcepackagename)
            self.assertIs(dsp, dsp_found)
        self.assertThat(recorder, HasQueryCount(Equals(1)))
        self.assertEqual(
            {(distribution.id, sourcepackagename.id): dsp.id},
            DistributionSourcePackageInDatabase._cache.items())

    def test_get_cached_and_found(self):
        # DistributionSourcePackageInDatabase.get() returns the DSP if it's
        # found in the database from a good mapping cache entry.
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        dsp = DistributionSourcePackageInDatabase.new(
            distribution, sourcepackagename)
        flush_database_updates()
        with StormStatementRecorder() as recorder:
            dsp_found = DistributionSourcePackageInDatabase.get(
                distribution, sourcepackagename)
            self.assertIs(dsp, dsp_found)
        # Hurrah! This is what we're aiming for: a DSP that is in the mapping
        # cache *and* in Storm's cache.
        self.assertThat(recorder, HasQueryCount(Equals(0)))
