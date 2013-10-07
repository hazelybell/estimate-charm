# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from StringIO import StringIO
from textwrap import dedent

from zope.component import getUtility
from zope.security.interfaces import ForbiddenAttribute
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.soyuz.interfaces.processacceptedbugsjob import (
    IProcessAcceptedBugsJobSource,
    )
from lp.soyuz.scripts.processaccepted import (
    close_bugs_for_sourcepackagerelease,
    close_bugs_for_sourcepublication,
    )
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestClosingBugs(TestCaseWithFactory):
    """Test the various bug closing methods in processaccepted.py.

    Tests are currently spread around the codebase; this is an attempt to
    start a unification in a single file and those other tests need
    migrating here.
    See also:
        * lib/lp/soyuz/doc/closing-bugs-from-changelogs.txt
        * lib/lp/archiveuploader/tests/nascentupload-closing-bugs.txt
    """
    layer = LaunchpadZopelessLayer

    def makeChangelogWithBugs(self, spr, target_series=None):
        """Create a changelog for the passed sourcepackagerelease that has
        6 bugs referenced.

        :param spr: The sourcepackagerelease that needs a changelog.
        :param target_distro: the distribution context for the source package
            bug target.  If None, default to its uploaded distribution.

        :return: A tuple which is a list of (bug, bugtask)
        """
        # Make 4 bugs and corresponding bugtasks and put them in an array
        # as tuples.
        bugs = []
        for i in range(6):
            if target_series is None:
                target = spr.sourcepackage
            else:
                target = target_series.getSourcePackage(spr.sourcepackagename)
            bug = self.factory.makeBug()
            bugtask = self.factory.makeBugTask(target=target, bug=bug)
            bugs.append((bug, bugtask))
        # Make a changelog entry for a package which contains the IDs of
        # the 6 bugs separated across 3 releases.
        changelog = dedent("""
            foo (1.0-3) unstable; urgency=low

              * closes: %s, %s
              * lp: #%s, #%s

             -- Foo Bar <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000

            foo (1.0-2) unstable; urgency=low

              * closes: %s

             -- Foo Bar <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000

            foo (1.0-1) unstable; urgency=low

              * closes: %s

             -- Foo Bar <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000

            """ % (
            bugs[0][0].id,
            bugs[1][0].id,
            bugs[2][0].id,
            bugs[3][0].id,
            bugs[4][0].id,
            bugs[5][0].id,
            ))
        lfa = self.factory.makeLibraryFileAlias(content=changelog)
        removeSecurityProxy(spr).changelog = lfa
        self.layer.txn.commit()
        return bugs

    def test_close_bugs_for_sourcepackagerelease_with_no_changes_file(self):
        # If there's no changes file it should read the changelog_entry on
        # the sourcepackagerelease.

        spr = self.factory.makeSourcePackageRelease(changelog_entry="blah")
        bugs = self.makeChangelogWithBugs(spr)

        # Call the method and test it's closed the bugs.
        close_bugs_for_sourcepackagerelease(
            spr.upload_distroseries, spr, None, since_version="1.0-1")
        for bug, bugtask in bugs:
            if bug.id != bugs[5][0].id:
                self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask.status)
            else:
                self.assertEqual(BugTaskStatus.NEW, bugtask.status)

    def test__close_bugs_for_sourcepublication__uses_right_distro(self):
        # If a source was originally uploaded to a different distro,
        # closing bugs based on a publication of the same source in a new
        # distro should work.

        # Create a source package that was originally uploaded to one
        # distro and publish it in a second distro.
        spr = self.factory.makeSourcePackageRelease(changelog_entry="blah")
        target_distro = self.factory.makeDistribution()
        target_distroseries = self.factory.makeDistroSeries(target_distro)
        bugs = self.makeChangelogWithBugs(
            spr, target_series=target_distroseries)
        target_spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, distroseries=target_distroseries,
            archive=target_distro.main_archive,
            pocket=PackagePublishingPocket.RELEASE)

        # The test depends on this pre-condition.
        self.assertNotEqual(spr.upload_distroseries.distribution,
                            target_distroseries.distribution)

        close_bugs_for_sourcepublication(target_spph, since_version="1.0")

        for bug, bugtask in bugs:
            self.assertEqual(BugTaskStatus.FIXRELEASED, bugtask.status)


class TestClosingPrivateBugs(TestCaseWithFactory):
    # The distroseries +queue page can close private bugs when accepting
    # packages.

    layer = DatabaseFunctionalLayer

    def test_close_bugs_for_sourcepackagerelease_with_private_bug(self):
        """close_bugs_for_sourcepackagerelease works with private bugs."""
        changes_file_template = "Format: 1.7\nLaunchpad-bugs-fixed: %s\n"
        # changelog_entry is required for an assertion inside the function
        # we're testing.
        spr = self.factory.makeSourcePackageRelease(changelog_entry="blah")
        archive_admin = self.factory.makePerson()
        series = spr.upload_distroseries
        dsp = series.distribution.getSourcePackage(spr.sourcepackagename)
        bug = self.factory.makeBug(
            target=dsp, information_type=InformationType.USERDATA)
        changes = StringIO(changes_file_template % bug.id)

        with person_logged_in(archive_admin):
            # The archive admin user can't normally see this bug.
            self.assertRaises(ForbiddenAttribute, bug, 'status')
            # But the bug closure should work.
            close_bugs_for_sourcepackagerelease(series, spr, changes)

        # Rather than closing the bugs immediately, this creates a
        # ProcessAcceptedBugsJob.
        with celebrity_logged_in("admin"):
            self.assertEqual(BugTaskStatus.NEW, bug.default_bugtask.status)
        job_source = getUtility(IProcessAcceptedBugsJobSource)
        [job] = list(job_source.iterReady())
        self.assertEqual(series, job.distroseries)
        self.assertEqual(spr, job.sourcepackagerelease)
        self.assertEqual([bug.id], job.bug_ids)
