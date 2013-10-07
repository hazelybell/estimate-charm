# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for the DistroSeriesDifference views."""

__metaclass__ = type

import re

from BeautifulSoup import BeautifulSoup
import soupmatchers
from testtools.matchers import (
    MatchesAny,
    Not,
    )
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.browser.distroseriesdifference import (
    DistroSeriesDifferenceDisplayComment,
    )
from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.services.comments.interfaces.conversation import (
    IComment,
    IConversation,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.soyuz.enums import (
    PackageDiffStatus,
    PackagePublishingStatus,
    )
from lp.soyuz.model.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease,
    )
from lp.testing import (
    anonymous_logged_in,
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class DistroSeriesDifferenceTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_provides_conversation(self):
        # The DSDView provides a conversation implementation.
        ds_diff = self.factory.makeDistroSeriesDifference()

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        self.assertTrue(verifyObject(IConversation, view))

    def test_comment_for_display_provides_icomment(self):
        # The DSDDisplayComment browser object provides IComment.
        ds_diff = self.factory.makeDistroSeriesDifference()

        person = self.factory.makePerson()
        with person_logged_in(person):
            comment = ds_diff.addComment(person, "I'm working on this.")
        comment_for_display = DistroSeriesDifferenceDisplayComment(comment)

        self.assertTrue(verifyObject(IComment, comment_for_display))

    def addSummaryToDifference(self, distro_series_difference):
        """Helper that adds binaries with summary info to the source pubs."""
        # Avoid circular import.
        from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
        distro_series = distro_series_difference.derived_series
        parent_series = distro_series_difference.parent_series
        source_package_name_str = (
            distro_series_difference.source_package_name.name)
        stp = SoyuzTestPublisher()

        if distro_series_difference.difference_type == (
            DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES):
            source_pub = distro_series_difference.parent_source_pub
        else:
            source_pub = distro_series_difference.source_pub

        stp.makeSourcePackageSummaryData(source_pub)
        stp.updateDistroSeriesPackageCache(source_pub.distroseries)

        # updateDistroSeriesPackageCache reconnects the db, so the
        # objects need to be reloaded.
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        ds_diff = dsd_source.getByDistroSeriesNameAndParentSeries(
            distro_series, source_package_name_str, parent_series)
        return ds_diff

    def test_binary_summaries_for_source_pub(self):
        # For packages unique to the derived series (or different
        # versions) the summary is based on the derived source pub.
        ds_diff = self.factory.makeDistroSeriesDifference()
        ds_diff = self.addSummaryToDifference(ds_diff)

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        self.assertIsNot(None, view.binary_summaries)
        self.assertEqual([
            u'flubber-bin: summary for flubber-bin',
            u'flubber-lib: summary for flubber-lib',
            ], view.binary_summaries)

    def test_binary_summaries_for_missing_difference(self):
        # For packages only in the parent series, the summary is based
        # on the parent publication.
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=(
                DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES))
        ds_diff = self.addSummaryToDifference(ds_diff)

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        self.assertIsNot(None, view.binary_summaries)
        self.assertEqual([
            u'flubber-bin: summary for flubber-bin',
            u'flubber-lib: summary for flubber-lib',
            ], view.binary_summaries)

    def test_binary_summaries_no_pubs(self):
        # If the difference has been resolved by removing packages then
        # there will not be a summary.
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=(
                DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES))
        with person_logged_in(ds_diff.parent_source_pub.archive.owner):
            ds_diff.parent_source_pub.requestDeletion(None)
        ds_diff.update()

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        self.assertIs(None, ds_diff.parent_source_pub)
        self.assertIs(None, ds_diff.source_pub)
        self.assertIs(None, view.binary_summaries)

    def test_binary_summaries_none_no_display(self):
        # If, for a difference, binary_summaries=None, then the slot to
        # display binary summaries is not present.
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=(
                DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES))
        removeSecurityProxy(ds_diff).parent_source_pub.status = (
            PackagePublishingStatus.DELETED)
        ds_diff.update()

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        binary_description_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Binary descriptions header', 'dt',
                text=re.compile(
                    '\s*Binary descriptions:\s*')))

        self.assertThat(view(), Not(binary_description_matcher))

    def test_show_edit_options_non_ajax(self):
        # Blacklist options and "Add comment" are not shown for non-ajax
        # requests.
        ds_diff = self.factory.makeDistroSeriesDifference()

        # Without JS, even editors don't see blacklist options.
        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
        self.assertFalse(view.show_add_comment)
        self.assertFalse(view.enable_blacklist_options)
        self.assertEqual(
            'blacklist-options-disabled',
            view.blacklist_options_css_class)

    def test_show_edit_options_editor(self):
        # The "Add comment" link is shown and the blacklist options are
        # not enabled if requested by an editor via ajax.
        ds_diff = self.factory.makeDistroSeriesDifference()

        request = LaunchpadTestRequest(HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra', request=request)
            self.assertTrue(view.show_add_comment)
            self.assertFalse(view.enable_blacklist_options)
            self.assertEqual(
                'blacklist-options-disabled',
                view.blacklist_options_css_class)

    def test_enable_blacklist_options_for_archive_admin(self):
        # To see the blacklist options enabled the user needs to be an
        # archive admin.
        ds_diff = self.factory.makeDistroSeriesDifference()
        archive_admin = self.factory.makeArchiveAdmin(
            archive=ds_diff.derived_series.main_archive)

        request = LaunchpadTestRequest(HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        with person_logged_in(archive_admin):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra', request=request)
            self.assertTrue(view.enable_blacklist_options)

    def test_show_add_comment_non_editor(self):
        # Even with a JS request, non-editors do not see the 'add
        # comment' option.
        ds_diff = self.factory.makeDistroSeriesDifference()

        request = LaunchpadTestRequest(HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        view = create_initialized_view(
            ds_diff, '+listing-distroseries-extra', request=request)
        self.assertFalse(view.show_add_comment)

    def test_does_display_child_diff(self):
        # If the child's latest published version is not the same as the base
        # version, we display two links to two diffs.
        changelog_lfa = self.factory.makeChangelog(
            'foo', ['0.1-1derived1', '0.1-1'])
        parent_changelog_lfa = self.factory.makeChangelog(
            'foo', ['0.1-2', '0.1-1'])
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '0.1-1derived1',
            'parent': '0.1-2',
            }, changelogs={
            'derived': changelog_lfa,
            'parent': parent_changelog_lfa})

        self.assertEqual('0.1-1', ds_diff.base_version)
        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            soup = BeautifulSoup(view())
        tags = soup.find('ul', 'package-diff-status').findAll('span')
        self.assertEqual(2, len(tags))

    def test_do_not_display_child_diff(self):
        # If the child's latest published version is the same as the base
        # version, we don't display the link to the diff.
        changelog_lfa = self.factory.makeChangelog('foo', ['0.30-1'])
        parent_changelog_lfa = self.factory.makeChangelog(
            'foo', ['0.32-1', '0.30-1'])
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '0.30-1',
            'parent': '0.32-1',
            }, changelogs={
            'derived': changelog_lfa,
            'parent': parent_changelog_lfa})

        self.assertEqual('0.30-1', ds_diff.base_version)
        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            soup = BeautifulSoup(view())
        tags = soup.find('ul', 'package-diff-status').findAll('span')
        self.assertEqual(1, len(tags))

    def test_do_not_display_parent_diff(self):
        # If the parent's latest published version is the same as the base
        # version, we don't display the link to the diff.
        changelog_lfa = self.factory.makeChangelog('foo', ['0.30-1'])
        parent_changelog_lfa = self.factory.makeChangelog(
            'foo', ['0.32-1', '0.30-1'])
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '0.32-1',
            'parent': '0.30-1',
            }, changelogs={
            'derived': changelog_lfa,
            'parent': parent_changelog_lfa})

        self.assertEqual('0.30-1', ds_diff.base_version)
        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            soup = BeautifulSoup(view())
        tags = soup.find('ul', 'package-diff-status').findAll('span')
        self.assertEqual(1, len(tags))

    def _assertNoRequestLink(self, ds_diff):
        view = create_initialized_view(
            ds_diff, '+listing-distroseries-extra')
        package_diff_request_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Request link', 'a',
                text=re.compile(
                    '\s*Compute differences from last common version\s*')))

        self.assertFalse(view.show_package_diffs_request_link)
        self.assertThat(view(), Not(package_diff_request_matcher))

    def test_no_package_diff_parent_same_version(self):
        # If the derived package diff is computed and parent_version is
        # the same as the base version, we don't display the link to
        # request package diffs.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True,
            versions={
                'derived': '0.32-1',
                'parent': '0.30-1',
                'base': '0.30-1'})

        with person_logged_in(ds_diff.derived_series.owner):
            ds_diff.package_diff = self.factory.makePackageDiff(
                status=PackageDiffStatus.COMPLETED)
            self._assertNoRequestLink(ds_diff)

    def test_no_package_diff_derived_same_version(self):
        # If the parent package diff is computed and source_version is
        # the same as the base version, we don't display the link to
        # request package diffs.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True,
            versions={
                'derived': '0.30-1',
                'parent': '0.32-1',
                'base': '0.30-1'})

        with person_logged_in(ds_diff.derived_series.owner):
            ds_diff.parent_package_diff = self.factory.makePackageDiff(
                status=PackageDiffStatus.COMPLETED)
            self._assertNoRequestLink(ds_diff)

    def _makeDistroSeriesDifferenceView(self, difference_type):
        # Helper method to create a view with the specified
        # difference_type.
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=difference_type)
        view = create_initialized_view(
            ds_diff, '+listing-distroseries-extra')
        return view

    def test_packagediffs_display_diff_version(self):
        # The packages diffs slots are displayed when the diff
        # is of type DIFFERENT_VERSIONS.
        view = self._makeDistroSeriesDifferenceView(
            DistroSeriesDifferenceType.DIFFERENT_VERSIONS)
        self.assertTrue(view.can_have_packages_diffs)

    def test_packagediffs_display_missing_from_derived(self):
        # The packages diffs slots are not displayed when the diff
        # is of type MISSING_FROM_DERIVED_SERIES.
        view = self._makeDistroSeriesDifferenceView(
            DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES)
        self.assertFalse(view.can_have_packages_diffs)

    def test_packagediffs_display_unique_to_derived(self):
        # The packages diffs slots are not displayed when the diff
        # is of type UNIQUE_TO_DERIVED_SERIES.
        view = self._makeDistroSeriesDifferenceView(
            DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES)
        self.assertFalse(view.can_have_packages_diffs)


class DistroSeriesDifferenceTemplateTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def number_of_request_diff_texts(self, html_or_soup):
        """Returns the number of request diff text."""
        if not(isinstance(html_or_soup, BeautifulSoup)):
            soup = BeautifulSoup(html_or_soup)
        else:
            soup = html_or_soup
        class_dict = {'class': re.compile('request-derived-diff')}
        return len(soup.findAll('span', class_dict))

    def contains_one_link_to_diff(self, html_or_soup, package_diff):
        """Return whether the html contains a link to the diff content."""
        if not(isinstance(html_or_soup, BeautifulSoup)):
            soup = BeautifulSoup(html_or_soup)
        else:
            soup = html_or_soup
        return 1 == len(soup.findAll(
            'a', href=package_diff.diff_content.http_url))

    def test_both_request_diff_texts_rendered(self):
        # An unlinked description of a potential diff is displayed when
        # no diff is present.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True)

        with person_logged_in(self.factory.makePerson()):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')#, principal=user)
            soup = BeautifulSoup(view())
        # Both diffs present simple text repr. of proposed diff.
        self.assertEqual(2, self.number_of_request_diff_texts(soup))

    def test_source_diff_rendering_diff(self):
        # A linked description of the diff is displayed when
        # it is present.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True)

        with person_logged_in(self.factory.makePerson()):
            ds_diff.package_diff = self.factory.makePackageDiff()

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        html = view()
        # The text for the parent diff remains, but the source package
        # diff is now a link.
        self.assertEqual(1, self.number_of_request_diff_texts(html))
        self.assertTrue(
            self.contains_one_link_to_diff(html, ds_diff.package_diff))

    def test_source_diff_rendering_diff_no_link(self):
        # The status of the package is shown if the package diff is in a
        # PENDING or FAILED state.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True)

        statuses_and_classes = [
            (PackageDiffStatus.PENDING, 'PENDING'),
            (PackageDiffStatus.FAILED, 'FAILED')]
        for status, css_class in statuses_and_classes:
            with person_logged_in(self.factory.makePerson()):
                ds_diff.package_diff = self.factory.makePackageDiff(
                     status=status)

            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            soup = BeautifulSoup(view())
            # Only one link since the other package diff is not COMPLETED.
            self.assertEqual(1, self.number_of_request_diff_texts(soup))
            # The diff has a css_class class.
            self.assertEqual(
                1,
                len(soup.findAll('span', {'class': re.compile(css_class)})))

    def test_parent_source_diff_rendering_diff_no_link(self):
        # The status of the package is shown if the parent package diff is
        # in a PENDING or FAILED state.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True)

        statuses_and_classes = [
            (PackageDiffStatus.PENDING, 'PENDING'),
            (PackageDiffStatus.FAILED, 'FAILED')]
        for status, css_class in statuses_and_classes:
            with person_logged_in(self.factory.makePerson()):
                ds_diff.parent_package_diff = self.factory.makePackageDiff(
                     status=status)

            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            soup = BeautifulSoup(view())
            # Only one link since the other package diff is not COMPLETED.
            self.assertEqual(1, self.number_of_request_diff_texts(soup))
            # The diff has a css_class class.
            self.assertEqual(
                1,
                len(soup.findAll('span', {'class': re.compile(css_class)})))

    def test_source_diff_rendering_no_source(self):
        # If there is no source pub for this difference, then we don't
        # display even the request for a diff.
        missing_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=missing_type)

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        self.assertEqual(0, self.number_of_request_diff_texts(view()))

    def test_parent_source_diff_rendering_diff(self):
        # A linked description of the diff is displayed when
        # it is present.
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True)

        with person_logged_in(self.factory.makePerson()):
            ds_diff.parent_package_diff = self.factory.makePackageDiff()

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        # The text for the source diff remains, but the parent package
        # diff is now a link.
        html = view()
        self.assertEqual(1, self.number_of_request_diff_texts(html))
        self.assertTrue(
            self.contains_one_link_to_diff(
                html, ds_diff.parent_package_diff))

    def test_parent_source_diff_rendering_no_source(self):
        # If there is no source pub for this difference, then we don't
        # display even the request for a diff.
        unique_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
        ds_diff = self.factory.makeDistroSeriesDifference(
            difference_type=unique_type)

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        self.assertEqual(0, self.number_of_request_diff_texts(view()))

    def test_comments_rendered(self):
        # If there are comments on the difference, they are rendered.
        ds_diff = self.factory.makeDistroSeriesDifference()
        person = self.factory.makePerson()
        with person_logged_in(person):
            ds_diff.addComment(person, "I'm working on this.")
            ds_diff.addComment(person, "Here's another comment.")

        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        soup = BeautifulSoup(view())

        self.assertEqual(
            1, len(soup.findAll('pre', text="I&#x27;m working on this.")))
        self.assertEqual(
            1, len(soup.findAll('pre', text="Here&#x27;s another comment.")))

    def test_last_common_version_is_linked(self):
        # The "Last Common Version" version text should link to the
        # parent distro sourcepackagerelease page.
        ds_diff = removeSecurityProxy(
            self.factory.makeDistroSeriesDifference(set_base_version=True))
        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')
        page = view()

        distro = ds_diff.parent_series.distribution
        sourcepackagerelease = ds_diff.parent_source_package_release
        url = canonical_url(
            DistributionSourcePackageRelease(distro, sourcepackagerelease),
            force_local_path=True)
        anchor_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                "VERSION LINK", 'a',
                attrs=dict(href=url)))

        self.assertThat(page, anchor_matcher)

    def getViewContentXmlHttpRequest(self, context, view_name, person):
        # Helper method to request a view via an XMLHttpRequest.
        with person_logged_in(person):
            request = LaunchpadTestRequest(
                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            view = create_initialized_view(
                context, view_name, request=request)
            return view()

    def test_blacklist_options(self):
        # Blacklist options are presented to the users who are archive
        # admins.
        ds_diff = self.factory.makeDistroSeriesDifference()
        archive_admin = self.factory.makeArchiveAdmin(
            archive=ds_diff.derived_series.main_archive)
        view_content = self.getViewContentXmlHttpRequest(
            ds_diff, '+listing-distroseries-extra', archive_admin)
        soup = BeautifulSoup(view_content)

        self.assertEqual(
            1, len(soup.findAll('div', {'class': 'blacklist-options'})))

    def test_blacklist_options_disabled(self):
        # Blacklist options are disabled to the users who are *not* archive
        # admins.
        ds_diff = self.factory.makeDistroSeriesDifference()
        person = self.factory.makePerson()
        view_content = self.getViewContentXmlHttpRequest(
            ds_diff, '+listing-distroseries-extra', person)
        soup = BeautifulSoup(view_content)

        self.assertEqual(
            1,
            len(soup.findAll('div', {'class': 'blacklist-options-disabled'})))

    def test_blacklist_options_initial_values_none(self):
        ds_diff = self.factory.makeDistroSeriesDifference()
        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        # If the difference is not currently blacklisted, 'NONE' is set
        # as the default value for the field.
        self.assertEqual('NONE', view.initial_values.get('blacklist_options'))

    def test_blacklist_options_initial_values_current(self):
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT)
        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT,
            view.initial_values.get('blacklist_options'))

    def test_blacklist_options_initial_values_always(self):
        ds_diff = self.factory.makeDistroSeriesDifference(
            status=DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS)
        view = create_initialized_view(ds_diff, '+listing-distroseries-extra')

        self.assertEqual(
            DistroSeriesDifferenceStatus.BLACKLISTED_ALWAYS,
            view.initial_values.get('blacklist_options'))

    def test_package_diff_request_link(self):
        # The link to compute package diffs is only shown to
        # a user with lp.Edit permission (i.e. lp.View on the
        # distribution).
        ds_diff = self.factory.makeDistroSeriesDifference(
            set_base_version=True)
        package_diff_request_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Request link', 'a',
                text=re.compile(
                    '\s*Compute differences from last common version\s*')))

        with person_logged_in(self.factory.makePerson()):
            self.assertTrue(
                check_permission('launchpad.Edit', ds_diff))
            self.assertTrue(
                check_permission(
                    'launchpad.View',
                    ds_diff.derived_series.parent))
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            self.assertThat(view(), package_diff_request_matcher)
            self.assertTrue(view.show_package_diffs_request_link)

    package_diff_header_matcher = soupmatchers.HTMLContains(
        soupmatchers.Tag(
            'Package diffs header', 'dt',
            text=re.compile(
                '\s*Differences from last common version:')))

    package_diff_info_matcher = soupmatchers.HTMLContains(
        soupmatchers.Within(
            soupmatchers.Tag('Package diff container', 'dd'),
            soupmatchers.Tag(
                'Package diffs info', 'ul',
                attrs={'class': 'package-diff-status'})))

    def test_package_diff_label(self):
        # If base_version is not None the label for the section is
        # there.
        changelog_lfa = self.factory.makeChangelog('foo', ['0.30-1'])
        parent_changelog_lfa = self.factory.makeChangelog(
            'foo', ['0.32-1', '0.30-1'])
        transaction.commit()  # Yay, librarian.
        ds_diff = self.factory.makeDistroSeriesDifference(versions={
            'derived': '0.30-1',
            'parent': '0.32-1',
            }, changelogs={
            'derived': changelog_lfa,
            'parent': parent_changelog_lfa})

        with celebrity_logged_in('admin'):
            ds_diff.parent_package_diff = self.factory.makePackageDiff()
            ds_diff.package_diff = self.factory.makePackageDiff()
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            html = view()
            self.assertThat(html, self.package_diff_header_matcher)

    def test_package_diff_no_base_version(self):
        # If diff's base_version is None packages diffs are not displayed
        # and neither is the link to compute them.
        versions = {
            'base': None,  # No base version.
            'derived': '0.1-1derived1',
            'parent': '0.1-2'}
        ds_diff = self.factory.makeDistroSeriesDifference(versions=versions)
        package_diff_request_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Request link', 'a',
                text=re.compile(
                    '\s*Compute differences from last common version\s*')))

        pending_package_diff_matcher = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Pending package diff', 'span',
                attrs={'class': 'PENDING'}))

        unknown_base_version = soupmatchers.HTMLContains(
            soupmatchers.Tag(
                'Unknown base version', 'dd',
                text=re.compile(
                    '\s*Unknown, so no diffs are available')))

        with celebrity_logged_in('admin'):
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            html = view()
            self.assertFalse(view.show_package_diffs_request_link)
            self.assertThat(html, unknown_base_version)
            self.assertThat(
                html,
                Not(
                    MatchesAny(
                        package_diff_request_matcher,
                        pending_package_diff_matcher,
                        self.package_diff_header_matcher)))

    def test_package_diffs_hidden_to_unprivileged_user_if_not_available(self):
        # No diff information is shown if pacakge diffs are not available and
        # the user does not have permission to request their creation.
        ds_diff = self.factory.makeDistroSeriesDifference(
            versions={'base': '0.1', 'derived': '0.1-1derived1',
                      'parent': '0.1-2'},
            set_base_version=True)
        with anonymous_logged_in():
            view = create_initialized_view(
                ds_diff, '+listing-distroseries-extra')
            html = view()
            self.assertThat(html, Not(self.package_diff_header_matcher))
            self.assertThat(html, Not(self.package_diff_info_matcher))
