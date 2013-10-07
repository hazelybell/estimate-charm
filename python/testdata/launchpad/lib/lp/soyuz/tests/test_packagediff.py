# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test source package diffs."""

__metaclass__ = type

from datetime import datetime
import os.path

import transaction
from zope.security.proxy import removeSecurityProxy

from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import sqlvalues
from lp.services.job.interfaces.job import JobType
from lp.services.job.model.job import Job
from lp.soyuz.enums import PackageDiffStatus
from lp.soyuz.model.archive import Archive
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import dbuser
from lp.testing.layers import LaunchpadZopelessLayer


def create_proper_job(factory):
    archive = factory.makeArchive()
    foo_dash1 = factory.makeSourcePackageRelease(archive=archive)
    foo_dash15 = factory.makeSourcePackageRelease(archive=archive)
    suite_dir = 'lib/lp/archiveuploader/tests/data/suite'
    files = {
        '%s/foo_1.0-1/foo_1.0-1.diff.gz' % suite_dir: None,
        '%s/foo_1.0-1/foo_1.0-1.dsc' % suite_dir: None,
        '%s/foo_1.0-1/foo_1.0.orig.tar.gz' % suite_dir: None,
        '%s/foo_1.0-1.5/foo_1.0-1.5.diff.gz' % suite_dir: None,
        '%s/foo_1.0-1.5/foo_1.0-1.5.dsc' % suite_dir: None}
    for name in files:
        filename = os.path.split(name)[-1]
        with open(name, 'r') as content:
            files[name] = factory.makeLibraryFileAlias(
                filename=filename, content=content.read())
    transaction.commit()
    dash1_files = (
        '%s/foo_1.0-1/foo_1.0-1.diff.gz' % suite_dir,
        '%s/foo_1.0-1/foo_1.0-1.dsc' % suite_dir,
        '%s/foo_1.0-1/foo_1.0.orig.tar.gz' % suite_dir)
    dash15_files = (
        '%s/foo_1.0-1/foo_1.0.orig.tar.gz' % suite_dir,
        '%s/foo_1.0-1.5/foo_1.0-1.5.diff.gz' % suite_dir,
        '%s/foo_1.0-1.5/foo_1.0-1.5.dsc' % suite_dir)
    for name in dash1_files:
        foo_dash1.addFile(files[name])
    for name in dash15_files:
        foo_dash15.addFile(files[name])
    return foo_dash1.requestDiffTo(factory.makePerson(), foo_dash15)


class TestPackageDiffs(TestCaseWithFactory):
    """Test package diffs."""
    layer = LaunchpadZopelessLayer
    dbuser = config.uploader.dbuser

    def test_packagediff_working(self):
        # Test the case where none of the files required for the diff are
        # expired in the librarian and where everything works as expected.
        diff = create_proper_job(self.factory)
        self.assertEqual(0, removeSecurityProxy(diff)._countDeletedLFAs())
        diff.performDiff()
        self.assertEqual(PackageDiffStatus.COMPLETED, diff.status)

    def expireLFAsForSource(self, source, expire=True, delete=True):
        """Expire the files associated with the given source package in the
        librarian."""
        assert expire or delete
        query = "UPDATE LibraryFileAlias lfa SET "
        if expire:
            query += "expires = %s" % sqlvalues(datetime.utcnow())
        if expire and delete:
            query += ", "
        if delete:
            query += "content = NULL"
        query += """
            FROM
                SourcePackageRelease spr, SourcePackageReleaseFile sprf
            WHERE
                spr.id = %s
                AND sprf.SourcePackageRelease = spr.id
                AND sprf.libraryfile = lfa.id
            """ % sqlvalues(source.id)
        with dbuser('launchpad'):
            IStore(Archive).execute(query)

    def test_packagediff_with_expired_and_deleted_lfas(self):
        # Test the case where files required for the diff are expired *and*
        # deleted in the librarian causing a package diff failure.
        diff = create_proper_job(self.factory)
        self.expireLFAsForSource(diff.from_source)
        self.assertEqual(4, removeSecurityProxy(diff)._countDeletedLFAs())
        diff.performDiff()
        self.assertEqual(PackageDiffStatus.FAILED, diff.status)

    def test_packagediff_with_expired_but_not_deleted_lfas(self):
        # Test the case where files required for the diff are expired but
        # not deleted in the librarian still allowing the package diff to be
        # performed.
        diff = create_proper_job(self.factory)
        # Expire but don't delete the files associated with the 'from_source'
        # package.
        self.expireLFAsForSource(diff.from_source, expire=True, delete=False)
        self.assertEqual(0, removeSecurityProxy(diff)._countDeletedLFAs())
        diff.performDiff()
        self.assertEqual(PackageDiffStatus.COMPLETED, diff.status)

    def test_packagediff_with_deleted_but_not_expired_lfas(self):
        # Test the case where files required for the diff have been
        # deleted explicitly, not through expiry.
        diff = create_proper_job(self.factory)
        self.expireLFAsForSource(diff.from_source, expire=False, delete=True)
        self.assertEqual(4, removeSecurityProxy(diff)._countDeletedLFAs())
        diff.performDiff()
        self.assertEqual(PackageDiffStatus.FAILED, diff.status)

    def test_packagediff_private_with_copied_spr(self):
        # If an SPR has been copied from a private archive to a public
        # archive, diffs against it are public.
        p3a = self.factory.makeArchive(private=True)
        orig_spr = self.factory.makeSourcePackageRelease(archive=p3a)
        spph = self.factory.makeSourcePackagePublishingHistory(
            archive=p3a, sourcepackagerelease=orig_spr)
        private_spr = self.factory.makeSourcePackageRelease(archive=p3a)
        private_diff = private_spr.requestDiffTo(p3a.owner, orig_spr)
        self.assertEqual(1, len(orig_spr.published_archives))
        self.assertTrue(private_diff.private)
        ppa = self.factory.makeArchive(owner=p3a.owner)
        spph.copyTo(spph.distroseries, spph.pocket, ppa)
        self.assertEqual(2, len(orig_spr.published_archives))
        public_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        public_diff = public_spr.requestDiffTo(p3a.owner, orig_spr)
        self.assertFalse(public_diff.private)

    def test_packagediff_public_unpublished(self):
        # If an SPR has been uploaded to a public archive but not yet
        # published, diffs to it are public.
        ppa = self.factory.makeArchive()
        from_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        to_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        diff = from_spr.requestDiffTo(ppa.owner, to_spr)
        self.assertFalse(diff.private)

    def test_job_created(self):
        # Requesting a package diff creates a PackageDiffJob.
        ppa = self.factory.makeArchive()
        from_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        to_spr = self.factory.makeSourcePackageRelease(archive=ppa)
        from_spr.requestDiffTo(ppa.owner, to_spr)
        [job] = IStore(Job).find(
            Job, Job.base_job_type == JobType.GENERATE_PACKAGE_DIFF)
        self.assertIsNot(None, job)
