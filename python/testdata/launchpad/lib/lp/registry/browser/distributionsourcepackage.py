# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistributionSourcePackageAnswersMenu',
    'DistributionSourcePackageBreadcrumb',
    'DistributionSourcePackageChangelogView',
    'DistributionSourcePackageEditView',
    'DistributionSourcePackageFacets',
    'DistributionSourcePackageHelpView',
    'DistributionSourcePackageNavigation',
    'DistributionSourcePackageOverviewMenu',
    'DistributionSourcePackagePublishingHistoryView',
    'DistributionSourcePackageView',
    'PublishingHistoryViewMixin',
    ]

import itertools
import operator

from lazr.delegates import delegates
from lazr.restful.utils import smartquote
from zope.component import (
    adapter,
    getUtility,
    )
from zope.interface import (
    implements,
    Interface,
    )

from lp.answers.browser.questiontarget import (
    QuestionTargetAnswersMenu,
    QuestionTargetFacetMixin,
    QuestionTargetTraversalMixin,
    )
from lp.answers.enums import QuestionStatus
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    )
from lp.app.browser.stringformatter import extract_email_addresses
from lp.app.browser.tales import CustomizableFormatter
from lp.app.enums import ServiceUsage
from lp.app.interfaces.launchpad import IServiceUsage
from lp.bugs.browser.bugtask import BugTargetTraversalMixin
from lp.bugs.browser.structuralsubscription import (
    expose_structural_subscription_data_to_js,
    StructuralSubscriptionMenuMixin,
    StructuralSubscriptionTargetTraversalMixin,
    )
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.registry.browser import add_subscribe_link
from lp.registry.browser.pillar import PillarBugsMenu
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import pocketsuffix
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.helpers import shortlist
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    Navigation,
    redirection,
    StandardLaunchpadFacets,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.interfaces import IBreadcrumb
from lp.services.webapp.menu import (
    ApplicationMenu,
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import LaunchpadView
from lp.services.webapp.sorting import sorted_dotted_numbers
from lp.soyuz.browser.sourcepackagerelease import linkify_changelog
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.interfaces.distributionsourcepackagerelease import (
    IDistributionSourcePackageRelease,
    )
from lp.soyuz.interfaces.packagediff import IPackageDiffSet
from lp.translations.browser.customlanguagecode import (
    HasCustomLanguageCodesTraversalMixin,
    )


class DistributionSourcePackageFormatterAPI(CustomizableFormatter):
    """Adapt IDistributionSourcePackage objects to a formatted string."""

    _link_permission = 'zope.Public'
    _link_summary_template = '%(displayname)s'

    def _link_summary_values(self):
        displayname = self._context.displayname
        return {'displayname': displayname}


@adapter(IDistributionSourcePackage)
class DistributionSourcePackageBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `IDistributionSourcePackage`."""
    implements(IBreadcrumb)

    @property
    def text(self):
        return smartquote('"%s" package') % (
            self.context.sourcepackagename.name)


class DistributionSourcePackageFacets(QuestionTargetFacetMixin,
                                      StandardLaunchpadFacets):

    usedfor = IDistributionSourcePackage
    enable_only = ['overview', 'bugs', 'answers', 'branches']

    def overview(self):
        text = 'Overview'
        summary = u'General information about {0}'.format(
            self.context.displayname)
        return Link('', text, summary)

    def bugs(self):
        text = 'Bugs'
        summary = u'Bugs reported about {0}'.format(self.context.displayname)
        return Link('', text, summary)

    def branches(self):
        text = 'Code'
        summary = u'Branches for {0}'.format(self.context.displayname)
        return Link('', text, summary)


class DistributionSourcePackageLinksMixin:

    def publishinghistory(self):
        return Link('+publishinghistory', 'Show publishing history')

    @enabled_with_permission('launchpad.BugSupervisor')
    def edit(self):
        """Edit the details of this source package."""
        # This is titled "Edit bug reporting guidelines" because that
        # is the only editable property of a source package right now.
        return Link('+edit', 'Configure bug tracker', icon='edit')

    def new_bugs(self):
        base_path = "+bugs"
        get_data = "?field.status:list=NEW"
        return Link(base_path + get_data, "New bugs", site="bugs")

    def open_questions(self):
        base_path = "+questions"
        get_data = "?field.status=OPEN"
        return Link(base_path + get_data, "Open Questions", site="answers")


class DistributionSourcePackageOverviewMenu(
    ApplicationMenu, DistributionSourcePackageLinksMixin):

    usedfor = IDistributionSourcePackage
    facet = 'overview'
    links = ['new_bugs', 'open_questions']


class DistributionSourcePackageBugsMenu(
    PillarBugsMenu,
    StructuralSubscriptionMenuMixin,
    DistributionSourcePackageLinksMixin):

    usedfor = IDistributionSourcePackage
    facet = 'bugs'

    @cachedproperty
    def links(self):
        links = ['filebug']
        add_subscribe_link(links)
        return links


class DistributionSourcePackageAnswersMenu(QuestionTargetAnswersMenu):

    usedfor = IDistributionSourcePackage
    facet = 'answers'

    links = QuestionTargetAnswersMenu.links + ['gethelp']

    def gethelp(self):
        return Link('+gethelp', 'Help and support options', icon='info')


class DistributionSourcePackageNavigation(Navigation,
    BugTargetTraversalMixin, HasCustomLanguageCodesTraversalMixin,
    QuestionTargetTraversalMixin,
    StructuralSubscriptionTargetTraversalMixin):

    usedfor = IDistributionSourcePackage

    redirection("+editbugcontact", "+subscribe")

    def traverse(self, name):
        return self.context.getVersion(name)


class DecoratedDistributionSourcePackageRelease:
    """A decorated DistributionSourcePackageRelease.

    The publishing history and package diffs for the release are
    pre-cached.
    """
    delegates(IDistributionSourcePackageRelease, 'context')

    def __init__(
        self, distributionsourcepackagerelease, publishing_history,
        package_diffs, person_data, user):
        self.context = distributionsourcepackagerelease
        self._publishing_history = publishing_history
        self._package_diffs = package_diffs
        self._person_data = person_data
        self._user = user

    @property
    def publishing_history(self):
        """ See `IDistributionSourcePackageRelease`."""
        return self._publishing_history

    @property
    def package_diffs(self):
        """ See `ISourcePackageRelease`."""
        return self._package_diffs

    @property
    def change_summary(self):
        """ See `ISourcePackageRelease`."""
        return linkify_changelog(
            self._user, self.context.change_summary, self._person_data)


class IDistributionSourcePackageActionMenu(Interface):
    """Marker interface for the action menu."""


class DistributionSourcePackageActionMenu(
    NavigationMenu,
    StructuralSubscriptionMenuMixin,
    DistributionSourcePackageLinksMixin):
    """Action menu for distro source packages."""
    usedfor = IDistributionSourcePackageActionMenu
    facet = 'overview'
    title = 'Actions'

    @cachedproperty
    def links(self):
        links = ['publishing_history', 'change_log']
        add_subscribe_link(links)
        links.append('edit')
        return links

    def publishing_history(self):
        text = 'View full publishing history'
        return Link('+publishinghistory', text, icon="info")

    def change_log(self):
        text = 'View full change log'
        return Link('+changelog', text, icon="info")


class DistributionSourcePackageBaseView(LaunchpadView):
    """Common features to all `DistributionSourcePackage` views."""

    def releases(self):
        """All releases for this `IDistributionSourcePackage`."""

        def not_empty(text):
            return (
                text is not None and isinstance(text, basestring)
                and len(text.strip()) > 0)

        dspr_pubs = self.context.getReleasesAndPublishingHistory()

        # Return as early as possible to avoid unnecessary processing.
        if len(dspr_pubs) == 0:
            return []

        sprs = [dspr.sourcepackagerelease for (dspr, spphs) in dspr_pubs]
        # Preload email/person data only if user is logged on. In the opposite
        # case the emails in the changelog will be obfuscated anyway and thus
        # cause no database lookups.
        the_changelog = '\n'.join(
            [spr.changelog_entry for spr in sprs
             if not_empty(spr.changelog_entry)])
        if self.user:
            self._person_data = dict(
                [(email.email, person) for (email, person) in
                    getUtility(IPersonSet).getByEmails(
                        extract_email_addresses(the_changelog),
                        include_hidden=False)])
        else:
            self._person_data = None
        # Collate diffs for relevant SourcePackageReleases
        pkg_diffs = getUtility(IPackageDiffSet).getDiffsToReleases(
            sprs, preload_for_display=True)
        spr_diffs = {}
        for spr, diffs in itertools.groupby(pkg_diffs,
                                            operator.attrgetter('to_source')):
            spr_diffs[spr] = list(diffs)

        return [
            DecoratedDistributionSourcePackageRelease(
                dspr, spphs, spr_diffs.get(dspr.sourcepackagerelease, []),
                self._person_data, self.user)
            for (dspr, spphs) in dspr_pubs]


class DistributionSourcePackageView(DistributionSourcePackageBaseView,
                                    LaunchpadView):
    """View class for DistributionSourcePackage."""
    implements(IDistributionSourcePackageActionMenu)

    def initialize(self):
        super(DistributionSourcePackageView, self).initialize()
        expose_structural_subscription_data_to_js(
            self.context, self.request, self.user)

    @property
    def label(self):
        return self.context.title

    page_title = label

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @property
    def all_published_in_active_distroseries(self):
        """Return a list of publishings in each active distroseries.

        The list contains dictionaries each with a key of "suite" and
        "description" where suite is "distroseries-pocket" and
        description is "(version): component/section".
        """
        results = []
        for pub in self.context.current_publishing_records:
            if pub.distroseries.active:
                entry = {
                    "suite": (pub.distroseries.name.capitalize() +
                               pocketsuffix[pub.pocket]),
                    "description": "(%s): %s/%s" % (
                        pub.sourcepackagerelease.version,
                        pub.component.name, pub.section.name),
                    }
                results.append(entry)
        return results

    @property
    def related_ppa_versions(self):
        """Return a list of the latest 3 ppas with related publishings.

        The list contains dictionaries each with a key of 'archive' and
        'publications'.
        """
        # Grab the related archive publications and limit the result to
        # the first 3.
        # XXX Michael Nelson 2009-06-24 bug=387020
        # Currently we need to find distinct archives here manually because,
        # without a concept of IArchive.rank or similar, the best ordering
        # that orderDistributionSourcePackage.findRelatedArchives() method
        # can provide is on a join (SourcePackageRelease.dateuploaded), but
        # this prohibits a distinct clause.
        # To ensure that we find distinct archives here with only one query,
        # we grab the first 20 results and iterate through to find three
        # distinct archives (20 is a magic number being greater than
        # 3 * number of distroseries).
        related_archives = self.context.findRelatedArchives()
        related_archives.config(limit=20)
        top_three_archives = []
        for archive in related_archives:
            if archive in top_three_archives:
                continue
            else:
                top_three_archives.append(archive)

            if len(top_three_archives) == 3:
                break

        # Now we'll find the relevant publications for the top
        # three archives.
        archive_set = getUtility(IArchiveSet)
        publications = archive_set.getPublicationsInArchives(
                self.context.sourcepackagename, top_three_archives,
                self.context.distribution)

        # Collect the publishings for each archive
        archive_publishings = {}
        for pub in publications:
            archive_publishings.setdefault(pub.archive, []).append(pub)

        # Then construct a list of dicts with the results for easy use in
        # the template, preserving the order of the archives:
        archive_versions = []
        for archive in top_three_archives:
            versions = []

            # For each publication, append something like:
            # 'Jaunty (1.0.1b)' to the versions list.
            for pub in archive_publishings[archive]:
                versions.append(
                    "%s (%s)" % (
                        pub.distroseries.displayname,
                        pub.source_package_version,
                        )
                    )
            archive_versions.append({
                'archive': archive,
                'versions': ", ".join(versions),
                })

        return archive_versions

    @property
    def further_ppa_versions_url(self):
        """Return the url used to find further PPA versions of this package.
        """
        return "%s/+ppas?name_filter=%s" % (
            canonical_url(self.context.distribution),
            self.context.name,
            )

    @cachedproperty
    def active_distroseries_packages(self):
        """Cached proxy call to context/get_distroseries_packages."""
        return self.context.get_distroseries_packages()

    @property
    def packages_by_active_distroseries(self):
        """Dict of packages keyed by distroseries."""
        packages_dict = {}
        for package in self.active_distroseries_packages:
            packages_dict[package.distroseries] = package
        return packages_dict

    @cachedproperty
    def active_series(self):
        """Return active distroseries where this package is published.

        Used in the template code that shows the table of versions.
        The returned series are sorted in reverse order of creation.
        """
        series = set()
        for package in self.active_distroseries_packages:
            series.add(package.distroseries)
        result = sorted_dotted_numbers(
            series, key=operator.attrgetter('version'))
        result.reverse()
        return result

    def published_by_version(self, sourcepackage):
        """Return a dict of publications keyed by version.

        :param sourcepackage: ISourcePackage
        """
        publications = sourcepackage.distroseries.getPublishedSources(
            sourcepackage.sourcepackagename)
        pocket_dict = {}
        for pub in shortlist(publications):
            version = pub.source_package_version
            pocket_dict.setdefault(version, []).append(pub)
        return pocket_dict

    @property
    def latest_sourcepackage(self):
        if len(self.active_series) == 0:
            return None
        return self.active_series[0].getSourcePackage(
            self.context.sourcepackagename)

    @property
    def version_table(self):
        """Rows of data for the template to render in the packaging table."""
        rows = []
        packages_by_series = self.packages_by_active_distroseries
        for distroseries in self.active_series:
            # The first row for each series is the "title" row.
            packaging = packages_by_series[distroseries].direct_packaging
            package = packages_by_series[distroseries]
            # Don't show the "Set upstream link" action for older series
            # without packaging info, so the user won't feel required to
            # fill it in.
            show_set_upstream_link = (
                packaging is None
                and distroseries.status in (
                    SeriesStatus.CURRENT,
                    SeriesStatus.DEVELOPMENT,
                    )
                )
            title_row = {
                'blank_row': False,
                'title_row': True,
                'data_row': False,
                'distroseries': distroseries,
                'series_package': package,
                'packaging': packaging,
                'show_set_upstream_link': show_set_upstream_link,
                }
            rows.append(title_row)

            # After the title row, we list each package version that's
            # currently published, and which pockets it's published in.
            pocket_dict = self.published_by_version(package)
            for version in pocket_dict:
                most_recent_publication = pocket_dict[version][0]
                date_published = most_recent_publication.datepublished
                pockets = ", ".join(
                    [pub.pocket.name for pub in pocket_dict[version]])
                row = {
                    'blank_row': False,
                    'title_row': False,
                    'data_row': True,
                    'version': version,
                    'publication': most_recent_publication,
                    'pockets': pockets,
                    'component': most_recent_publication.component_name,
                    'date_published': date_published,
                    }
                rows.append(row)
            # We need a blank row after each section, so the series
            # header row doesn't appear too close to the previous
            # section.
            rows.append({
                'blank_row': True,
                'title_row': False,
                'data_row': False,
                })

        return rows

    @cachedproperty
    def open_questions(self):
        """Return result set containing open questions for this package."""
        return self.context.searchQuestions(status=QuestionStatus.OPEN)

    @cachedproperty
    def bugs_answers_usage(self):
        """Return a  dict of uses_bugs, uses_answers, uses_both, uses_either.
        """
        service_usage = IServiceUsage(self.context)
        uses_bugs = (
            service_usage.bug_tracking_usage == ServiceUsage.LAUNCHPAD)
        uses_answers = service_usage.answers_usage == ServiceUsage.LAUNCHPAD
        uses_both = uses_bugs and uses_answers
        uses_either = uses_bugs or uses_answers
        return dict(
            uses_bugs=uses_bugs, uses_answers=uses_answers,
            uses_both=uses_both, uses_either=uses_either)

    @cachedproperty
    def new_bugtasks_count(self):
        search_params = BugTaskSearchParams(
            self.user, status=BugTaskStatus.NEW, omit_dupes=True)
        return self.context.searchTasks(search_params).count()


class DistributionSourcePackageChangelogView(
    DistributionSourcePackageBaseView, LaunchpadView):
    """View for presenting change logs for a `DistributionSourcePackage`."""

    page_title = 'Change log'

    @property
    def label(self):
        return 'Change log for %s' % self.context.title


class PublishingHistoryViewMixin:
    """Mixin for presenting batches of `SourcePackagePublishingHistory`s."""

    def _preload_people(self, pubs):
        ids = set()
        for spph in pubs:
            ids.update((spph.removed_byID, spph.creatorID, spph.sponsorID))
        ids.discard(None)
        if ids:
            list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
                ids, need_validity=True))

    @property
    def batchnav(self):
        # No point using StormRangeFactory right now, as the sorted
        # lookup can't be fully indexed (it spans multiple archives).
        return BatchNavigator(
            DecoratedResultSet(
                self.context.publishing_history,
                pre_iter_hook=self._preload_people),
            self.request)


class DistributionSourcePackagePublishingHistoryView(
        LaunchpadView, PublishingHistoryViewMixin):
    """View for presenting `DistributionSourcePackage` publishing history."""

    page_title = 'Publishing history'

    @property
    def label(self):
        return 'Publishing history of %s' % self.context.title


class DistributionSourcePackageEditView(LaunchpadEditFormView):
    """Edit a distribution source package."""

    schema = IDistributionSourcePackage
    field_names = [
        'bug_reporting_guidelines',
        'bug_reported_acknowledgement',
        'enable_bugfiling_duplicate_search',
        ]

    @property
    def label(self):
        """The form label."""
        return 'Edit %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @action("Change", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url


class DistributionSourcePackageHelpView(LaunchpadView):
    """A View to show Answers help."""

    page_title = 'Help and support options'
