# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime
import os
import subprocess
import sys
import time

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.job.interfaces.job import JobStatus
from lp.services.log.logger import BufferLogger
from lp.soyuz.adapters.packagelocation import PackageLocationError
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.scripts.ftpmasterbase import SoyuzScriptError
from lp.soyuz.scripts.populate_archive import ArchivePopulator
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCaseWithFactory
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import (
    DatabaseLayer,
    LaunchpadZopelessLayer,
    )


def get_spn(build):
    """Return the SourcePackageName of the given Build."""
    pub = build.current_source_publication
    return pub.sourcepackagerelease.sourcepackagename


class TestPopulateArchiveScript(TestCaseWithFactory):
    """Test the populate-archive.py script."""

    layer = LaunchpadZopelessLayer
    expected_build_spns = [
        u'alsa-utils', u'cnews', u'evolution', u'libstdc++',
        u'linux-source-2.6.15', u'netapplet']
    expected_src_names = [
        u'alsa-utils 1.0.9a-4ubuntu1 in hoary',
        u'cnews cr.g7-37 in hoary', u'evolution 1.0 in hoary',
        u'libstdc++ b8p in hoary',
        u'linux-source-2.6.15 2.6.15.3 in hoary',
        u'netapplet 1.0-1 in hoary', u'pmount 0.1-2 in hoary']
    pending_statuses = (
        PackagePublishingStatus.PENDING,
        PackagePublishingStatus.PUBLISHED)

    def runWrapperScript(self, extra_args=None):
        """Run populate-archive.py, returning the result and output.

        Runs the wrapper script using Popen(), returns a tuple of the
        process's return code, stdout output and stderr output."""
        if extra_args is None:
            extra_args = []
        script = os.path.join(
            config.root, "scripts", "populate-archive.py")
        args = [sys.executable, script, '-y']
        args.extend(extra_args)
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        return (process.returncode, stdout, stderr)

    def getScript(self, test_args=None):
        """Return an ArchivePopulator instance."""
        if test_args is None:
            test_args = []
        script = ArchivePopulator("test copy archives", test_args=test_args)
        script.logger = BufferLogger()
        script.txn = self.layer.txn
        return script

    def testCopyArchiveCreation(self):
        """Start archive population, check data before and after.

        Use the hoary-RELEASE suite along with the main component.
        """
        # XXX: JamesWestby 2010-06-21 bug=596984: it is not clear
        # what this test is testing that is not covered in more
        # specific tests. It should be removed if there is nothing
        # else as it is fragile due to use of sampledata.
        DatabaseLayer.force_dirty_database()
        # Make sure a copy archive with the desired name does
        # not exist yet.
        distro_name = 'ubuntu'
        distro = getUtility(IDistributionSet).getByName(distro_name)

        archive_name = "msa%s" % int(time.time())
        copy_archive = getUtility(IArchiveSet).getByDistroPurpose(
            distro, ArchivePurpose.COPY, archive_name)
        # This is a sanity check: a copy archive with this name should not
        # exist yet.
        self.assertTrue(copy_archive is None)

        hoary = getUtility(IDistributionSet)[distro_name]['hoary']

        # Verify that we have the right source packages in the sample data.
        self._verifyPackagesInSampleData(hoary)

        # Command line arguments required for the invocation of the
        # 'populate-archive.py' script.
        extra_args = [
            '-a', '386',
            '--from-distribution', distro_name, '--from-suite', 'hoary',
            '--to-distribution', distro_name, '--to-suite', 'hoary',
            '--to-archive', archive_name, '--to-user', 'salgado', '--reason',
            '"copy archive from %s"' % datetime.ctime(datetime.utcnow()),
            ]

        # Start archive population now!
        (exitcode, out, err) = self.runWrapperScript(extra_args)
        # Check for zero exit code.
        self.assertEqual(
            exitcode, 0, "\n=> %s\n=> %s\n=> %s\n" % (exitcode, out, err))

        # Make sure the copy archive with the desired name was
        # created
        copy_archive = getUtility(IArchiveSet).getByDistroPurpose(
            distro, ArchivePurpose.COPY, archive_name)
        self.assertTrue(copy_archive is not None)

        # Make sure the right source packages were cloned.
        self._verifyClonedSourcePackages(copy_archive, hoary)

        # Now check that we have build records for the sources cloned.
        builds = list(getUtility(IBinaryPackageBuildSet).getBuildsForArchive(
            copy_archive, status=BuildStatus.NEEDSBUILD))

        # Please note: there will be no build for the pmount package
        # since it is architecture independent and the 'hoary'
        # DistroSeries in the sample data has no DistroArchSeries
        # with chroots set up.
        build_spns = [
            get_spn(removeSecurityProxy(build)).name for build in builds]

        self.assertEqual(build_spns, self.expected_build_spns)

    def runScript(
        self, archive_name=None, suite='hoary', user='salgado',
        exists_before=None, exists_after=None, exception_type=None,
        exception_text=None, extra_args=None, copy_archive_name=None,
        reason=None, output_substr=None, nonvirtualized=False):
        """Run the script to test.

        :type archive_name: `str`
        :param archive_name: the name of the copy archive to create.
        :type suite: `str`
        :param suite: the name of the copy archive suite.
        :type user: `str`
        :param user: the name of the user creating the archive.
        :type exists_before: `bool`
        :param exists_before: copy archive with given name should
            already exist if True.
        :type exists_after: `True`
        :param exists_after: the copy archive is expected to exist
            after script invocation if True.
        :type exception_type: type
        :param exception_type: the type of exception expected in case
            of failure.
        :type exception_text: `str`
        :param exception_text: expected exception text prefix in case
            of failure.
        :type extra_args: list of strings
        :param extra_args: additional arguments to be passed to the
            script (if any).
        :type copy_archive_name: `IArchive`
        :param copy_archive_name: optional copy archive instance, used for
            merge copy testing.
        :param reason: if empty do not provide '--reason' cmd line arg to
            the script
        :param output_substr: this must be part of the script's output
        """

        if copy_archive_name is None:
            now = int(time.time())
            if archive_name is None:
                archive_name = "ra%s" % now
        else:
            archive_name = copy_archive_name

        distro_name = 'ubuntu'
        distro = getUtility(IDistributionSet).getByName(distro_name)

        copy_archive = getUtility(IArchiveSet).getByDistroPurpose(
            distro, ArchivePurpose.COPY, archive_name)

        # Enforce these assertions only if the 'exists_before' flag was
        # specified in first place.
        if exists_before is not None:
            if exists_before:
                self.assertTrue(copy_archive is not None)
            else:
                self.assertTrue(copy_archive is None)

        # Command line arguments required for the invocation of the
        # 'populate-archive.py' script.
        script_args = [
            '--from-distribution', distro_name, '--from-suite', suite,
            '--to-distribution', distro_name, '--to-suite', suite,
            '--to-archive', archive_name, '--to-user', user,
            ]

        # Empty reason string indicates that the '--reason' command line
        # argument should be ommitted.
        if reason is not None and not reason.isspace():
            script_args.extend(['--reason', reason])
        elif reason is None:
            reason = "copy archive, %s" % datetime.ctime(datetime.utcnow())
            script_args.extend(['--reason', reason])

        if nonvirtualized:
            script_args.append('--nonvirtualized')

        if extra_args is not None:
            script_args.extend(extra_args)

        script = ArchivePopulator(
            'populate-archive', dbuser=config.uploader.dbuser,
            test_args=script_args)

        script.logger = BufferLogger()
        script.txn = FakeTransaction()

        if exception_type is not None:
            self.assertRaisesWithContent(
                exception_type, exception_text, script.mainTask)
        else:
            script.mainTask()

        # Does the script's output contain the specified sub-string?
        if output_substr is not None and not output_substr.isspace():
            output = script.logger.getLogBuffer()
            self.assertTrue(output_substr in output)

        copy_archive = getUtility(IArchiveSet).getByDistroPurpose(
            distro, ArchivePurpose.COPY, archive_name)

        # Enforce these assertions only if the 'exists_after' flag was
        # specified in first place.
        if exists_after is not None:
            if exists_after:
                self.assertTrue(copy_archive is not None)
            else:
                self.assertTrue(copy_archive is None)

        return copy_archive

    def testInvalidCopyArchiveName(self):
        """Try copy archive creation/population with an invalid archive name.

        When trying to create and populate a copy archive with an invalid name
        the script should fail with an appropriate error message.
        """
        now = int(time.time())
        # The slashes in the name make it invalid.
        invalid_name = "ra//%s" % now

        extra_args = ['-a', '386']
        self.runScript(
            extra_args=extra_args,
            archive_name=invalid_name,
            exception_type=SoyuzScriptError,
            exception_text=(
                "Invalid destination archive name: '%s'" % invalid_name))

    def testInvalidSuite(self):
        """Try copy archive creation/population with a non-existent suite.

        A suite is a combination of a distro series and pocket e.g.
        hoary-updates or hardy-security.
        In the case where a non-existent suite is specified the script should
        abort with an appropriate error message.
        """
        now = int(time.time())
        invalid_suite = "suite/:/%s" % now
        extra_args = ['-a', '386']
        self.runScript(
            extra_args=extra_args,
            suite=invalid_suite,
            exception_type=PackageLocationError,
            exception_text="Could not find suite '%s'" % invalid_suite)

    def testInvalidUserName(self):
        """Try copy archive population with an invalid user name.

        The destination/copy archive will be created for some Launchpad user.
        If the user name passed is invalid the script should abort with an
        appropriate error message.
        """
        now = int(time.time())
        invalid_user = "user//%s" % now
        extra_args = ['-a', '386']
        self.runScript(
            extra_args=extra_args,
            user=invalid_user,
            exception_type=SoyuzScriptError,
            exception_text="Invalid user name: '%s'" % invalid_user)

    def testUnknownPackagesetName(self):
        """Try copy archive population with an unknown packageset name.

        The caller can request copying specific packagesets. We test
        what happens if they request a packageset that doesn't exist.
        """
        unknown_packageset = "unknown"
        extra_args = ['-a', '386', "--package-set", unknown_packageset]
        self.runScript(
            extra_args=extra_args,
            exception_type=PackageLocationError,
            exception_text="Could not find packageset No such package set"
            " (in the specified distro series): '%s'." % unknown_packageset)

    def testNonvirtualized(self):
        """--nonvirtualized means the archive won't require virtualization."""
        copy_archive = self.runScript(
            archive_name="copy-archive-test", exists_before=False,
            exists_after=True, nonvirtualized=True,
            extra_args=['-a', '386'])
        self.assertFalse(copy_archive.require_virtualized)

    def testPackagesetDelta(self):
        """Try to calculate the delta between two source package sets."""
        hoary = getUtility(IDistributionSet)['ubuntu']['hoary']

        # Verify that we have the right source packages in the sample data.
        self._verifyPackagesInSampleData(hoary)

        # Take a snapshot of ubuntu/hoary first.
        extra_args = ['-a', 'amd64']
        first_stage = self.runScript(
            extra_args=extra_args, exists_after=True,
            copy_archive_name='first-stage')
        self._verifyClonedSourcePackages(first_stage, hoary)

        # Now add a new package to ubuntu/hoary and update one.
        self._prepareMergeCopy()

        # Check which source packages are fresher or new in the second stage
        # archive.
        expected_output = (
            "INFO Fresher packages: 1\n"
            "INFO * alsa-utils (2.0 > 1.0.9a-4ubuntu1)\n"
            "INFO New packages: 1\n"
            "INFO * new-in-second-round (1.0)\n")

        extra_args = ['--package-set-delta']
        self.runScript(
            extra_args=extra_args, reason='', output_substr=expected_output,
            copy_archive_name=first_stage.name)

    def testMergeCopy(self):
        """Try repeated copy archive population (merge copy).

        In this (test) case an archive is populated twice and only fresher or
        new packages are copied to it.
        """
        hoary = getUtility(IDistributionSet)['ubuntu']['hoary']

        # Verify that we have the right source packages in the sample data.
        self._verifyPackagesInSampleData(hoary)

        # Take a snapshot of ubuntu/hoary first.
        extra_args = ['-a', 'amd64']
        first_stage = self.runScript(
            extra_args=extra_args, exists_after=True,
            copy_archive_name='first-stage')
        self._verifyClonedSourcePackages(first_stage, hoary)

        # Now add a new package to ubuntu/hoary and update one.
        self._prepareMergeCopy()

        # Take a snapshot of the modified ubuntu/hoary primary archive.
        second_stage = self.runScript(
            extra_args=extra_args, exists_after=True,
            copy_archive_name='second-stage')
        # Verify that the 2nd snapshot has the fresher and the new package.
        self._verifyClonedSourcePackages(
            second_stage, hoary,
            # The set of packages that were superseded in the target archive.
            obsolete=set(['alsa-utils 1.0.9a-4ubuntu1 in hoary']),
            # The set of packages that are new/fresher in the source archive.
            new=set([
                'alsa-utils 2.0 in hoary',
                'new-in-second-round 1.0 in hoary',
                ]))

        # Now populate a 3rd copy archive from the first ubuntu/hoary
        # snapshot.
        extra_args = ['-a', 'amd64', '--from-archive', first_stage.name]
        copy_archive = self.runScript(
            extra_args=extra_args, exists_after=True)
        self._verifyClonedSourcePackages(copy_archive, hoary)

        # Then populate the same copy archive from the 2nd snapshot.
        # This results in the copying of the fresher and of the new package.
        extra_args = [
            '--merge-copy', '--from-archive', second_stage.name]

        # We need to enable the copy archive before we can copy to it.
        copy_archive.enable()
        # An empty 'reason' string is passed to runScript() i.e. the latter
        # will not pass a '--reason' command line argument to the script which
        # is OK since this is a repeated population of an *existing* COPY
        # archive.
        copy_archive = self.runScript(
            extra_args=extra_args, copy_archive_name=copy_archive.name,
            reason='')
        self._verifyClonedSourcePackages(
            copy_archive, hoary,
            # The set of packages that were superseded in the target archive.
            obsolete=set(['alsa-utils 1.0.9a-4ubuntu1 in hoary']),
            # The set of packages that are new/fresher in the source archive.
            new=set([
                'alsa-utils 2.0 in hoary',
                'new-in-second-round 1.0 in hoary',
                ]))

    def testUnknownOriginArchive(self):
        """Try copy archive population with a unknown origin archive.

        This test should provoke a `SoyuzScriptError` exception.
        """
        extra_args = ['-a', 'amd64', '--from-archive', '9th-level-cache']
        self.runScript(
            extra_args=extra_args,
            exception_type=SoyuzScriptError,
            exception_text="Origin archive does not exist: '9th-level-cache'")

    def testUnknownOriginPPA(self):
        """Try copy archive population with an invalid PPA owner name.

        This test should provoke a `SoyuzScriptError` exception.
        """
        extra_args = ['-a', 'amd64', '--from-user', 'king-kong']
        self.runScript(
            extra_args=extra_args,
            exception_type=SoyuzScriptError,
            exception_text="No PPA for user: 'king-kong'")

    def testInvalidOriginArchiveName(self):
        """Try copy archive population with an invalid origin archive name.

        This test should provoke a `SoyuzScriptError` exception.
        """
        extra_args = [
            '-a', 'amd64', '--from-archive', '//']
        self.runScript(
            extra_args=extra_args,
            exception_type=SoyuzScriptError,
            exception_text="Invalid origin archive name: '//'")

    def testInvalidProcessorName(self):
        """Try copy archive population with an invalid architecture tag.

        This test should provoke a `SoyuzScriptError` exception.
        """
        extra_args = ['-a', 'wintel']
        self.runScript(
            extra_args=extra_args,
            exception_type=SoyuzScriptError,
            exception_text="Invalid architecture tag: 'wintel'")

    def testProcessorsForExistingArchives(self):
        """Try specifying processor names for existing archive.

        The user is not supposed to specify processor on the command
        line for existing copy archives. The processor will be read
        from the database instead. Please see also the end of the
        testMultipleArchTags test.

        This test should provoke a `SoyuzScriptError` exception.
        """
        extra_args = ['-a', '386', '-a', 'amd64']
        copy_archive = self.runScript(
            extra_args=extra_args, exists_before=False)

        extra_args = ['--merge-copy', '-a', '386', '-a', 'amd64']
        self.runScript(
            extra_args=extra_args, copy_archive_name=copy_archive.name,
            exception_type=SoyuzScriptError,
            exception_text=(
                'error: cannot specify architecture tags for *existing* '
                'archive.'))

    def testMissingCreationReason(self):
        """Try copy archive population without a copy archive creation reason.

        This test should provoke a `SoyuzScriptError` exception because the
        copy archive does not exist yet and will need to be created.

        This is different from a merge copy scenario where the destination
        copy archive exists already and hence no archive creation reason is
        needed.
        """
        extra_args = ['-a', 'amd64']
        self.runScript(
            # Pass an empty reason parameter string to indicate that no
            # '--reason' command line argument is to be provided.
            extra_args=extra_args, reason='',
            exception_type=SoyuzScriptError,
            exception_text=(
                'error: reason for copy archive creation not specified.'))

    def testMergecopyToMissingArchive(self):
        """Try merge copy to non-existent archive.

        This test should provoke a `SoyuzScriptError` exception because the
        copy archive does not exist yet and we specified the '--merge-copy'
        command line option. The latter specifies the repeated population of
        *existing* archives.
        """
        extra_args = ['--merge-copy', '-a', 'amd64']
        self.runScript(
            extra_args=extra_args,
            exception_type=SoyuzScriptError,
            exception_text=(
                'error: merge copy requested for non-existing archive.'))

    def testArchiveNameClash(self):
        """Try creating an archive with same name and distribution twice.

        This test should provoke a `SoyuzScriptError` exception because there
        is a uniqueness constraint based on (distribution, name) for all
        non-PPA archives i.e. we do not allow the creation of a second archive
        with the same name and distribution.
        """
        extra_args = ['-a', 'amd64']
        self.runScript(
            extra_args=extra_args, exists_after=True,
            copy_archive_name='hello-1')
        extra_args = ['-a', 'amd64']
        self.runScript(
            extra_args=extra_args,
            copy_archive_name='hello-1', exception_type=SoyuzScriptError,
            exception_text=(
                "error: archive 'hello-1' already exists for 'ubuntu'."))

    def testMissingProcessor(self):
        """Try copy archive population without a single architecture tag.

        This test should provoke a `SoyuzScriptError` exception.
        """
        self.runScript(
            exception_type=SoyuzScriptError,
            exception_text="error: architecture tags not specified.")

    def testBuildsPendingAndSuspended(self):
        """All builds in the new copy archive are pending and suspended."""

        def build_in_wrong_state(build):
            """True if the given build is not (pending and suspended)."""
            return not (
                build.status == BuildStatus.NEEDSBUILD and
                build.buildqueue_record.job.status == JobStatus.SUSPENDED)
        hoary = getUtility(IDistributionSet)['ubuntu']['hoary']

        # Verify that we have the right source packages in the sample data.
        self._verifyPackagesInSampleData(hoary)

        extra_args = ['-a', '386']
        archive = self.runScript(extra_args=extra_args, exists_after=True)

        # Make sure the right source packages were cloned.
        self._verifyClonedSourcePackages(archive, hoary)

        # Get the binary builds generated for the copy archive at hand.
        builds = list(getUtility(IBinaryPackageBuildSet).getBuildsForArchive(
            archive))
        # At least one binary build was generated for the target copy archive.
        self.assertTrue(len(builds) > 0)
        # Now check that the binary builds and their associated job records
        # are in the state expected:
        #   - binary build: pending
        #   - job: suspended
        builds_in_wrong_state = filter(build_in_wrong_state, builds)
        self.assertEqual(
            [], builds_in_wrong_state,
            "The binary builds generated for the target copy archive "
            "should all be pending and suspended. However, at least one of "
            "the builds is in the wrong state.")

    def testPrivateOriginArchive(self):
        """Try copying from a private archive.

        This test should provoke a `SoyuzScriptError` exception because
        presently copy archives can only be created as public archives.
        The copying of packages from private archives to public ones
        thus constitutes a security breach.
        """
        # We will make a private PPA and then attempt to copy from it.
        joe = self.factory.makePerson(name='joe')
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        self.factory.makeArchive(
            owner=joe, private=True, name="ppa", distribution=ubuntu)

        extra_args = ['--from-user', 'joe', '-a', 'amd64']
        self.runScript(
            extra_args=extra_args, exception_type=SoyuzScriptError,
            exception_text=(
                "Cannot copy from private archive ('joe/ppa')"))

    def testDisabledDestinationArchive(self):
        """Try copying to a disabled archive.

        This test should provoke a `SoyuzScriptError` exception because
        the destination archive is disabled.
        """
        # Create a copy archive, disable it and then attempt to copy to it.
        cprov = getUtility(IPersonSet).getByName('cprov')
        distro = getUtility(IDistributionSet).getByName('ubuntu')
        disabled_archive = getUtility(IArchiveSet).new(
            ArchivePurpose.COPY, cprov, name='disabled-copy-archive',
            distribution=distro, description='disabled-copy-archive test',
            enabled=False)

        extra_args = ['--from-user', 'cprov', '--merge-copy']
        self.runScript(
            copy_archive_name=disabled_archive.name, reason='',
            extra_args=extra_args, exception_type=SoyuzScriptError,
            exception_text='error: cannot copy to disabled archive')

    def _verifyClonedSourcePackages(
        self, copy_archive, series, obsolete=None, new=None):
        """Verify that the expected source packages have been cloned.

        The destination copy archive should be populated with the expected
        source packages.

        :type copy_archive: `Archive`
        :param copy_archive: the destination copy archive to check.
        :type series: `DistroSeries`
        :param series: the destination distro series.
        """
        # Make sure the source packages were cloned.
        target_set = set(self.expected_src_names)
        copy_src_names = self._getPendingPackageNames(copy_archive, series)
        if obsolete is not None:
            target_set -= obsolete
        if new is not None:
            target_set = target_set.union(new)
        self.assertEqual(copy_src_names, target_set)

    def _getPendingPackageNames(self, archive, series):
        sources = archive.getPublishedSources(
            distroseries=series, status=self.pending_statuses)
        return set(source.displayname for source in sources)

    def _prepareMergeCopy(self):
        """Add a fresher and a new package to ubuntu/hoary.

        This is used to test merge copy functionality."""
        test_publisher = SoyuzTestPublisher()
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        hoary = ubuntu.getSeries('hoary')
        test_publisher.addFakeChroots(hoary)
        test_publisher.setUpDefaultDistroSeries(hoary)
        test_publisher.getPubSource(
            sourcename="new-in-second-round", version="1.0",
            distroseries=hoary, archive=ubuntu.main_archive)
        test_publisher.getPubSource(
            sourcename="alsa-utils", version="2.0", distroseries=hoary,
            archive=ubuntu.main_archive)
        sources = ubuntu.main_archive.getPublishedSources(
            distroseries=hoary, status=self.pending_statuses,
            name=u'alsa-utils')
        for src in sources:
            if src.source_package_version != '2.0':
                src.supersede()
        LaunchpadZopelessLayer.txn.commit()

    def _verifyPackagesInSampleData(self, series, archive_name=None):
        """Verify that the expected source packages are in the sample data.

        :type series: `DistroSeries`
        :param series: the origin distro series.
        """
        if archive_name is None:
            archive = series.distribution.main_archive
        else:
            archive = getUtility(IArchiveSet).getByDistroPurpose(
                series.distribution, ArchivePurpose.COPY, archive)
        # These source packages will be copied to the copy archive.
        sources = archive.getPublishedSources(
            distroseries=series, status=self.pending_statuses)

        src_names = sorted(source.displayname for source in sources)
        # Make sure the source to be copied are the ones we expect (this
        # should break in case of a sample data change/corruption).
        self.assertEqual(src_names, self.expected_src_names)
