# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for deathrow class."""

__metaclass__ = type


import os
import shutil
import tempfile

from zope.component import getUtility

from lp.archivepublisher.deathrow import DeathRow
from lp.archivepublisher.diskpool import DiskPool
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.log.logger import BufferLogger
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCase
from lp.testing.layers import LaunchpadZopelessLayer


class TestDeathRow(TestCase):

    layer = LaunchpadZopelessLayer

    def getTestPublisher(self, distroseries):
        """Return an `SoyuzTestPublisher`instance."""
        stp = SoyuzTestPublisher()
        stp.addFakeChroots(distroseries)
        stp.setUpDefaultDistroSeries(distroseries)
        return stp

    def getDeathRow(self, archive):
        """Return an `DeathRow` for the given archive.

        Created the temporary 'pool' and 'temp' directories and register
        a 'cleanup' to purge them after the test runs.
        """
        pool_path = tempfile.mkdtemp('-pool')
        temp_path = tempfile.mkdtemp('-pool-tmp')

        def clean_pool(pool_path, temp_path):
            shutil.rmtree(pool_path)
            shutil.rmtree(temp_path)
        self.addCleanup(clean_pool, pool_path, temp_path)

        logger = BufferLogger()
        diskpool = DiskPool(pool_path, temp_path, logger)
        return DeathRow(archive, diskpool, logger)

    def getDiskPoolPath(self, pub_file, diskpool):
        """Return the absolute path to a published file in the disk pool/."""
        return diskpool.pathFor(
            pub_file.componentname.encode('utf-8'),
            pub_file.sourcepackagename.encode('utf8'),
            pub_file.libraryfilealiasfilename.encode('utf-8'))

    def assertIsFile(self, path):
        """Assert the path exists and is a regular file."""
        self.assertTrue(
            os.path.exists(path),
            "File %s does not exist" % os.path.basename(path))
        self.assertFalse(
            os.path.islink(path),
            "File %s is a symbolic link" % os.path.basename(path))

    def assertIsLink(self, path):
        """Assert the path exists and is a symbolic link."""
        self.assertTrue(
            os.path.exists(path),
            "File %s does not exist" % os.path.basename(path))
        self.assertTrue(
            os.path.islink(path),
            "File %s is a not symbolic link" % os.path.basename(path))

    def assertDoesNotExist(self, path):
        """Assert the path does not exit."""
        self.assertFalse(
            os.path.exists(path),
            "File %s exists" % os.path.basename(path))

    def test_MissingSymLinkInPool(self):
        # When a publication is promoted from 'universe' to 'main' and
        # the symbolic links expected in 'universe' are not present,
        # a `MissingSymlinkInPool` error is generated and immediately
        # ignored by the `DeathRow` processor. Even in this adverse
        # circumstances the database record (removal candidate) is
        # updated to match the disk status.

        # Setup an `SoyuzTestPublisher` and a `DeathRow` instance.
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        hoary = ubuntu.getSeries('hoary')
        stp = self.getTestPublisher(hoary)
        deathrow = self.getDeathRow(hoary.main_archive)

        # Create a source publication with a since file (DSC) in
        # 'universe' and promote it to 'main'.
        source_universe = stp.getPubSource(component='universe')
        source_main = source_universe.changeOverride(
            new_component=getUtility(IComponentSet)['main'])
        test_publications = (source_universe, source_main)

        # Commit for exposing the just-created librarian files.
        self.layer.commit()

        # Publish the testing publication on disk, the file for the
        # 'universe' component will be a symbolic link to the one
        # in 'main'.
        for pub in test_publications:
            pub.publish(deathrow.diskpool, deathrow.logger)
        [main_dsc_path] = [
            self.getDiskPoolPath(pub_file, deathrow.diskpool)
            for pub_file in source_main.files]
        [universe_dsc_path] = [
            self.getDiskPoolPath(pub_file, deathrow.diskpool)
            for pub_file in source_universe.files]
        self.assertIsFile(main_dsc_path)
        self.assertIsLink(universe_dsc_path)

        # Remove the symbolic link to emulate MissingSymlinkInPool scenario.
        os.remove(universe_dsc_path)

        # Remove the testing publications.
        for pub in test_publications:
            pub.requestObsolescence()

        # Commit for exposing the just-created removal candidates.
        self.layer.commit()

        # Due to the MissingSymlinkInPool scenario, it takes 2 iteration to
        # remove both references to the shared file in pool/.
        deathrow.reap()
        deathrow.reap()

        for pub in test_publications:
            self.assertTrue(
                pub.dateremoved is not None,
                '%s (%s) is not marked as removed.'
                % (pub.displayname, pub.component.name))

        self.assertDoesNotExist(main_dsc_path)
        self.assertDoesNotExist(universe_dsc_path)
