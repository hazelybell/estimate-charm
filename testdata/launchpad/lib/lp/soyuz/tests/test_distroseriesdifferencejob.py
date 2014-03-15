# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `DistroSeriesDifferenceJob` and utility."""

__metaclass__ = type

from psycopg2 import ProgrammingError
from testtools.matchers import MatchesStructure
import transaction
from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.proxy import removeSecurityProxy

from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.distroseriesdifference import DistroSeriesDifference
from lp.services.database import bulk
from lp.services.database.interfaces import IMasterStore
from lp.services.features.testing import FeatureFixture
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.tests import block_on_job
from lp.services.scripts.tests import run_script
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.distributionjob import (
    DistributionJobType,
    IDistroSeriesDifferenceJobSource,
    )
from lp.soyuz.model.distributionjob import DistributionJob
from lp.soyuz.model.distroseriesdifferencejob import (
    create_job,
    create_multiple_jobs,
    DistroSeriesDifferenceJob,
    find_waiting_jobs,
    make_metadata,
    may_require_job,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    CeleryJobLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


def find_dsd_for(dsp, package):
    """Find `DistroSeriesDifference`.

    :param dsp: `DistroSeriesParent`.
    :param package: `SourcePackageName`.
    """
    store = IMasterStore(DistroSeriesDifference)
    return store.find(
        DistroSeriesDifference,
        DistroSeriesDifference.derived_series == dsp.derived_series,
        DistroSeriesDifference.parent_series == dsp.parent_series,
        DistroSeriesDifference.source_package_name == package)


class TestDistroSeriesDifferenceJobSource(TestCaseWithFactory):
    """Tests for `IDistroSeriesDifferenceJobSource`."""

    layer = ZopelessDatabaseLayer

    def getJobSource(self):
        return getUtility(IDistroSeriesDifferenceJobSource)

    def makeDerivedDistroSeries(self):
        dsp = self.factory.makeDistroSeriesParent()
        return dsp.derived_series

    def test_baseline(self):
        verifyObject(IDistroSeriesDifferenceJobSource, self.getJobSource())

    def test___repr__(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        jobs = self.getJobSource().createForPackagePublication(
            dsp.derived_series, package,
            PackagePublishingPocket.RELEASE)
        [job] = jobs
        self.assertEqual(
            ("<DistroSeriesDifferenceJob for package {package.name} "
             "from {parentseries.name} to "
             "{derivedseries.name}>").format(
                package=package,
                parentseries=dsp.parent_series,
                derivedseries=dsp.derived_series),
            repr(job))

    def test_make_metadata_is_consistent(self):
        package = self.factory.makeSourcePackageName()
        parent_series = self.factory.makeDistroSeries()
        self.assertEqual(
            make_metadata(package.id, parent_series.id),
            make_metadata(package.id, parent_series.id))

    def test_make_metadata_distinguishes_packages(self):
        parent_series = self.factory.makeDistroSeries()
        one_package = self.factory.makeSourcePackageName()
        another_package = self.factory.makeSourcePackageName()
        self.assertNotEqual(
            make_metadata(one_package.id, parent_series.id),
            make_metadata(another_package.id, parent_series.id))

    def test_make_metadata_distinguishes_parents(self):
        package = self.factory.makeSourcePackageName()
        one_parent = self.factory.makeDistroSeries()
        another_parent = self.factory.makeDistroSeries()
        self.assertNotEqual(
            make_metadata(package.id, one_parent.id),
            make_metadata(package.id, another_parent.id))

    def test_may_require_job_allows_new_jobs(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        self.assertTrue(may_require_job(
            dsp.derived_series, package, dsp.parent_series))

    def test_may_require_job_forbids_redundant_jobs(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertFalse(
            may_require_job(dsp.derived_series, package, dsp.parent_series))

    def test_may_require_job_forbids_jobs_for_intra_distro_derivation(self):
        package = self.factory.makeSourcePackageName()
        parent = self.factory.makeDistroSeries()
        child = self.factory.makeDistroSeries(
            distribution=parent.distribution, previous_series=parent)
        self.assertFalse(may_require_job(child, package, parent))

    def test_may_require_job_only_considers_waiting_jobs_for_redundancy(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        existing_job = create_job(
            dsp.derived_series, package, dsp.parent_series)
        existing_job.job.start()
        self.assertTrue(
            may_require_job(dsp.derived_series, package, dsp.parent_series))

    def test_create_job_creates_waiting_job(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        dsdjob = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertEqual(JobStatus.WAITING, dsdjob.job.status)

    def createSPPHs(self, derived_series, nb_spph=10):
        res_spph = []
        for i in xrange(nb_spph):
            packagename = self.factory.makeSourcePackageName()
            spph = self.factory.makeSourcePackagePublishingHistory(
                sourcepackagename=packagename,
                distroseries=derived_series,
                pocket=PackagePublishingPocket.RELEASE)
            res_spph.append(spph)
        transaction.commit()
        return res_spph

    def test_create_multiple_jobs_structure(self):
        dsp = self.factory.makeDistroSeriesParent()
        spph = self.createSPPHs(dsp.derived_series, 1)[0]
        job_ids = create_multiple_jobs(
            dsp.derived_series, dsp.parent_series)
        job = bulk.load(DistributionJob, job_ids)[0]

        sourcepackagenameid = spph.sourcepackagerelease.sourcepackagename.id
        expected_metadata = {
            u'sourcepackagename': sourcepackagenameid,
            u'parent_series': dsp.parent_series.id}
        self.assertThat(job, MatchesStructure.byEquality(
            distribution=dsp.derived_series.distribution,
            distroseries=dsp.derived_series,
            job_type=DistributionJobType.DISTROSERIESDIFFERENCE,
            metadata=expected_metadata))

    def test_create_multiple_jobs_ignore_other_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        spphs = self.createSPPHs(dsp.derived_series)

        # Create other SPPHs ...
        dsp2 = self.factory.makeDistroSeriesParent()
        self.createSPPHs(dsp2.derived_series)

        # ... and some more.
        dsp3 = self.factory.makeDistroSeriesParent(
            parent_series=dsp.parent_series)
        self.createSPPHs(dsp3.derived_series)

        job_ids = create_multiple_jobs(
            dsp.derived_series, dsp.parent_series)
        jobs = bulk.load(DistributionJob, job_ids)

        self.assertContentEqual(
            [spph.sourcepackagerelease.sourcepackagename.id
                for spph in spphs],
            [job.metadata[u'sourcepackagename'] for job in jobs])

    def test_create_multiple_jobs_creates_waiting_jobs(self):
        dsp = self.factory.makeDistroSeriesParent()
        self.createSPPHs(dsp.derived_series, 1)
        job_ids = create_multiple_jobs(
            dsp.derived_series, dsp.parent_series)
        dsdjob = bulk.load(DistributionJob, job_ids)[0]

        self.assertEqual(JobStatus.WAITING, dsdjob.job.status)

    def test_create_multiple_jobs_no_jobs(self):
        # If no job needs to be created, create_multiple_jobs
        # returns an empty list.
        dsp = self.factory.makeDistroSeriesParent()
        job_ids = create_multiple_jobs(
            dsp.derived_series, dsp.parent_series)

        self.assertEqual([], job_ids)

    def find_waiting_jobs_finds_waiting_jobs(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertContentEqual(
            [job],
            find_waiting_jobs(dsp.derived_series, package, dsp.parent_series))

    def find_waiting_jobs_ignores_other_derived_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        create_job(dsp.derived_series, package, dsp.parent_series)
        other_series = self.factory.makeDistroSeries()
        self.assertContentEqual(
            [], find_waiting_jobs(other_series, package, dsp.parent_series))

    def find_waiting_jobs_ignores_other_parent_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        create_job(dsp.derived_series, package, dsp.parent_series)
        other_series = self.factory.makeDistroSeries()
        self.assertContentEqual(
            [], find_waiting_jobs(dsp.derived_series, package, other_series))

    def test_find_waiting_jobs_ignores_other_packages(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        create_job(dsp.derived_series, package, dsp.parent_series)
        other_package = self.factory.makeSourcePackageName()
        self.assertContentEqual(
            [],
            find_waiting_jobs(
                dsp.derived_series, other_package, dsp.parent_series))

    def test_find_waiting_jobs_considers_only_waiting_jobs(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        job.start()
        self.assertContentEqual(
            [],
            find_waiting_jobs(dsp.derived_series, package, dsp.parent_series))
        job.complete()
        self.assertContentEqual(
            [],
            find_waiting_jobs(dsp.derived_series, package, dsp.parent_series))

    def assertJobsSeriesAndMetadata(self, job, series, metadata):
        self.assertEqual(job.distroseries, series)
        self.assertEqual(
            (metadata[0], metadata[1]),
            (job.metadata["sourcepackagename"],
             job.metadata["parent_series"]))

    def test_createForPackagePublication_creates_job_for_derived_series(self):
        # A call to createForPackagePublication for the derived_series
        # creates a job for the derived series.
        dsp = self.factory.makeDistroSeriesParent()
        parent_dsp = self.factory.makeDistroSeriesParent(
            derived_series=dsp.parent_series)
        package = self.factory.makeSourcePackageName()
        self.getJobSource().createForPackagePublication(
            parent_dsp.derived_series, package,
            PackagePublishingPocket.RELEASE)
        jobs = find_waiting_jobs(
            dsp.derived_series, package, dsp.parent_series)

        self.assertEquals(len(jobs), 1)
        self.assertJobsSeriesAndMetadata(
            jobs[0], dsp.derived_series, [package.id, dsp.parent_series.id])

    def test_createForPackagePublication_creates_job_for_parent_series(self):
        # A call to createForPackagePublication for the derived_series
        # creates a job for the parent series.
        dsp = self.factory.makeDistroSeriesParent()
        parent_dsp = self.factory.makeDistroSeriesParent(
            derived_series=dsp.parent_series)
        package = self.factory.makeSourcePackageName()
        self.getJobSource().createForPackagePublication(
            parent_dsp.derived_series, package,
            PackagePublishingPocket.RELEASE)
        parent_jobs = find_waiting_jobs(
            parent_dsp.derived_series, package, parent_dsp.parent_series)

        self.assertEquals(len(parent_jobs), 1)
        self.assertJobsSeriesAndMetadata(
            parent_jobs[0], dsp.parent_series,
            [package.id, parent_dsp.parent_series.id])

    def test_createForPackagePublication_ignores_backports_and_proposed(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        self.getJobSource().createForPackagePublication(
            dsp.derived_series, package, PackagePublishingPocket.BACKPORTS)
        self.getJobSource().createForPackagePublication(
            dsp.derived_series, package, PackagePublishingPocket.PROPOSED)
        self.assertContentEqual(
            [],
            find_waiting_jobs(dsp.derived_series, package, dsp.parent_series))

    def test_createForSPPHs_creates_job_for_derived_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        spph = self.factory.makeSourcePackagePublishingHistory(
            dsp.parent_series, pocket=PackagePublishingPocket.RELEASE)
        spn = spph.sourcepackagerelease.sourcepackagename

        self.getJobSource().createForSPPHs([spph])

        self.assertEqual(
            1, len(find_waiting_jobs(
                dsp.derived_series, spn, dsp.parent_series)))

    def test_createForSPPHs_creates_job_for_parent_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        spph = self.factory.makeSourcePackagePublishingHistory(
            dsp.derived_series, pocket=PackagePublishingPocket.RELEASE)
        spn = spph.sourcepackagerelease.sourcepackagename

        self.getJobSource().createForSPPHs([spph])

        self.assertEqual(
            1, len(find_waiting_jobs(
                dsp.derived_series, spn, dsp.parent_series)))

    def test_createForSPPHs_ignores_backports_and_proposed(self):
        dsp = self.factory.makeDistroSeriesParent()
        spr = self.factory.makeSourcePackageRelease()
        spn = spr.sourcepackagename
        ignored_pockets = [
            PackagePublishingPocket.BACKPORTS,
            PackagePublishingPocket.PROPOSED,
            ]
        spphs = [
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=dsp.parent_series, sourcepackagerelease=spr,
                pocket=pocket)
            for pocket in ignored_pockets]
        self.getJobSource().createForSPPHs(spphs)
        self.assertContentEqual(
            [], find_waiting_jobs(dsp.derived_series, spn, dsp.parent_series))

    def test_createForSPPHs_creates_no_jobs_for_unrelated_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        other_series = self.factory.makeDistroSeries(
            distribution=dsp.derived_series.distribution)
        spph = self.factory.makeSourcePackagePublishingHistory(
            dsp.parent_series, pocket=PackagePublishingPocket.RELEASE)
        spn = spph.sourcepackagerelease.sourcepackagename
        self.getJobSource().createForSPPHs([spph])
        self.assertContentEqual(
            [], find_waiting_jobs(dsp.derived_series, spn, other_series))

    def test_createForSPPHs_accepts_SPPHs_for_multiple_distroseries(self):
        derived_distro = self.factory.makeDistribution()
        spn = self.factory.makeSourcePackageName()
        series = [
            self.factory.makeDistroSeries(derived_distro)
            for counter in xrange(2)]
        dsps = [
            self.factory.makeDistroSeriesParent(derived_series=distroseries)
            for distroseries in series]

        for distroseries in series:
            self.factory.makeSourcePackagePublishingHistory(
                distroseries, pocket=PackagePublishingPocket.RELEASE,
                sourcepackagerelease=self.factory.makeSourcePackageRelease(
                    sourcepackagename=spn))

        job_counts = dict(
            (dsp.derived_series, len(find_waiting_jobs(
                dsp.derived_series, spn, dsp.parent_series)))
            for dsp in dsps)
        self.assertEqual(
            dict((distroseries, 1) for distroseries in series),
            job_counts)

    def test_createForSPPHs_behaves_sensibly_if_job_already_exists(self):
        # If a job already existed, createForSPPHs may create a
        # redundant one but it certainly won't do anything weird like
        # delete what was there or create too many.
        dsp = self.factory.makeDistroSeriesParent()
        spph = self.factory.makeSourcePackagePublishingHistory(
            dsp.parent_series, pocket=PackagePublishingPocket.RELEASE)
        spn = spph.sourcepackagerelease.sourcepackagename

        create_jobs = range(1, 3)
        for counter in create_jobs:
            self.getJobSource().createForSPPHs([spph])

        job_count = len(find_waiting_jobs(
            dsp.derived_series, spn, dsp.parent_series))
        self.assertIn(job_count, create_jobs)

    def test_createForSPPHs_creates_no_jobs_for_ppas(self):
        dsp = self.factory.makeDistroSeriesParent()
        series = dsp.parent_series
        spph = self.factory.makeSourcePackagePublishingHistory(
            series, pocket=PackagePublishingPocket.RELEASE,
            archive=self.factory.makeArchive(
                distribution=series.distribution, purpose=ArchivePurpose.PPA))
        spn = spph.sourcepackagerelease.sourcepackagename
        self.getJobSource().createForSPPHs([spph])
        self.assertContentEqual(
            [], find_waiting_jobs(dsp.derived_series, spn, dsp.parent_series))

    def test_getPendingJobsForDifferences_finds_job(self):
        dsd = self.factory.makeDistroSeriesDifference()
        job = create_job(
            dsd.derived_series, dsd.source_package_name, dsd.parent_series)
        self.assertEqual(
            {dsd: [job]},
            self.getJobSource().getPendingJobsForDifferences(
                dsd.derived_series, [dsd]))

    def test_getPendingJobsForDifferences_ignores_other_package(self):
        dsd = self.factory.makeDistroSeriesDifference()
        create_job(
            dsd.derived_series, self.factory.makeSourcePackageName(),
            dsd.parent_series)
        self.assertEqual(
            {},
            self.getJobSource().getPendingJobsForDifferences(
                dsd.derived_series, [dsd]))

    def test_getPendingJobsForDifferences_ignores_other_derived_series(self):
        dsd = self.factory.makeDistroSeriesDifference()
        create_job(
            self.makeDerivedDistroSeries(), dsd.source_package_name,
            dsd.parent_series)
        self.assertEqual(
            {},
            self.getJobSource().getPendingJobsForDifferences(
                dsd.derived_series, [dsd]))

    def test_getPendingJobsForDifferences_ignores_other_parent_series(self):
        dsd = self.factory.makeDistroSeriesDifference()
        other_parent = self.factory.makeDistroSeriesParent(
            dsd.derived_series).parent_series
        create_job(
            dsd.derived_series, dsd.source_package_name, other_parent)
        self.assertEqual(
            {},
            self.getJobSource().getPendingJobsForDifferences(
                dsd.derived_series, [dsd]))

    def test_getPendingJobsForDifferences_ignores_non_pending_jobs(self):
        dsd = self.factory.makeDistroSeriesDifference()
        job = create_job(
            dsd.derived_series, dsd.source_package_name, dsd.parent_series)
        removeSecurityProxy(job).job._status = JobStatus.COMPLETED
        self.assertEqual(
            {},
            self.getJobSource().getPendingJobsForDifferences(
                dsd.derived_series, [dsd]))

    def test_getPendingJobsForDifferences_ignores_other_job_types(self):
        dsd = self.factory.makeDistroSeriesDifference()
        DistributionJob(
            distribution=dsd.derived_series.distribution,
            distroseries=dsd.derived_series,
            job_type=DistributionJobType.INITIALIZE_SERIES,
            metadata={
                "sourcepackagename": dsd.source_package_name.id,
                "parent_series": dsd.parent_series.id})
        self.assertEqual(
            {},
            self.getJobSource().getPendingJobsForDifferences(
                dsd.derived_series, [dsd]))

    def test_cronscript(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        self.getJobSource().createForPackagePublication(
            dsp.derived_series, package, PackagePublishingPocket.RELEASE)
        # Make changes visible to the process we'll be spawning.
        transaction.commit()
        return_code, stdout, stderr = run_script(
            'cronscripts/process-job-source.py',
            ['-v', 'IDistroSeriesDifferenceJobSource'])
        # The cronscript ran how we expected it to.
        self.assertEqual(return_code, 0)
        self.assertIn(
            'INFO    Ran 1 DistroSeriesDifferenceJob jobs.', stderr)
        # And it did what we expected.
        jobs = find_waiting_jobs(
            dsp.derived_series, package, dsp.parent_series)
        self.assertContentEqual([], jobs)
        self.assertEqual(1, find_dsd_for(dsp, package).count())

    def test_job_runner_does_not_create_multiple_dsds(self):
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        job = self.getJobSource().createForPackagePublication(
            dsp.derived_series, package, PackagePublishingPocket.RELEASE)
        job[0].start()
        job[0].run()
        # Complete the job so we can create another.
        job[0].job.complete()
        # The first job would have created a DSD for us.
        self.assertEqual(1, find_dsd_for(dsp, package).count())
        # If we run the job again, it will not create another DSD.
        job = self.getJobSource().createForPackagePublication(
            dsp.derived_series, package, PackagePublishingPocket.RELEASE)
        job[0].start()
        job[0].run()
        self.assertEqual(1, find_dsd_for(dsp, package).count())

    def test_packageset_filter_passes_inherited_packages(self):
        dsp = self.factory.makeDistroSeriesParent()
        # Parent must have a packageset or the filter will pass anyway.
        self.factory.makePackageset(distroseries=dsp.parent_series)
        package = self.factory.makeSourcePackageName()
        # Package is not in the packageset _but_ both the parent and
        # derived series have it.
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series, sourcepackagename=package)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.derived_series, sourcepackagename=package)
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertTrue(job.passesPackagesetFilter())

    def test_packageset_filter_passes_packages_unique_to_derived_series(self):
        dsp = self.factory.makeDistroSeriesParent()
        # Parent must have a packageset or the filter will pass anyway.
        self.factory.makePackageset(distroseries=dsp.parent_series)
        package = self.factory.makeSourcePackageName()
        # Package exists in the derived series but not in the parent
        # series.
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.derived_series, sourcepackagename=package)
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertTrue(job.passesPackagesetFilter())

    def test_packageset_filter_passes_all_if_parent_has_no_packagesets(self):
        # Debian in particular has no packagesets.  If the parent series
        # has no packagesets, the packageset filter passes all packages.
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series, sourcepackagename=package)
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertTrue(job.passesPackagesetFilter())

    def makeInheritedPackageSet(self, distro_series_parent, packages=()):
        """Simulate an inherited `Packageset`.

        Creates a packageset in the parent that has an equivalent in
        `derived_series`.
        """
        parent_packageset = self.factory.makePackageset(
            distroseries=distro_series_parent.parent_series,
            packages=packages)
        return self.factory.makePackageset(
            distroseries=distro_series_parent.derived_series,
            packages=packages, name=parent_packageset.name,
            owner=parent_packageset.owner, related_set=parent_packageset)

    def test_packageset_filter_passes_package_in_inherited_packageset(self):
        dsp = self.factory.makeDistroSeriesParent()
        # Package is in a packageset on the parent that the derived
        # series also has.
        package = self.factory.makeSourcePackageName()
        self.makeInheritedPackageSet(dsp, [package])
        # Package is in parent series and in a packageset that the
        # derived series inherited.
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series, sourcepackagename=package)
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertTrue(job.passesPackagesetFilter())

    def test_packageset_filter_blocks_unwanted_parent_package(self):
        dsp = self.factory.makeDistroSeriesParent()
        self.makeInheritedPackageSet(dsp)
        package = self.factory.makeSourcePackageName()
        # Package is in the parent series but not in a packageset shared
        # between the derived series and the parent series.
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series, sourcepackagename=package)
        job = create_job(dsp.derived_series, package, dsp.parent_series)
        self.assertFalse(job.passesPackagesetFilter())


class TestDistroSeriesDifferenceJobEndToEnd(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestDistroSeriesDifferenceJobEndToEnd, self).setUp()
        self.store = IMasterStore(DistroSeriesDifference)

    def getJobSource(self):
        return getUtility(IDistroSeriesDifferenceJobSource)

    def makeDerivedDistroSeries(self):
        dsp = self.factory.makeDistroSeriesParent()
        return dsp

    def createPublication(self, source_package_name, versions, distroseries,
                          archive=None):
        if archive is None:
            archive = distroseries.main_archive
        changelog_lfa = self.factory.makeChangelog(
            source_package_name.name, versions)
        # Commit for the Librarian's sake.
        transaction.commit()
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=source_package_name, version=versions[0],
            changelog=changelog_lfa)
        return self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, archive=archive,
            distroseries=distroseries,
            status=PackagePublishingStatus.PUBLISHED,
            pocket=PackagePublishingPocket.RELEASE)

    def findDSD(self, derived_series, source_package_name):
        return self.store.find(
            DistroSeriesDifference,
            DistroSeriesDifference.derived_series == derived_series,
            DistroSeriesDifference.source_package_name ==
            source_package_name)

    def runJob(self, job):
        switch_dbuser('distroseriesdifferencejob')
        dsdjob = DistroSeriesDifferenceJob(job)
        dsdjob.start()
        dsdjob.run()
        dsdjob.complete()
        switch_dbuser('launchpad')

    def test_parent_gets_newer(self):
        # When a new source package is uploaded to the parent distroseries,
        # a job is created that updates the relevant DSD.
        dsp = self.makeDerivedDistroSeries()
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-1derived1', '1.0-1'],
            dsp.derived_series)
        self.createPublication(
            source_package_name, ['1.0-1'], dsp.parent_series)

        # Creating the SPPHs has created jobs for us, so grab them off
        # the queue.
        jobs = find_waiting_jobs(
            dsp.derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = find_dsd_for(dsp, source_package_name)
        self.assertEqual(1, ds_diff.count())
        self.assertEqual('1.0-1', ds_diff[0].parent_source_version)
        self.assertEqual('1.0-1derived1', ds_diff[0].source_version)
        self.assertEqual('1.0-1', ds_diff[0].base_version)
        # Now create a 1.0-2 upload to the parent.
        self.createPublication(
            source_package_name, ['1.0-2', '1.0-1'],
            dsp.parent_series)
        jobs = find_waiting_jobs(
            dsp.derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        # And the DSD we have a hold of will have updated.
        self.assertEqual('1.0-2', ds_diff[0].parent_source_version)
        self.assertEqual('1.0-1derived1', ds_diff[0].source_version)
        self.assertEqual('1.0-1', ds_diff[0].base_version)

    def test_child_gets_newer(self):
        # When a new source is uploaded to the child distroseries, the DSD is
        # updated and auto-blacklisted.
        dsp = self.makeDerivedDistroSeries()
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-1'], dsp.derived_series)
        self.createPublication(
            source_package_name, ['1.0-1'], dsp.parent_series)
        jobs = find_waiting_jobs(
            dsp.derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = find_dsd_for(dsp, source_package_name)
        self.assertEqual(
            DistroSeriesDifferenceStatus.RESOLVED, ds_diff[0].status)
        self.createPublication(
            source_package_name, ['2.0-0derived1', '1.0-1'],
            dsp.derived_series)
        jobs = find_waiting_jobs(
            dsp.derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            ds_diff[0].status)
        self.assertEqual('1.0-1', ds_diff[0].base_version)

        # An additional upload should not change the blacklisted status.
        self.createPublication(
            source_package_name, ['2.0-0derived2', '1.0-1'],
            dsp.derived_series)
        jobs = find_waiting_jobs(
            dsp.derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            ds_diff[0].status)

    def test_child_is_synced(self):
        # If the source package gets 'synced' to the child from the parent,
        # the job correctly updates the DSD.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-1derived1', '1.0-1'], derived_series)
        self.createPublication(
            source_package_name, ['1.0-2', '1.0-1'], dsp.parent_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = self.findDSD(derived_series, source_package_name)
        self.assertEqual('1.0-1', ds_diff[0].base_version)
        self.createPublication(
            source_package_name, ['1.0-2', '1.0-1'], derived_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        self.assertEqual(
            DistroSeriesDifferenceStatus.RESOLVED, ds_diff[0].status)

    def test_only_in_child(self):
        # If a source package only exists in the child distroseries, the DSD
        # is created with the right type.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-0derived1'], derived_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = self.findDSD(derived_series, source_package_name)
        self.assertEqual(
            DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES,
            ds_diff[0].difference_type)

    def test_only_in_parent(self):
        # If a source package only exists in the parent distroseries, the DSD
        # is created with the right type.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-1'], dsp.parent_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = self.findDSD(derived_series, source_package_name)
        self.assertEqual(
            DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES,
            ds_diff[0].difference_type)

    def test_deleted_in_parent(self):
        # If a source package is deleted in the parent, a job is created, and
        # the DSD is updated correctly.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-1'], derived_series)
        spph = self.createPublication(
            source_package_name, ['1.0-1'], dsp.parent_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = self.findDSD(derived_series, source_package_name)
        self.assertEqual(
            DistroSeriesDifferenceStatus.RESOLVED, ds_diff[0].status)
        spph.requestDeletion(self.factory.makePerson())
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        self.assertEqual(
            DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES,
            ds_diff[0].difference_type)

    def test_deleted_in_child(self):
        # If a source package is deleted in the child, a job is created, and
        # the DSD is updated correctly.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        spph = self.createPublication(
            source_package_name, ['1.0-1'], derived_series)
        self.createPublication(
            source_package_name, ['1.0-1'], dsp.parent_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = self.findDSD(derived_series, source_package_name)
        self.assertEqual(
            DistroSeriesDifferenceStatus.RESOLVED, ds_diff[0].status)
        spph.requestDeletion(self.factory.makePerson())
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        self.assertEqual(
            DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES,
            ds_diff[0].difference_type)

    def test_no_job_for_PPA(self):
        # If a source package is uploaded to a PPA, a job is not created.
        dsp = self.makeDerivedDistroSeries()
        source_package_name = self.factory.makeSourcePackageName()
        ppa = self.factory.makeArchive()
        self.createPublication(
            source_package_name, ['1.0-1'], dsp.derived_series, ppa)
        self.assertContentEqual(
            [],
            find_waiting_jobs(
                dsp.derived_series, source_package_name, dsp.parent_series))

    def test_no_job_for_PPA_with_deleted_source(self):
        # If a source package is deleted from a PPA, no job is created.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        ppa = self.factory.makeArchive()
        spph = self.createPublication(
            source_package_name, ['1.0-1'], derived_series, ppa)
        spph.requestDeletion(ppa.owner)
        self.assertContentEqual(
            [],
            find_waiting_jobs(
                derived_series, source_package_name, dsp.parent_series))

    def test_update_deletes_diffs(self):
        # When a DSD is updated, the diffs are invalidated.
        dsp = self.makeDerivedDistroSeries()
        derived_series = dsp.derived_series
        source_package_name = self.factory.makeSourcePackageName()
        self.createPublication(
            source_package_name, ['1.0-1derived1', '1.0-1'], derived_series)
        self.createPublication(
            source_package_name, ['1.0-2', '1.0-1'], dsp.parent_series)
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=source_package_name, version='1.0-1')
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr,
            archive=dsp.parent_series.main_archive,
            distroseries=dsp.parent_series,
            status=PackagePublishingStatus.SUPERSEDED)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        ds_diff = self.findDSD(derived_series, source_package_name)
        ds_diff[0].requestPackageDiffs(self.factory.makePerson())
        self.assertIsNot(None, ds_diff[0].package_diff)
        self.assertIsNot(None, ds_diff[0].parent_package_diff)
        self.createPublication(
            source_package_name, ['1.0-3', '1.0-2', '1.0-1'],
            dsp.parent_series)
        jobs = find_waiting_jobs(
            derived_series, source_package_name, dsp.parent_series)
        self.runJob(jobs[0])
        # Since the diff showing the changes from 1.0-1 to 1.0-1derived1 is
        # still valid, it isn't reset, but the parent diff is.
        self.assertIsNot(None, ds_diff[0].package_diff)
        self.assertIs(None, ds_diff[0].parent_package_diff)


class TestDistroSeriesDifferenceJobPermissions(TestCaseWithFactory):
    """Database permissions test for `DistroSeriesDifferenceJob`."""

    layer = LaunchpadZopelessLayer

    def test_permissions(self):
        script_users = [
            'archivepublisher',
            'gina',
            'queued',
            'uploader',
            ]
        dsp = self.factory.makeDistroSeriesParent()
        parent = dsp.parent_series
        derived = dsp.derived_series
        packages = dict(
            (user, self.factory.makeSourcePackageName())
            for user in script_users)
        for user in script_users:
            switch_dbuser(user)
            try:
                create_job(derived, packages[user], parent)
            except ProgrammingError as e:
                self.assertTrue(
                    False,
                    "Database role %s was unable to create a job.  "
                    "Error was: %s" % (user, e))

        # The test is that we get here without exceptions.
        pass

    def test_getDerivedSeries(self):
        # Check that DB users can query derived series.
        script_users = ['queued']
        dsp = self.factory.makeDistroSeriesParent()
        for user in script_users:
            switch_dbuser(user)
            list(dsp.parent_series.getDerivedSeries())

    def test_passesPackagesetFilter(self):
        dsp = self.factory.makeDistroSeriesParent()
        self.factory.makePackageset(distroseries=dsp.parent_series)
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series,
            archive=dsp.parent_series.main_archive,
            pocket=PackagePublishingPocket.RELEASE)
        dsdj = create_job(
            dsp.derived_series, spph.sourcepackagerelease.sourcepackagename,
            dsp.parent_series)

        switch_dbuser('distroseriesdifferencejob')

        dsdj.passesPackagesetFilter()

        # The test is that we get here without exceptions.
        pass


class TestViaCelery(TestCaseWithFactory):

    layer = CeleryJobLayer

    def test_DerivedDistroseriesDifferenceJob(self):
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'DistroSeriesDifferenceJob',
            }))
        dsp = self.factory.makeDistroSeriesParent()
        package = self.factory.makeSourcePackageName()
        with block_on_job():
            job = create_job(dsp.derived_series, package, dsp.parent_series)
            transaction.commit()
        self.assertEqual(JobStatus.COMPLETED, job.status)
