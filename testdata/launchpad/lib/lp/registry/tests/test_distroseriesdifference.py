# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Model tests for the DistroSeriesDifference class."""

__metaclass__ = type

from storm.exceptions import IntegrityError
from storm.store import Store
import transaction
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.errors import (
    DistroSeriesDifferenceError,
    NotADerivedSeriesError,
    )
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifference,
    IDistroSeriesDifferenceSource,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.distroseriesdifference import (
    get_comment_with_status_change,
    most_recent_comments,
    most_recent_publications,
    )
from lp.services.propertycache import get_property_cache
from lp.services.webapp.authorization import check_permission
from lp.soyuz.enums import PackageDiffStatus
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.soyuz.model.packagesetsources import PackagesetSources
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class DistroSeriesDifferenceTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_implements_interface(self):
        # The implementation implements the interface correctly.
        ds_diff = self.factory.makeDistroSeriesDifference()
        # Flush the store to ensure db constraints are triggered.
        Store.of(ds_diff).flush()

        verifyObject(IDistroSeriesDifference, ds_diff)

    def test_source_implements_interface(self):
        # The utility for creating differences implements its interface.
        utility = getUtility(IDistroSeriesDifferenceSource)

        verifyObject(IDistroSeriesDifferenceSource, utility)

    def test_new_non_derived_series(self):
        # A DistroSeriesDifference cannot be created with a non-derived
        # series.
        distro_series = self.factory.makeDistroSeries()
        source_package_name = self.factory.makeSourcePackageName('myfoo')
        distroseriesdifference_factory = getUtility(
            IDistroSeriesDifferenceSource)

        self.assertRaises(
            NotADerivedSeriesError, distroseriesdifference_factory.new,
            distro_series, source_package_name,
            self.factory.makeDistroSeries())

    def test_source_pub(self):
        # The related source pub is returned for the derived series.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew")

        self.assertEqual(
            'foonew', ds_diff.source_pub.source_package_name)
        self.assertEqual(
            ds_diff.derived_series, ds_diff.source_pub.distroseries)

    def test_source_pub_gets_latest_pending(self):
        # The most recent publication is always returned, even if its pending.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew")
        pending_pub = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING)

        self.assertEqual(pending_pub, ds_diff.source_pub)

    def test_source_pub_returns_none(self):
        # None is returned when there is no source pub.
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=(
                DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES))

        self.assertIs(None, ds_diff.source_pub)

    def test_parent_source_pub(self):
        # The related source pub for the parent distro series is returned.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew")

        self.assertEqual(
            'foonew', ds_diff.parent_source_pub.source_package_name)
        self.assertEqual(
            ds_diff.parent_series, ds_diff.parent_source_pub.distroseries)

    def test_parent_source_pub_gets_latest_pending(self):
        # The most recent publication is always returned, even if its pending.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew")
        pending_pub = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.parent_series,
            status=PackagePublishingStatus.PENDING)

        self.assertEqual(pending_pub, ds_diff.parent_source_pub)

    def test_source_version(self):
        # The version of the source in the derived series is returned.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew")

        self.assertEqual(
            ds_diff.source_pub.source_package_version, ds_diff.source_version)

    def test_source_version_none(self):
        # None is returned for source_version when there is no source pub.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            difference_type=(
                DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES))

        self.assertEqual(None, ds_diff.source_version)

    def test_update_resolves_difference(self):
        # Status is set to resolved when versions match.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions={
                'parent': '1.0',
                'derived': '0.9',
                })
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING,
            version='1.0')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceStatus.RESOLVED,
            ds_diff.status)

    def test_update_nulls_diffs_for_resolved(self):
        # Resolved differences should null out the package_diff and
        # parent_package_diff fields so the libraryfilealias gets
        # considered for GC later.
        derived_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.2'])
        parent_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.3'])
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '1.2',
            'parent': '1.3',
            'base': '1.0',
            },
            changelogs={
                'derived': derived_changelog,
                'parent': parent_changelog,
            })
        person = self.factory.makePerson()
        with person_logged_in(person):
            ds_diff.requestPackageDiffs(person)
        # The pre-test state is that there are diffs present:
        self.assertIsNot(None, ds_diff.package_diff)
        self.assertIsNot(None, ds_diff.parent_package_diff)

        # Resolve the DSD by making the same package version published
        # in parent and derived.
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING,
            version='1.4')
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.parent_series,
            status=PackagePublishingStatus.PENDING,
            version='1.4')

        # Packagediffs should be gone now.
        was_updated = ds_diff.update()
        self.assertTrue(was_updated)
        self.assertEqual(
            ds_diff.status, DistroSeriesDifferenceStatus.RESOLVED)
        self.assertIs(None, ds_diff.package_diff)
        self.assertIs(None, ds_diff.parent_package_diff)

    def test_parent_update_re_opens_difference(self):
        # The status of a resolved difference will be updated to
        # NEEDS_ATTENTION with parent uploads.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions=dict(parent='1.0', derived='1.0'),
            status=DistroSeriesDifferenceStatus.RESOLVED)
        # Publish package in the parent series.
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.parent_series,
            status=PackagePublishingStatus.PENDING,
            version='1.1')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            ds_diff.status)

    def test_child_update_re_opens_difference(self):
        # The status of a resolved difference will updated to
        # BLACKLISTED_CURRENT with child uploads.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions=dict(parent='1.0', derived='1.0'),
            status=DistroSeriesDifferenceStatus.RESOLVED)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING,
            version='1.1')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            ds_diff.status)

    def test_update_new_parent_version_doesnt_change_status(self):
        # Uploading a new (different) parent_version does not update the
        # status of the record, but the version is updated.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions={
                'parent': '1.0',
                'derived': '0.9',
                })
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.parent_series,
            status=PackagePublishingStatus.PENDING,
            version='1.1')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            ds_diff.status)
        self.assertEqual('1.1', ds_diff.parent_source_version)

    def test_update_changes_type(self):
        # The type of difference is updated when appropriate.
        # In this case, a package that was previously only in the
        # derived series (UNIQUE_TO_DERIVED_SERIES), is uploaded
        # to the parent series with a different version.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions={
                'derived': '0.9',
                },
            difference_type=(
                DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES))
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.parent_series,
            status=PackagePublishingStatus.PENDING,
            version='1.1')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceType.DIFFERENT_VERSIONS,
            ds_diff.difference_type)

    def test_update_removes_version_blacklist(self):
        # A blacklist on a version of a package is removed when a new
        # version is uploaded to the derived series.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions={
                'derived': '0.9',
                },
            difference_type=(
                DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES),
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING,
            version='1.1')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            ds_diff.status)

    def test_update_does_not_remove_permanent_blacklist(self):
        # A permanent blacklist is not removed when a new version
        # is uploaded, even if it resolves the difference (as later
        # uploads could re-create a difference, and we want to keep
        # the blacklist).
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew",
            versions={
                'derived': '0.9',
                'parent': '1.0',
                },
            status=DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING,
            version='1.0')

        was_updated = ds_diff.update()

        self.assertTrue(was_updated)
        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS,
            ds_diff.status)

    def test_title(self):
        # The title is a friendly description of the difference.
        parent_series = self.factory.makeDistroSeries(name="lucid")
        derived_series = self.factory.makeDistroSeries(name="derilucid")
        self.factory.makeDistroSeriesParent(
            derived_series=derived_series, parent_series=parent_series)
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew", derived_series=derived_series,
            versions={
                'parent': '1.0',
                'derived': '0.9',
                })

        self.assertEqual(
            "Difference between distroseries 'Lucid' and 'Derilucid' "
            "for package 'foonew' (1.0/0.9)",
            ds_diff.title)

    def test_addComment(self):
        # Adding a comment creates a new DistroSeriesDifferenceComment
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foonew")

        person = self.factory.makePerson()
        with person_logged_in(person):
            dsd_comment = ds_diff.addComment(
                person, "Wait until version 2.1")

        self.assertEqual(ds_diff, dsd_comment.distro_series_difference)

    def test_getComments(self):
        # All comments for this difference are returned with the
        # most recent comment first.
        ds_diff = self.factory.makeDistroSeriesDifference()

        person = self.factory.makePerson()
        with person_logged_in(person):
            dsd_comment = ds_diff.addComment(
                person, "Wait until version 2.1")
            dsd_comment_2 = ds_diff.addComment(
                person, "Wait until version 2.1")

        self.assertEqual(
            [dsd_comment_2, dsd_comment], list(ds_diff.getComments()))

    def test_latest_comment(self):
        # latest_comment is a property containing the most recent comment.
        ds_diff = self.factory.makeDistroSeriesDifference()

        with person_logged_in(ds_diff.owner):
            comments = [
                ds_diff.addComment(
                    ds_diff.owner, "Wait until version 2.1"),
                ds_diff.addComment(
                    ds_diff.owner, "Wait until version 2.1"),
                ]

        self.assertEqual(comments[-1], ds_diff.latest_comment)

    def test_addComment_for_owners(self):
        # Comments can be added by any of the owners of the derived
        # series.
        ds_diff = self.factory.makeDistroSeriesDifference()

        person = self.factory.makePerson()
        with person_logged_in(person):
            self.assertTrue(check_permission('launchpad.Edit', ds_diff))
            ds_diff.addComment(ds_diff.derived_series.owner, "Boo")

    def _setupPackageSets(self, ds_diff, distroseries, nb_packagesets):
        # Helper method to create packages sets.
        packagesets = []
        with celebrity_logged_in('admin'):
            for i in range(nb_packagesets):
                ps = self.factory.makePackageset(
                    packages=[ds_diff.source_package_name],
                    distroseries=distroseries)
                packagesets.append(ps)
        return packagesets

    def test_parent_packagesets(self):
        # All parent's packagesets are returned ordered alphabetically.
        ds_diff = self.factory.makeDistroSeriesDifference()
        packagesets = self._setupPackageSets(
            ds_diff, ds_diff.parent_series, 5)
        parent_packagesets = ds_diff.parent_packagesets
        self.assertEquals(
            sorted([packageset.name for packageset in packagesets]),
            [packageset.name for packageset in parent_packagesets])

    def test_packagesets(self):
        # All the packagesets are returned ordered alphabetically.
        ds_diff = self.factory.makeDistroSeriesDifference()
        packagesets = self._setupPackageSets(
            ds_diff, ds_diff.derived_series, 5)
        self.assertEquals(
            sorted([packageset.name for packageset in packagesets]),
            [packageset.name for packageset in ds_diff.packagesets])

    def test_blacklist_unauthorised(self):
        # If you're not an archive admin, you don't get to blacklist or
        # unblacklist.
        ds_diff = self.factory.makeDistroSeriesDifference()
        random_joe = self.factory.makePerson()
        with person_logged_in(random_joe):
            self.assertRaises(Unauthorized, getattr, ds_diff, 'blacklist')
            self.assertRaises(Unauthorized, getattr, ds_diff, 'unblacklist')

    def test_blacklist_default(self):
        # By default the current version is blacklisted.
        ds_diff = self.factory.makeDistroSeriesDifference()
        admin = self.factory.makeArchiveAdmin(
            ds_diff.derived_series.main_archive)

        with person_logged_in(admin):
            ds_diff.blacklist(admin)

        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            ds_diff.status)

    def test_blacklist_all(self):
        # All versions are blacklisted with the all=True param.
        ds_diff = self.factory.makeDistroSeriesDifference()
        admin = self.factory.makeArchiveAdmin(
            ds_diff.derived_series.main_archive)

        with person_logged_in(admin):
            ds_diff.blacklist(admin, all=True)

        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS,
            ds_diff.status)

    def test_unblacklist(self):
        # Unblacklisting will return to NEEDS_ATTENTION by default.
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)
        admin = self.factory.makeArchiveAdmin(
            ds_diff.derived_series.main_archive)

        with person_logged_in(admin):
            ds_diff.unblacklist(admin)

        self.assertEqual(
            DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            ds_diff.status)

    def test_unblacklist_resolved(self):
        # Status is resolved when unblacklisting a now-resolved difference.
        ds_diff = self.factory.makeDistroSeriesDifference(
            versions={
                'derived': '0.9',
                'parent': '1.0',
                },
            status=DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS)
        self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=ds_diff.derived_series,
            status=PackagePublishingStatus.PENDING,
            version='1.0')

        admin = self.factory.makeArchiveAdmin(
            ds_diff.derived_series.main_archive)
        with person_logged_in(admin):
            ds_diff.unblacklist(admin)

        self.assertEqual(
            DistroSeriesDifferenceStatus.RESOLVED,
            ds_diff.status)

    def test_get_comment_with_status_change(self):
        # Test the new comment string created to describe a status
        # change.
        old_status = DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS
        new_status = DistroSeriesDifferenceStatus.NEEDS_ATTENTION
        new_comment = get_comment_with_status_change(
            old_status, new_status, 'simple comment')

        self.assertEqual(
            'simple comment\n\nIgnored: %s => %s' % (
                old_status.title, new_status.title),
            new_comment)

    def assertDSDComment(self, ds_diff, dsd_comment, comment_string):
        self.assertEqual(
            dsd_comment,
            ds_diff.latest_comment)
        self.assertEqual(
            comment_string,
            ds_diff.latest_comment.message.text_contents)

    def test_unblacklist_creates_comment(self):
        old_status = DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=old_status,
            source_package_name_str="foo")
        admin = self.factory.makeArchiveAdmin(
            ds_diff.derived_series.main_archive)
        with person_logged_in(admin):
            dsd_comment = ds_diff.unblacklist(
                admin, "Ok now")
        new_status = DistroSeriesDifferenceStatus.NEEDS_ATTENTION
        expected_comment = 'Ok now\n\nIgnored: %s => %s' % (
                old_status.title, new_status.title)

        self.assertDSDComment(ds_diff, dsd_comment, expected_comment)

    def test_blacklist_creates_comment(self):
        old_status = DistroSeriesDifferenceStatus.NEEDS_ATTENTION
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=old_status,
            source_package_name_str="foo")
        admin = self.factory.makeArchiveAdmin(
            ds_diff.derived_series.main_archive)
        with person_logged_in(admin):
            dsd_comment = ds_diff.blacklist(
                admin, True, "Wait until version 2.1")
        new_status = DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS
        expected_comment = 'Wait until version 2.1\n\nIgnored: %s => %s' % (
                old_status.title, new_status.title)

        self.assertDSDComment(ds_diff, dsd_comment, expected_comment)

    def test_source_package_name_unique_for_derived_series(self):
        # We cannot create two differences for the same derived series
        # for the same package.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str="foo")
        self.assertRaises(
            IntegrityError, self.factory.makeDistroSeriesDifference,
            derived_series=ds_diff.derived_series,
            source_package_name_str="foo")

    def test_cached_properties(self):
        # The source and parent publication properties are cached on the
        # model.
        ds_diff = self.factory.makeDistroSeriesDifference()
        ds_diff.source_pub
        ds_diff.parent_source_pub

        cache = get_property_cache(ds_diff)

        self.assertContentEqual(
            ['source_pub', 'parent_source_pub'], cache)

    def test_base_version_none(self):
        # The attribute is set to None if there is no common base version.
        # Publish different versions in the series.
        dsp = self.factory.makeDistroSeriesParent()
        source_package_name = self.factory.getOrMakeSourcePackageName('foo')
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.derived_series,
            version='1.0deri1',
            sourcepackagename=source_package_name,
            status=PackagePublishingStatus.PUBLISHED)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series,
            version='1.0ubu2',
            sourcepackagename=source_package_name,
            status=PackagePublishingStatus.PUBLISHED)
        ds_diff = self.factory.makeDistroSeriesDifference()

        self.assertIs(None, ds_diff.base_version)

    def test_base_version_multiple(self):
        # The latest common base version is set as the base-version.
        dsp = self.factory.makeDistroSeriesParent()
        self.factory.getOrMakeSourcePackageName('foo')
        # Create changelogs for both.
        changelog_lfa = self.factory.makeChangelog('foo', ['1.2', '1.1'])
        parent_changelog_lfa = self.factory.makeChangelog('foo', ['1.1'])
        transaction.commit()  # Yay, librarian.

        ds_diff = self.factory.makeDistroSeriesDifference(
            derived_series=dsp.derived_series, source_package_name_str='foo',
            versions={
                'derived': '1.2',
                'parent': '1.3',
                },
            changelogs={
                'derived': changelog_lfa,
                'parent': parent_changelog_lfa})

        self.assertEqual('1.1', ds_diff.base_version)

    def test_base_version_invalid(self):
        # If the maximum base version is invalid, it is discarded and not
        # set as the base version.
        dsp = self.factory.makeDistroSeriesParent()
        self.factory.getOrMakeSourcePackageName('foo')
        # Create changelogs for both.
        changelog_lfa = self.factory.makeChangelog(
            'foo', ['1:2.0-1', 'a1:1.8.8-070403-1~priv1', '1:1.7-1'])
        parent_changelog_lfa = self.factory.makeChangelog(
            'foo', ['1:2.0-2', 'a1:1.8.8-070403-1~priv1', '1:1.7-1'])
        transaction.commit()  # Yay, librarian.

        ds_diff = self.factory.makeDistroSeriesDifference(
            derived_series=dsp.derived_series, source_package_name_str='foo',
            versions={
                'derived': '1:2.0-1',
                'parent': '1:2.0-2',
                },
            changelogs={
                'derived': changelog_lfa,
                'parent': parent_changelog_lfa})

        self.assertEqual('1:1.7-1', ds_diff.base_version)

    def test_base_source_pub_none(self):
        # None is simply returned if there is no base version.
        ds_diff = self.factory.makeDistroSeriesDifference()

        self.assertIs(None, ds_diff.base_version)
        self.assertIs(None, ds_diff.base_source_pub)

    def test_base_source_pub(self):
        # The publication in the parent series with the base version is
        # returned.
        derived_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.2'])
        parent_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.3'])
        transaction.commit()  # Yay, librarian.

        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '1.2',
            'parent': '1.3',
            'base': '1.0',
            },
            changelogs={
                'derived': derived_changelog,
                'parent': parent_changelog,
            })

        base_pub = ds_diff.base_source_pub
        self.assertEqual('1.0', base_pub.source_package_version)
        self.assertEqual(ds_diff.parent_series, base_pub.distroseries)

    def test_base_source_pub_not_published(self):
        # If the base version isn't published, the base version is
        # calculated, but the source publication isn't set.
        derived_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.2'])
        parent_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.3'])
        transaction.commit()  # Yay, librarian.

        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '1.2',
            'parent': '1.3',
            },
            changelogs={
                'derived': derived_changelog,
                'parent': parent_changelog,
            })
        self.assertEqual('1.0', ds_diff.base_version)
        self.assertIs(None, ds_diff.base_source_pub)

    def test_base_source_pub_only_in_child(self):
        # If the base version is only published in the child distroseries,
        # the base source publication is still located and returned.
        derived_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.2'])
        parent_changelog = self.factory.makeChangelog(
            versions=['1.0', '1.3'])
        transaction.commit()  # Yay, librarian.

        ds_diff = self.factory.makeDistroSeriesDifference(
            versions={
                'derived': '1.2',
                'parent': '1.3',
            },
            changelogs={
                'derived': derived_changelog,
                'parent': parent_changelog,
            })

        # Passing in a base version to makeDistroSeriesDifference() creates
        # it in both distroseries, which we don't want, so we need to do it
        # ourselves.
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=ds_diff.source_package_name, version='1.0')
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=ds_diff.derived_series, sourcepackagerelease=spr,
            status=PackagePublishingStatus.SUPERSEDED)
        self.assertEqual('1.0', ds_diff.base_version)
        self.assertEqual(
            ds_diff.derived_series, ds_diff.base_source_pub.distroseries)

    def _setupDSDsWithChangelog(self, derived_versions, parent_versions,
                                status=None):
        # Helper to create DSD with changelogs.
        # {derived,parent}_versions must be ordered (e.g. ['1.1',
        # '1.2', '1.3']).
        if status is None:
            status = DistroSeriesDifferenceStatus.NEEDS_ATTENTION
        derived_changelog = self.factory.makeChangelog(
            versions=derived_versions)
        parent_changelog = self.factory.makeChangelog(
            versions=parent_versions)
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=status,
            versions={
                'derived': derived_versions[-1],
                'parent': parent_versions[-1],
                'base': derived_versions[0],
            },
            changelogs={
                'derived': derived_changelog,
                'parent': parent_changelog,
            })
        return ds_diff

    def test_requestPackageDiffs(self):
        # IPackageDiffs are created for the corresponding versions.
        ds_diff = self._setupDSDsWithChangelog(
            ['1.0', '1.2'], ['1.0', '1.3'])
        person = self.factory.makePerson()
        with person_logged_in(person):
            ds_diff.requestPackageDiffs(person)

        self.assertEqual(
            '1.2', ds_diff.package_diff.to_source.version)
        self.assertEqual(
            '1.3', ds_diff.parent_package_diff.to_source.version)
        self.assertEqual(
            '1.0', ds_diff.package_diff.from_source.version)
        self.assertEqual(
            '1.0', ds_diff.parent_package_diff.from_source.version)

    def test_requestPackageDiffs_child_is_base(self):
        # When the child has the same version as the base version, when
        # diffs are requested, child diffs aren't.
        ds_diff = self._setupDSDsWithChangelog(
            ['0.1-1'], ['0.1-1', '0.1-2'])
        person = self.factory.makePerson()
        with person_logged_in(person):
            ds_diff.requestPackageDiffs(person)

        self.assertIs(None, ds_diff.package_diff)
        self.assertIsNot(None, ds_diff.parent_package_diff)

    def test_requestPackageDiffs_parent_is_base(self):
        # When the parent has the same version as the base version, when
        # diffs are requested, parent diffs aren't.
        ds_diff = self._setupDSDsWithChangelog(
            ['0.1-1', '0.1-2'], ['0.1-1'])
        person = self.factory.makePerson()
        with person_logged_in(person):
            ds_diff.requestPackageDiffs(person)

        self.assertIsNot(None, ds_diff.package_diff)
        self.assertIs(None, ds_diff.parent_package_diff)

    def test_requestPackageDiffs_with_resolved_DSD(self):
        # Diffs can't be requested for DSDs that are RESOLVED.
        ds_diff = self._setupDSDsWithChangelog(
            ['0.1-1'], ['0.1-1'],
            status=DistroSeriesDifferenceStatus.RESOLVED)
        person = self.factory.makePerson()
        with person_logged_in(person):
            self.assertRaisesWithContent(
                DistroSeriesDifferenceError,
                "Can not generate package diffs for a resolved difference.",
                ds_diff.requestPackageDiffs, person)

    def test_package_diff_urls_none(self):
        # URLs to the package diffs are only present when the diffs
        # have been generated.
        ds_diff = self.factory.makeDistroSeriesDifference()

        self.assertEqual(None, ds_diff.package_diff_url)
        self.assertEqual(None, ds_diff.parent_package_diff_url)

    def test_source_package_release_pending(self):
        # source_package_release returns the package release of version
        # source_version with status PUBLISHED or PENDING.
        dsp = self.factory.makeDistroSeriesParent()
        source_package_name = self.factory.getOrMakeSourcePackageName('foo')
        versions = {'derived': u'1.2', 'parent': u'1.3'}

        ds_diff = self.factory.makeDistroSeriesDifference(
            derived_series=dsp.derived_series,
            source_package_name_str=source_package_name.name,
            versions=versions)

        # Create pending source package releases.
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.derived_series,
            version='1.4',
            sourcepackagename=source_package_name,
            status=PackagePublishingStatus.PENDING)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.parent_series,
            version='1.5',
            sourcepackagename=source_package_name,
            status=PackagePublishingStatus.PENDING)

        # Manually change the diff's source_version and
        # parent_source_version.
        naked_ds_diff = removeSecurityProxy(ds_diff)
        naked_ds_diff.source_version = '1.4'
        naked_ds_diff.parent_source_version = '1.5'

        self.assertEqual('1.4', ds_diff.source_package_release.version)
        self.assertEqual(
            '1.5', ds_diff.parent_source_package_release.version)

    def createPublication(self, spn, versions, distroseries,
                          status=PackagePublishingStatus.PUBLISHED):
        changelog_lfa = self.factory.makeChangelog(spn.name, versions)
        transaction.commit()  # Yay, librarian.
        spr = self.factory.makeSourcePackageRelease(
            sourcepackagename=spn, version=versions[0],
            changelog=changelog_lfa)
        return self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr, distroseries=distroseries,
            status=status, pocket=PackagePublishingPocket.RELEASE)

    def test_existing_packagediff_is_linked_when_dsd_created(self):
        # When a relevant packagediff already exists, it is linked to the
        # DSD when it is created.
        dsp = self.factory.makeDistroSeriesParent()
        spn = self.factory.getOrMakeSourcePackageName(
            name=self.factory.getUniqueString())
        self.createPublication(
            spn, ['1.2-1', '1.0-1'], dsp.parent_series)
        spph = self.createPublication(
            spn, ['1.1-1', '1.0-1'], dsp.derived_series)
        base_spph = self.createPublication(
            spn, ['1.0-1'], dsp.derived_series,
            status=PackagePublishingStatus.SUPERSEDED)
        pd = self.factory.makePackageDiff(
            from_source=base_spph.sourcepackagerelease,
            to_source=spph.sourcepackagerelease)
        # factory.makeDistroSeriesDifference() will always create
        # publications to be helpful. We don't need the help in this case.
        dsd = getUtility(IDistroSeriesDifferenceSource).new(
            dsp.derived_series, spn, dsp.parent_series)
        self.assertEqual(pd, dsd.package_diff)

    def _initDiffWithMultiplePendingPublications(self, versions, parent):
        ds_diff = self.factory.makeDistroSeriesDifference(versions=versions)
        if parent:
            series = ds_diff.parent_series
            version = versions.get('parent')
        else:
            series = ds_diff.derived_series
            version = versions.get('derived')
        pub1 = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=series,
            status=PackagePublishingStatus.PENDING,
            version=version)
        pub2 = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagename=ds_diff.source_package_name,
            distroseries=series,
            status=PackagePublishingStatus.PENDING,
            version=version)
        return ds_diff, pub1, pub2

    def test_multiple_pending_publications_derived(self):
        # If multiple (PENDING) publications are present in the derived
        # series, the most recent is returned.
        ds_diff, _, pub = self._initDiffWithMultiplePendingPublications(
            versions={'derived': '1.0'},
            parent=False)
        self.assertEqual(
            pub,
            ds_diff.source_package_release.publishings[0])

    def test_multiple_pending_publications_parent(self):
        # If multiple (PENDING) publications are present in the parent
        # series, the most recent is returned.
        ds_diff, _, pub = self._initDiffWithMultiplePendingPublications(
            versions={'parent': '1.0'},
            parent=True)
        self.assertEqual(
            pub,
            ds_diff.parent_source_package_release.publishings[0])

    def test_source_package_release_superseded(self):
        # If the publication is not actively published, it is still returned
        # by source_package_release()
        dsp = self.factory.makeDistroSeriesParent()
        spn = self.factory.makeSourcePackageName()
        spph = self.factory.makeSourcePackagePublishingHistory(
            distroseries=dsp.derived_series,
            archive=dsp.derived_series.main_archive, sourcepackagename=spn,
            status=PackagePublishingStatus.SUPERSEDED)
        dsd = getUtility(IDistroSeriesDifferenceSource).new(
            dsp.derived_series, spn, dsp.parent_series)
        spr = dsd.source_package_release
        self.assertEqual(dsp.derived_series, spr.distroseries)
        self.assertEqual(spph.sourcepackagerelease, spr.sourcepackagerelease)

    def test_package_diff_urls(self):
        # Only completed package diffs have urls.
        ds_diff = self.factory.makeDistroSeriesDifference()
        naked_dsdiff = removeSecurityProxy(ds_diff)
        naked_dsdiff.package_diff = self.factory.makePackageDiff(
            status=PackageDiffStatus.PENDING)
        naked_dsdiff.parent_package_diff = self.factory.makePackageDiff()

        self.assertEqual(None, ds_diff.package_diff_url)
        self.assertTrue(ds_diff.parent_package_diff_url is not None)


class DistroSeriesDifferenceSourceTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeDifferencesForAllDifferenceTypes(self, derived_series):
        """Create DSDs of all types for `derived_series`."""
        return dict(
            (diff_type, self.factory.makeDistroSeriesDifference(
                derived_series, difference_type=diff_type))
            for diff_type in DistroSeriesDifferenceType.items)

    def makeDifferencesForAllStatuses(self, derived_series):
        """Create DSDs of all statuses for `derived_series`."""
        return dict(
            (status, self.factory.makeDistroSeriesDifference(
                derived_series, status=status))
            for status in DistroSeriesDifferenceStatus.items)

    def makeDerivedSeries(self, derived_series=None):
        """Create a derived `DistroSeries`."""
        dsp = self.factory.makeDistroSeriesParent(
            derived_series=derived_series)
        return dsp.derived_series

    def makeVersionDifference(self, derived_series=None, changed_parent=False,
                              changed_child=False, status=None):
        """Create a `DistroSeriesDifference` between package versions.

        The differing package will exist in both the parent series and in the
        child.

        :param derived_series: Optional `DistroSeries` that the difference is
            for.  If not given, one will be created.
        :param changed_parent: Whether the difference should show a change in
            the parent's version of the package.
        :param changed_child: Whether the difference should show a change in
            the child's version of the package.
        :param status: Optional status for the `DistroSeriesDifference`.  If
            not given, defaults to `NEEDS_ATTENTION`.
        """
        if status is None:
            status = DistroSeriesDifferenceStatus.NEEDS_ATTENTION
        base_version = "1.%d" % self.factory.getUniqueInteger()
        versions = dict.fromkeys(('base', 'parent', 'derived'), base_version)
        if changed_parent:
            versions['parent'] += "-%s" % self.factory.getUniqueString()
        if changed_child:
            versions['derived'] += "-%s" % self.factory.getUniqueString()
        return self.factory.makeDistroSeriesDifference(
            derived_series=derived_series, versions=versions, status=status,
            set_base_version=True)

    def test_implements_interface(self):
        self.assertProvides(
            getUtility(IDistroSeriesDifferenceSource),
            IDistroSeriesDifferenceSource),

    def test_getForDistroSeries_default(self):
        # By default all differences for the given series are returned.
        series = self.makeDerivedSeries()
        dsd = self.factory.makeDistroSeriesDifference(series)
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual([dsd], dsd_source.getForDistroSeries(series))

    def test_getForDistroSeries_filters_by_distroseries(self):
        # Differences for other series are not included.
        self.factory.makeDistroSeriesDifference()
        other_series = self.makeDerivedSeries()
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [], dsd_source.getForDistroSeries(other_series))

    def test_getForDistroSeries_does_not_filter_dsd_type_by_default(self):
        # If no difference_type is given, getForDistroSeries returns
        # DSDs of all types (missing in derived series, different
        # versions, or unique to derived series).
        series = self.makeDerivedSeries()
        dsds = self.makeDifferencesForAllDifferenceTypes(series)
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            dsds.values(), dsd_source.getForDistroSeries(series))

    def test_getForDistroSeries_filters_by_type(self):
        # Only differences for the specified types are returned.
        series = self.makeDerivedSeries()
        dsds = self.makeDifferencesForAllDifferenceTypes(series)
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        wanted_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        self.assertContentEqual(
            [dsds[wanted_type]],
            dsd_source.getForDistroSeries(
                series, difference_type=wanted_type))

    def test_getForDistroSeries_includes_all_statuses_by_default(self):
        # If no status is given, getForDistroSeries returns DSDs of all
        # statuses.
        series = self.makeDerivedSeries()
        dsds = self.makeDifferencesForAllStatuses(series)
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            dsds.values(), dsd_source.getForDistroSeries(series))

    def test_getForDistroSeries_filters_by_status(self):
        # A single status can be used to filter results.
        series = self.makeDerivedSeries()
        dsds = self.makeDifferencesForAllStatuses(series)
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        wanted_status = DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT
        self.assertContentEqual(
            [dsds[wanted_status]],
            dsd_source.getForDistroSeries(series, status=wanted_status))

    def test_getForDistroSeries_filters_by_multiple_statuses(self):
        # Multiple statuses can be passed for filtering.
        series = self.makeDerivedSeries()
        dsds = self.makeDifferencesForAllStatuses(series)
        wanted_statuses = (
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            )
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsds[status] for status in wanted_statuses],
            dsd_source.getForDistroSeries(series, status=wanted_statuses))

    def test_getForDistroSeries_matches_by_package_name(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        package_name = dsd.source_package_name.name
        source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsd],
            source.getForDistroSeries(series, name_filter=package_name))

    def test_getForDistroSeries_matches_by_packageset_name(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        packageset = self.factory.makePackageset(
            distroseries=series, packages=[dsd.source_package_name])
        packageset_name = packageset.name
        source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsd],
            source.getForDistroSeries(series, name_filter=packageset_name))

    def test_getForDistroSeries_filters_by_package_and_packageset_name(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        other_name = self.factory.getUniqueUnicode()
        source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [],
            source.getForDistroSeries(series, name_filter=other_name))

    def test_getForDistroSeries_ignores_parent_packagesets(self):
        dsd = self.factory.makeDistroSeriesDifference()
        series = dsd.derived_series
        packageset = self.factory.makePackageset(
            distroseries=dsd.parent_series,
            packages=[dsd.source_package_name])
        packageset_name = packageset.name
        source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [],
            source.getForDistroSeries(series, name_filter=packageset_name))

    def test_getForDistroSeries_sorted_by_package_name(self):
        # The differences are sorted by package name.
        series = self.makeDerivedSeries()
        names = [
            self.factory.makeDistroSeriesDifference(
                series).source_package_name.name
            for counter in xrange(10)]

        results = getUtility(
            IDistroSeriesDifferenceSource).getForDistroSeries(series)

        self.assertContentEqual(
            sorted(names),
            [result.source_package_name.name for result in results])

    def test_getForDistroSeries_filters_by_parent(self):
        # The differences can be filtered by parent series.
        derived_series = self.factory.makeDistroSeries()
        dsps = [
            self.factory.makeDistroSeriesParent(derived_series=derived_series)
            for counter in xrange(2)]
        dsds = [
            self.factory.makeDistroSeriesDifference(
                parent_series=dsp.parent_series,
                derived_series=derived_series)
            for dsp in dsps]
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsds[0]],
            dsd_source.getForDistroSeries(
                derived_series, parent_series=dsps[0].parent_series))

    def test_getForDistroSeries_matches_packageset(self):
        dsd = self.factory.makeDistroSeriesDifference()
        packageset = self.factory.makePackageset(
            distroseries=dsd.derived_series)
        Store.of(dsd).add(PackagesetSources(
            packageset=packageset, sourcepackagename=dsd.source_package_name))
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsd], dsd_source.getForDistroSeries(
                dsd.derived_series, packagesets=(packageset, )))

    def test_getForDistroSeries_matches_any_packageset_in_filter(self):
        dsd = self.factory.makeDistroSeriesDifference()
        packagesets = [
            self.factory.makePackageset(distroseries=dsd.derived_series)
            for counter in xrange(2)]
        Store.of(dsd).add(PackagesetSources(
            packageset=packagesets[0],
            sourcepackagename=dsd.source_package_name))
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsd], dsd_source.getForDistroSeries(
                dsd.derived_series, packagesets=packagesets))

    def test_getForDistroSeries_filters_by_packageset(self):
        dsd = self.factory.makeDistroSeriesDifference()
        packageset = self.factory.makePackageset(
            distroseries=dsd.derived_series)
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [], dsd_source.getForDistroSeries(
                dsd.derived_series, packagesets=(packageset, )))

    def makeDistroSeriesDifferenceForUser(self, series, user):
        dsd = self.factory.makeDistroSeriesDifference(derived_series=series)
        removeSecurityProxy(dsd.source_package_release).creator = user
        return dsd

    def test_getForDistroSeries_filters_by_spr_creator(self):
        # Specifiying changed_by limits the DSDs returned to those where the
        # associated SPR was created by the given user or team.
        megatron = self.factory.makePersonByName("Megatron")
        alderney = self.factory.makePersonByName("Alderney")
        bulgaria = self.factory.makePersonByName("Bulgaria")
        # Create the derived distroseries and a DSD for each of the users
        # above.
        derived_distroseries = self.factory.makeDistroSeries()
        dsd_megatron = self.makeDistroSeriesDifferenceForUser(
            derived_distroseries, megatron)
        dsd_alderney = self.makeDistroSeriesDifferenceForUser(
            derived_distroseries, alderney)
        dsd_bulgaria = self.makeDistroSeriesDifferenceForUser(
            derived_distroseries, bulgaria)
        # When changed_by is a person we see DSDs created only by that person.
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.assertContentEqual(
            [dsd_alderney],
            dsd_source.getForDistroSeries(
                derived_distroseries, changed_by=alderney))
        # When changed_by is a team we see DSDs created by any member of the
        # team.
        wombles = self.factory.makeTeam(members=(alderney, bulgaria))
        self.assertContentEqual(
            [dsd_alderney, dsd_bulgaria],
            dsd_source.getForDistroSeries(
                derived_distroseries, changed_by=wombles))
        # When changed_by is not a person or team it is treated as a
        # collection, and we see DSDs created by any person in the collection
        # or member of a team in the collection.
        self.assertContentEqual(
            [dsd_alderney, dsd_bulgaria, dsd_megatron],
            dsd_source.getForDistroSeries(
                derived_distroseries, changed_by=(megatron, wombles)))

    def test_getByDistroSeriesNameAndParentSeries(self):
        # An individual difference is obtained using the name.
        ds_diff = self.factory.makeDistroSeriesDifference(
            source_package_name_str='fooname')

        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        result = dsd_source.getByDistroSeriesNameAndParentSeries(
            ds_diff.derived_series, 'fooname', ds_diff.parent_series)

        self.assertEqual(ds_diff, result)

    def test_getSimpleUpgrades_finds_simple_update(self):
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        dsd = self.makeVersionDifference(changed_parent=True)
        self.assertEqual(dsd.base_version, dsd.source_version)
        self.assertContentEqual(
            [dsd], dsd_source.getSimpleUpgrades(dsd.derived_series))

    def test_getSimpleUpgrades_ignores_hidden_differences(self):
        invisible_statuses = [
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS,
            DistroSeriesDifferenceStatus.RESOLVED,
            ]
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        series = self.makeDerivedSeries()
        for status in invisible_statuses:
            self.makeVersionDifference(
                derived_series=series, changed_parent=True, status=status)
        self.assertContentEqual([], dsd_source.getSimpleUpgrades(series))

    def test_getSimpleUpgrades_ignores_other_distroseries(self):
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        self.makeVersionDifference(changed_parent=True)
        self.assertContentEqual(
            [], dsd_source.getSimpleUpgrades(self.factory.makeDistroSeries()))

    def test_getSimpleUpgrades_ignores_packages_changed_in_child(self):
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        dsd = self.makeVersionDifference(
            changed_parent=True, changed_child=True)
        self.assertContentEqual(
            [], dsd_source.getSimpleUpgrades(dsd.derived_series))

    def test_getSimpleUpgrades_ignores_packages_not_updated_in_parent(self):
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        dsd = self.makeVersionDifference(changed_parent=False)
        self.assertContentEqual(
            [], dsd_source.getSimpleUpgrades(dsd.derived_series))

    def test_getSimpleUpgrades_ignores_packages_unique_to_child(self):
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        diff_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        dsd = self.factory.makeDistroSeriesDifference(
            difference_type=diff_type)
        self.assertContentEqual(
            [], dsd_source.getSimpleUpgrades(dsd.derived_series))

    def test_getSimpleUpgrades_ignores_packages_missing_from_child(self):
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        diff_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        dsd = self.factory.makeDistroSeriesDifference(
            difference_type=diff_type)
        self.assertContentEqual(
            [], dsd_source.getSimpleUpgrades(dsd.derived_series))


class TestMostRecentComments(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_most_recent_comments(self):
        dsp = self.factory.makeDistroSeriesParent()
        dsds = set(
            self.factory.makeDistroSeriesDifference(
                derived_series=dsp.derived_series) for index in xrange(5))
        expected_comments = set()
        for dsd in dsds:
            # Add a couple of comments.
            self.factory.makeDistroSeriesDifferenceComment(dsd)
            expected_comments.add(
                self.factory.makeDistroSeriesDifferenceComment(dsd))
        self.assertContentEqual(
            expected_comments, most_recent_comments(dsds))


class TestMostRecentPublications(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def create_difference(self, derived_series):
        # Create a new DistroSeriesDifference
        version = self.factory.getUniqueInteger()
        versions = {
            'base': u'1.%d' % version,
            'derived': u'1.%dderived1' % version,
            'parent': u'1.%d-1' % version,
            }
        dsd = self.factory.makeDistroSeriesDifference(
            derived_series=derived_series,
            versions=versions)
        # Push a base_version in... not sure how better to do it.
        removeSecurityProxy(dsd).base_version = versions["base"]
        return dsd

    def test_simple(self):
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series
        dsds = [
            self.create_difference(derived_series),
            self.create_difference(derived_series),
            ]
        # Derived publication.
        source_pubs_by_spn_id_expected = set(
            (dsd.source_package_name.id, dsd.source_pub)
            for dsd in dsds)
        source_pubs_by_spn_id_found = most_recent_publications(
            dsds, in_parent=False, statuses=(
                PackagePublishingStatus.PUBLISHED,
                PackagePublishingStatus.PENDING))
        self.assertContentEqual(
            source_pubs_by_spn_id_expected,
            source_pubs_by_spn_id_found)
        # Parent publication
        parent_source_pubs_by_spn_id_expected = set(
            (dsd.source_package_name.id, dsd.parent_source_pub)
            for dsd in dsds)
        parent_source_pubs_by_spn_id_found = most_recent_publications(
            dsds, in_parent=True, statuses=(
                PackagePublishingStatus.PUBLISHED,
                PackagePublishingStatus.PENDING))
        self.assertContentEqual(
            parent_source_pubs_by_spn_id_expected,
            parent_source_pubs_by_spn_id_found)

    def test_statuses(self):
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series
        dsd = self.create_difference(derived_series)
        # Change the derived source publication to DELETED.
        removeSecurityProxy(dsd.source_pub).status = (
            PackagePublishingStatus.DELETED)
        # Searching for DELETED will find the source publication.
        self.assertContentEqual(
            [(dsd.source_package_name.id, dsd.source_pub)],
            most_recent_publications(
                [dsd], in_parent=False, statuses=(
                    PackagePublishingStatus.DELETED,)))
        # Searched for DELETED will *not* find the parent publication.
        self.assertContentEqual(
            [], most_recent_publications(
                [dsd], in_parent=True, statuses=(
                    PackagePublishingStatus.DELETED,)))

    def test_match_version(self):
        # When match_version is True, the version of the publications (well,
        # the release) must exactly match those recorded on the
        # DistroSeriesDifference.
        dsp = self.factory.makeDistroSeriesParent()
        derived_series = dsp.derived_series
        dsd = self.create_difference(derived_series)
        # Modify the release version.
        removeSecurityProxy(
            dsd.source_package_release.sourcepackagerelease).version += u"2"
        # Searching with match_version=False finds the publication.
        self.assertContentEqual(
            [(dsd.source_package_name.id, dsd.source_pub)],
            most_recent_publications(
                [dsd], in_parent=False, match_version=False,
                statuses=(PackagePublishingStatus.PUBLISHED,)))
        # Searching with match_version=True does not find the publication.
        self.assertContentEqual(
            [], most_recent_publications(
                [dsd], in_parent=False, match_version=True,
                statuses=(PackagePublishingStatus.PUBLISHED,)))
