# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functional tests for process-death-row.py script.

See lib/canonical/launchpad/doc/deathrow.txt for more detailed tests
of the module functionality; here we just aim to test that the script
processes its arguments and handles dry-run correctly.
"""

__metaclass__ = type

import datetime
import os
import shutil
import subprocess
import sys
from tempfile import mkdtemp
from unittest import TestCase

import pytz
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.model.publishing import SourcePackagePublishingHistory
from lp.testing.layers import LaunchpadZopelessLayer


class TestProcessDeathRow(TestCase):
    """Test the process-death-row.py script works properly."""

    layer = LaunchpadZopelessLayer

    def runDeathRow(self, extra_args, distribution="ubuntutest"):
        """Run process-death-row.py, returning the result and output."""
        script = os.path.join(config.root, "scripts", "process-death-row.py")
        args = [sys.executable, script, "-v", "-d", distribution,
                "-p", self.primary_test_folder]
        args.extend(extra_args)
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        err_msg = ("process-deathrow returned %s:\n%s" %
                   (process.returncode, stderr))
        self.assertEqual(process.returncode, 0, err_msg)

        return (process.returncode, stdout, stderr)

    def setUp(self):
        """Set up for a test death row run."""
        self.setupPrimaryArchive()
        self.setupPPA()

        # Commit so script can see our publishing record changes.
        self.layer.txn.commit()

    def tearDown(self):
        """Clean up after ourselves."""
        self.tearDownPrimaryArchive()
        self.tearDownPPA()

    def setupPrimaryArchive(self):
        """Create pending removal publications in ubuntutest PRIMARY archive.

        Also places the respective content in disk, so it can be removed
        and verified.
        """
        ubuntutest = getUtility(IDistributionSet)["ubuntutest"]
        ut_alsautils = ubuntutest.getSourcePackage("alsa-utils")
        ut_alsautils_109a4 = ut_alsautils.getVersion("1.0.9a-4")
        primary_pubrecs = ut_alsautils_109a4.publishing_history
        self.primary_pubrec_ids = self.markPublishingForRemoval(
            primary_pubrecs)

        self.primary_test_folder = mkdtemp()
        package_folder = os.path.join(
            self.primary_test_folder, "main", "a", "alsa-utils")
        os.makedirs(package_folder)

        self.primary_package_path = os.path.join(
            package_folder, "alsa-utils_1.0.9a-4.dsc")

        self.writeContent(self.primary_package_path)

    def tearDownPrimaryArchive(self):
        shutil.rmtree(self.primary_test_folder)

    def setupPPA(self):
        """Create pending removal publications in cprov PPA.

        Firstly, transform the cprov & mark PPAs in a ubuntutest PPA,
        since ubuntu publish configuration is broken in the sampledata.

        Also create one respective file in disk, so it can be removed and
        verified.
        """
        ubuntutest = getUtility(IDistributionSet)['ubuntutest']

        cprov = getUtility(IPersonSet).getByName('cprov')
        removeSecurityProxy(cprov.archive).distribution = ubuntutest
        ppa_pubrecs = cprov.archive.getPublishedSources(u'iceweasel')
        self.ppa_pubrec_ids = self.markPublishingForRemoval(ppa_pubrecs)

        mark = getUtility(IPersonSet).getByName('mark')
        removeSecurityProxy(mark.archive).distribution = ubuntutest
        ppa_pubrecs = mark.archive.getPublishedSources(u'iceweasel')
        self.ppa_pubrec_ids.extend(self.markPublishingForRemoval(ppa_pubrecs))

        # Fill one of the files in cprov PPA just to ensure that deathrow
        # will be able to remove it. The other files can remain missing
        # in order to test if deathrow can cope with not-found files.
        self.ppa_test_folder = os.path.join(
            config.personalpackagearchive.root, "cprov", cprov.archive.name)
        package_folder = os.path.join(
            self.ppa_test_folder, "ubuntutest/pool/main/i/iceweasel")
        os.makedirs(package_folder)
        self.ppa_package_path = os.path.join(
            package_folder, "iceweasel-1.0.dsc")
        self.writeContent(self.ppa_package_path)

    def tearDownPPA(self):
        shutil.rmtree(self.ppa_test_folder)

    def writeContent(self, path, content="whatever"):
        f = open(path, "w")
        f.write("This is some test file contents")
        f.close()

    def markPublishingForRemoval(self, pubrecs):
        """Mark the given publishing record for removal."""
        pubrec_ids = []
        for pubrec in pubrecs:
            pubrec.status = PackagePublishingStatus.SUPERSEDED
            pubrec.dateremoved = None
            pubrec.scheduleddeletiondate = datetime.datetime(
                1999, 1, 1, tzinfo=pytz.UTC)
            pubrec_ids.append(pubrec.id)
        return pubrec_ids

    def probePublishingStatus(self, pubrec_ids, status):
        """Check if all source publishing records match the given status."""
        for pubrec_id in pubrec_ids:
            spph = SourcePackagePublishingHistory.get(pubrec_id)
            self.assertEqual(
                spph.status, status, "ID %s -> %s (expected %s)" % (
                spph.id, spph.status.title, status.title))

    def probeRemoved(self, pubrec_ids):
        """Check if all source publishing records were removed."""
        right_now = datetime.datetime.now(pytz.timezone('UTC'))
        for pubrec_id in pubrec_ids:
            spph = SourcePackagePublishingHistory.get(pubrec_id)
            self.assertTrue(
                spph.dateremoved < right_now,
                "ID %s -> not removed" % (spph.id))

    def probeNotRemoved(self, pubrec_ids):
        """Check if all source publishing records were not removed."""
        for pubrec_id in pubrec_ids:
            spph = SourcePackagePublishingHistory.get(pubrec_id)
            self.assertTrue(
                spph.dateremoved is None,
                "ID %s -> removed" % (spph.id))

    def testDryRun(self):
        """Test we don't delete the file or change the db in dry run mode."""
        self.runDeathRow(["-n"])
        self.assertTrue(os.path.exists(self.primary_package_path))
        self.assertTrue(os.path.exists(self.ppa_package_path))

        self.probePublishingStatus(
            self.primary_pubrec_ids, PackagePublishingStatus.SUPERSEDED)
        self.probeNotRemoved(self.primary_pubrec_ids)
        self.probePublishingStatus(
            self.ppa_pubrec_ids, PackagePublishingStatus.SUPERSEDED)
        self.probeNotRemoved(self.ppa_pubrec_ids)

    def testWetRun(self):
        """Test we do delete the file and change the db in wet run mode."""
        self.runDeathRow([])
        self.assertFalse(os.path.exists(self.primary_package_path))
        self.assertTrue(os.path.exists(self.ppa_package_path))

        self.probePublishingStatus(
            self.primary_pubrec_ids, PackagePublishingStatus.SUPERSEDED)
        self.probeRemoved(self.primary_pubrec_ids)
        self.probePublishingStatus(
            self.ppa_pubrec_ids, PackagePublishingStatus.SUPERSEDED)
        self.probeNotRemoved(self.ppa_pubrec_ids)

    def testPPARun(self):
        """Test we only work upon PPA."""
        self.runDeathRow(["--ppa"])

        self.assertTrue(os.path.exists(self.primary_package_path))
        self.assertFalse(os.path.exists(self.ppa_package_path))

        self.probePublishingStatus(
            self.primary_pubrec_ids, PackagePublishingStatus.SUPERSEDED)
        self.probeNotRemoved(self.primary_pubrec_ids)
        self.probePublishingStatus(
            self.ppa_pubrec_ids, PackagePublishingStatus.SUPERSEDED)
        self.probeRemoved(self.ppa_pubrec_ids)
