# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import date
import subprocess

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.services.database.interfaces import IStore
from lp.services.worlddata.interfaces.country import ICountrySet
from lp.soyuz.model.binarypackagerelease import (
    BinaryPackageReleaseDownloadCount,
    )
from lp.soyuz.scripts.ppa_apache_log_parser import get_ppa_file_key
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadZopelessLayer


class TestPathParsing(TestCase):
    """Test parsing of PPA request paths."""

    def test_get_ppa_file_key_parses_good_paths(self):
        # A valid binary path results in archive, archive owner,
        # distribution and file names.
        archive_owner, archive_name, distro_name, filename = get_ppa_file_key(
            '/cprov/ppa/ubuntu/pool/main/f/foo/foo_1.2.3-4_i386.deb')
        self.assertEqual('cprov', archive_owner)
        self.assertEqual('ppa', archive_name)
        self.assertEqual('ubuntu', distro_name)
        self.assertEqual('foo_1.2.3-4_i386.deb', filename)

    def test_get_ppa_file_key_ignores_bad_paths(self):
        # A path with extra path segments returns None, to indicate that
        # it should be ignored.
        self.assertIs(None, get_ppa_file_key(
            '/cprov/ppa/ubuntu/pool/main/aha/f/foo/foo_1.2.3-4_i386.deb'))
        self.assertIs(None, get_ppa_file_key('/foo'))

    def test_get_ppa_file_key_ignores_non_binary_path(self):
        # A path pointing to a file not from a binary package returns
        # None to indicate that it should be ignored.
        self.assertIs(None, get_ppa_file_key(
            '/cprov/ppa/ubuntu/pool/main/f/foo/foo_1.2.3-4.dsc'))

    def test_get_ppa_file_key_unquotes_path(self):
        archive_owner, archive_name, distro_name, filename = get_ppa_file_key(
            '/cprov/ppa/ubuntu/pool/main/f/foo/foo_1.2.3%7E4_i386.deb')
        self.assertEqual('cprov', archive_owner)
        self.assertEqual('ppa', archive_name)
        self.assertEqual('ubuntu', distro_name)
        self.assertEqual('foo_1.2.3~4_i386.deb', filename)

    def test_get_ppa_file_key_normalises_path(self):
        archive_owner, archive_name, distro_name, filename = get_ppa_file_key(
            '/cprov/ppa/ubuntu/pool//main/f///foo/foo_1.2.3-4_i386.deb')
        self.assertEqual('cprov', archive_owner)
        self.assertEqual('ppa', archive_name)
        self.assertEqual('ubuntu', distro_name)
        self.assertEqual('foo_1.2.3-4_i386.deb', filename)


class TestScriptRunning(TestCaseWithFactory):
    """Run parse-ppa-apache-access-logs.py and test its outcome."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestScriptRunning, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        self.store = IStore(BinaryPackageReleaseDownloadCount)

        self.archive = getUtility(IPersonSet).getByName('cprov').archive
        self.archive.require_virtualized = False

        self.foo_i386, self.foo_hppa = self.publisher.getPubBinaries(
                archive=self.archive, architecturespecific=True)
        self.bar_i386, self.bar_hppa = self.publisher.getPubBinaries(
                binaryname='bar-bin', archive=self.archive,
                architecturespecific=False)

        # Commit so the script can see our changes.
        import transaction
        transaction.commit()

    def test_script_run(self):
        # Before we run the script, there are no binary package
        # downloads in the database.
        # After the script's run, we will check that the results in the
        # database match the sample log files we use for this test:
        # lib/lp/soyuz/scripts/tests/ppa-apache-log-files
        # In addition to the wanted access log file, there is also an
        # error log that will be skipped by the configured glob.
        self.assertEqual(
            0, self.store.find(BinaryPackageReleaseDownloadCount).count())

        process = subprocess.Popen(
            'cronscripts/parse-ppa-apache-access-logs.py', shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out, err) = process.communicate()
        self.assertEqual(
            process.returncode, 0, "stdout:%s, stderr:%s" % (out, err))

        # The error log does not match the glob, so it is not processed,
        # and no OOPS is generated.
        self.oops_capture.sync()
        self.assertEqual([], self.oopses)

        # Must commit because the changes were done in another transaction.
        import transaction
        transaction.commit()
        results = self.store.find(BinaryPackageReleaseDownloadCount)

        australia = getUtility(ICountrySet)['AU']
        austria = getUtility(ICountrySet)['AT']

        self.assertEqual(
            [(self.foo_hppa.binarypackagerelease,
              self.archive,
              date(2008, 6, 13),
              australia,
              1),
             (self.foo_i386.binarypackagerelease,
              self.archive,
              date(2008, 6, 13),
              australia,
              1),
             (self.foo_i386.binarypackagerelease,
              self.archive,
              date(2008, 6, 13),
              austria,
              1),
             (self.bar_i386.binarypackagerelease,
              self.archive,
              date(2008, 6, 14),
              None,
              1),
             (self.bar_i386.binarypackagerelease,
              self.archive,
              date(2008, 6, 14),
              austria,
              1)],
            sorted(
                [(result.binary_package_release, result.archive, result.day,
                  result.country, result.count) for result in results],
                 key=lambda r: (r[0].id, r[2], r[3].name if r[3] else None)))
