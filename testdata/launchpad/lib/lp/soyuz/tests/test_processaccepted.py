# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test process-accepted.py"""

from cStringIO import StringIO
from optparse import OptionValueError

from debian.deb822 import Changes
from testtools.matchers import LessThan
import transaction

from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.log.logger import BufferLogger
from lp.services.scripts.base import LaunchpadScriptFailure
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    PackageUploadStatus,
    )
from lp.soyuz.model.queue import PackageUpload
from lp.soyuz.scripts.processaccepted import (
    get_bug_ids_from_changes_file,
    ProcessAccepted,
    )
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class TestProcessAccepted(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer
    dbuser = config.uploadqueue.dbuser

    def setUp(self):
        """Create the Soyuz test publisher."""
        TestCaseWithFactory.setUp(self)
        self.stp = SoyuzTestPublisher()
        self.stp.prepareBreezyAutotest()
        self.test_package_name = u"accept-test"
        self.distro = self.factory.makeDistribution()

    def getScript(self, test_args=None):
        """Return a ProcessAccepted instance."""
        if test_args is None:
            test_args = []
        test_args.append(self.distro.name)
        script = ProcessAccepted("process accepted", test_args=test_args)
        script.logger = BufferLogger()
        script.txn = self.layer.txn
        return script

    def createWaitingAcceptancePackage(self, distroseries, archive=None,
                                       sourcename=None):
        """Create some pending publications."""
        if archive is None:
            archive = self.distro.main_archive
        if sourcename is None:
            sourcename = self.test_package_name
        return self.stp.getPubSource(
            archive=archive, sourcename=sourcename, distroseries=distroseries,
            spr_only=True)

    def test_robustness(self):
        """Test that a broken package doesn't block the publication of other
        packages."""
        # Attempt to upload one source to a supported series.
        # The record is created first and then the status of the series
        # is changed from DEVELOPMENT to SUPPORTED, otherwise it's impossible
        # to create the record.
        distroseries = self.factory.makeDistroSeries(distribution=self.distro)
        # This creates a broken publication.
        self.createWaitingAcceptancePackage(
            distroseries=distroseries, sourcename="notaccepted")
        distroseries.status = SeriesStatus.SUPPORTED
        # Also upload some other things.
        other_distroseries = self.factory.makeDistroSeries(
            distribution=self.distro)
        self.createWaitingAcceptancePackage(distroseries=other_distroseries)
        script = self.getScript([])
        switch_dbuser(self.dbuser)
        script.main()

        # The other source should be published now.
        published_main = self.distro.main_archive.getPublishedSources(
            name=self.test_package_name)
        self.assertEqual(published_main.count(), 1)

        # And an oops should be filed for the first.
        self.assertEqual(1, len(self.oopses))
        error_report = self.oopses[0]
        expected_error = "Failure processing queue_item"
        self.assertStartsWith(
                error_report['req_vars']['error-explanation'],
                expected_error)

    def test_accept_copy_archives(self):
        """Test that publications in a copy archive are accepted properly."""
        # Upload some pending packages in a copy archive.
        distroseries = self.factory.makeDistroSeries(distribution=self.distro)
        copy_archive = self.factory.makeArchive(
            distribution=self.distro, purpose=ArchivePurpose.COPY)
        copy_source = self.createWaitingAcceptancePackage(
            archive=copy_archive, distroseries=distroseries)
        # Also upload some stuff in the main archive.
        self.createWaitingAcceptancePackage(distroseries=distroseries)

        # Before accepting, the package should not be published at all.
        published_copy = copy_archive.getPublishedSources(
            name=self.test_package_name)
        # Using .count() until Storm fixes __nonzero__ on SQLObj result
        # sets, then we can use bool() which is far more efficient than
        # counting.
        self.assertEqual(published_copy.count(), 0)

        # Accept the packages.
        script = self.getScript(['--copy-archives'])
        switch_dbuser(self.dbuser)
        script.main()

        # Packages in main archive should not be accepted and published.
        published_main = self.distro.main_archive.getPublishedSources(
            name=self.test_package_name)
        self.assertEqual(published_main.count(), 0)

        # Check the copy archive source was accepted.
        published_copy = copy_archive.getPublishedSources(
            name=self.test_package_name).one()
        self.assertEqual(
            published_copy.status, PackagePublishingStatus.PENDING)
        self.assertEqual(copy_source, published_copy.sourcepackagerelease)

    def test_commits_after_each_item(self):
        # Test that the script commits after each item, not just at the end.
        uploads = [
            self.createWaitingAcceptancePackage(
                distroseries=self.factory.makeDistroSeries(
                    distribution=self.distro),
                sourcename='source%d' % i)
            for i in range(3)]

        class UploadCheckingSynchronizer:

            commit_count = 0

            def beforeCompletion(inner_self, txn):
                pass

            def afterCompletion(inner_self, txn):
                if txn.status != 'Committed':
                    return
                inner_self.commit_count += 1
                done_count = len([
                    upload for upload in uploads
                    if upload.package_upload.status ==
                        PackageUploadStatus.DONE])
                self.assertEqual(
                    min(len(uploads), inner_self.commit_count),
                    done_count)

        script = self.getScript([])
        switch_dbuser(self.dbuser)
        synch = UploadCheckingSynchronizer()
        transaction.manager.registerSynch(synch)
        script.main()
        self.assertThat(len(uploads), LessThan(synch.commit_count))

    def test_commits_work(self):
        upload = self.factory.makeSourcePackageUpload(
            distroseries=self.factory.makeDistroSeries(
                distribution=self.distro))
        upload_id = upload.id
        self.getScript([]).main()
        self.layer.txn.abort()
        self.assertEqual(
            upload, IStore(PackageUpload).get(PackageUpload, upload_id))

    def test_validateArguments_requires_distro_by_default(self):
        self.assertRaises(
            OptionValueError, ProcessAccepted(test_args=[]).validateArguments)

    def test_validateArguments_requires_no_distro_for_derived_run(self):
        ProcessAccepted(test_args=['--derived']).validateArguments()
        # The test is that this does not raise an exception.
        pass

    def test_validateArguments_does_not_accept_distro_for_derived_run(self):
        distro = self.factory.makeDistribution()
        script = ProcessAccepted(test_args=['--derived', distro.name])
        self.assertRaises(OptionValueError, script.validateArguments)

    def test_findTargetDistros_finds_named_distro(self):
        distro = self.factory.makeDistribution()
        script = ProcessAccepted(test_args=[distro.name])
        self.assertContentEqual([distro], script.findTargetDistros())

    def test_findNamedDistro_raises_error_if_not_found(self):
        nonexistent_distro = self.factory.getUniqueString()
        script = ProcessAccepted(test_args=[nonexistent_distro])
        self.assertRaises(
            LaunchpadScriptFailure,
            script.findNamedDistro, nonexistent_distro)

    def test_findTargetDistros_for_derived_finds_derived_distro(self):
        dsp = self.factory.makeDistroSeriesParent()
        script = ProcessAccepted(test_args=['--derived'])
        self.assertIn(
            dsp.derived_series.distribution, script.findTargetDistros())


class TestBugIDsFromChangesFile(TestCaseWithFactory):
    """Test get_bug_ids_from_changes_file."""

    layer = LaunchpadZopelessLayer
    dbuser = config.uploadqueue.dbuser

    def setUp(self):
        super(TestBugIDsFromChangesFile, self).setUp()
        self.changes = Changes({
            'Format': '1.8',
            'Source': 'swat',
            })

    def getBugIDs(self):
        """Serialize self.changes and use get_bug_ids_from_changes_file to
        extract bug IDs from it.
        """
        stream = StringIO()
        self.changes.dump(stream)
        stream.seek(0)
        return get_bug_ids_from_changes_file(stream)

    def test_no_bugs(self):
        # An empty list is returned if there are no bugs
        # mentioned.
        self.assertEqual([], self.getBugIDs())

    def test_invalid_bug_id(self):
        # Invalid bug ids (i.e. containing non-digit characters) are ignored.
        self.changes["Launchpad-Bugs-Fixed"] = "bla"
        self.assertEqual([], self.getBugIDs())

    def test_unknown_bug_id(self):
        # Unknown bug ids are passed through; they will be ignored later, by
        # close_bug_ids_for_sourcepackagerelease.
        self.changes["Launchpad-Bugs-Fixed"] = "45120"
        self.assertEqual([45120], self.getBugIDs())

    def test_valid_bug(self):
        # For valid bug ids the bug object is returned.
        bug = self.factory.makeBug()
        self.changes["Launchpad-Bugs-Fixed"] = "%d" % bug.id
        self.assertEqual([bug.id], self.getBugIDs())

    def test_case_sensitivity(self):
        # The spelling of Launchpad-Bugs-Fixed is case-insensitive.
        bug = self.factory.makeBug()
        self.changes["LaUnchpad-Bugs-fixed"] = "%d" % bug.id
        self.assertEqual([bug.id], self.getBugIDs())

    def test_multiple_bugs(self):
        # Multiple bug ids can be specified, separated by spaces.
        bug1 = self.factory.makeBug()
        bug2 = self.factory.makeBug()
        self.changes["Launchpad-Bugs-Fixed"] = "%d invalid %d" % (
            bug1.id, bug2.id)
        self.assertEqual([bug1.id, bug2.id], self.getBugIDs())
