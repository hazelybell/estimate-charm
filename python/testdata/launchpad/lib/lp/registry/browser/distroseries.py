# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View classes related to `IDistroSeries`."""

__metaclass__ = type

__all__ = [
    'DistroSeriesAddView',
    'DistroSeriesAdminView',
    'DistroSeriesBreadcrumb',
    'DistroSeriesEditView',
    'DistroSeriesFacets',
    'DistroSeriesInitializeView',
    'DistroSeriesLocalDifferencesView',
    'DistroSeriesMissingPackagesView',
    'DistroSeriesNavigation',
    'DistroSeriesPackageSearchView',
    'DistroSeriesPackagesView',
    'DistroSeriesUniquePackagesView',
    'DistroSeriesView',
    ]

import apt_pkg
from lazr.restful.interface import copy_field
from lazr.restful.interfaces import IJSONRequestCache
from zope.component import getUtility
from zope.event import notify
from zope.formlib import form
from zope.interface import Interface
from zope.lifecycleevent import ObjectCreatedEvent
from zope.schema import (
    Choice,
    List,
    TextLine,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.errors import NotFoundError
from lp.app.widgets.itemswidgets import (
    LabeledMultiCheckBoxWidget,
    LaunchpadDropdownWidget,
    LaunchpadRadioWidget,
    )
from lp.app.widgets.popup import PersonPickerWidget
from lp.archivepublisher.interfaces.publisherconfig import IPublisherConfigSet
from lp.blueprints.browser.specificationtarget import (
    HasSpecificationsMenuMixin,
    )
from lp.bugs.browser.bugtask import BugTargetTraversalMixin
from lp.bugs.browser.structuralsubscription import (
    expose_structural_subscription_data_to_js,
    StructuralSubscriptionMenuMixin,
    StructuralSubscriptionTargetTraversalMixin,
    )
from lp.registry.browser import (
    add_subscribe_link,
    MilestoneOverlayMixin,
    )
from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.browser_helpers import get_plural_text
from lp.services.database.constants import UTC_NOW
from lp.services.features import getFeatureFlag
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    GetitemNavigation,
    StandardLaunchpadFacets,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import structured
from lp.services.webapp.menu import (
    ApplicationMenu,
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    stepthrough,
    stepto,
    )
from lp.services.webapp.url import urlappend
from lp.services.worlddata.helpers import browser_languages
from lp.services.worlddata.interfaces.country import ICountry
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.soyuz.browser.archive import PackageCopyingMixin
from lp.soyuz.browser.packagesearch import PackageSearchViewBase
from lp.soyuz.enums import PackageCopyPolicy
from lp.soyuz.interfaces.distributionjob import (
    IDistroSeriesDifferenceJobSource,
    )
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.soyuz.interfaces.packageset import IPackagesetSet
from lp.soyuz.interfaces.queue import IPackageUploadSet
from lp.soyuz.model.queue import PackageUploadQueue
from lp.translations.browser.distroseries import (
    check_distroseries_translations_viewable,
    )

# DistroSeries statuses that benefit from mass package upgrade support.
UPGRADABLE_SERIES_STATUSES = [
    SeriesStatus.FUTURE,
    SeriesStatus.EXPERIMENTAL,
    SeriesStatus.DEVELOPMENT,
    ]


def get_dsd_source():
    """For convenience: the `IDistroSeriesDifferenceSource` utility."""
    return getUtility(IDistroSeriesDifferenceSource)


class DistroSeriesNavigation(GetitemNavigation, BugTargetTraversalMixin,
    StructuralSubscriptionTargetTraversalMixin):

    usedfor = IDistroSeries

    @stepthrough('+lang')
    def traverse_lang(self, langcode):
        """Retrieve the DistroSeriesLanguage or a dummy if one it is None."""
        # We do not want users to see the 'en' pofile because
        # we store the messages we want to translate as English.
        if langcode == 'en':
            raise NotFoundError(langcode)

        langset = getUtility(ILanguageSet)
        try:
            lang = langset[langcode]
        except IndexError:
            # Unknown language code.
            raise NotFoundError

        distroserieslang = self.context.getDistroSeriesLanguageOrDummy(lang)

        # Check if user is able to view the translations for
        # this distribution series language.
        # If not, raise TranslationUnavailable.
        check_distroseries_translations_viewable(self.context)

        return distroserieslang

    @stepthrough('+source')
    def source(self, name):
        return self.context.getSourcePackage(name)

    # sabdfl 17/10/05 please keep this old location here for
    # LaunchpadIntegration on Breezy, unless you can figure out how to
    # redirect to the newer +source, defined above
    @stepthrough('+sources')
    def sources(self, name):
        return self.context.getSourcePackage(name)

    @stepthrough('+package')
    def package(self, name):
        return self.context.getBinaryPackage(name)

    @stepto('+latest-full-language-pack')
    def latest_full_language_pack(self):
        if self.context.last_full_language_pack_exported is None:
            return None
        else:
            return self.context.last_full_language_pack_exported.file

    @stepto('+latest-delta-language-pack')
    def redirect_latest_delta_language_pack(self):
        if self.context.last_delta_language_pack_exported is None:
            return None
        else:
            return self.context.last_delta_language_pack_exported.file

    @stepthrough('+upload')
    def traverse_queue(self, id):
        return getUtility(IPackageUploadSet).get(id)


class DistroSeriesBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `IDistroSeries`."""

    @property
    def text(self):
        return self.context.named_version


class DistroSeriesFacets(StandardLaunchpadFacets):

    usedfor = IDistroSeries
    enable_only = ['overview', 'branches', 'bugs', 'specifications',
                   'translations']


class DistroSeriesOverviewMenu(
    ApplicationMenu, StructuralSubscriptionMenuMixin):

    usedfor = IDistroSeries
    facet = 'overview'

    @property
    def links(self):
        links = ['edit',
                 'driver',
                 'answers',
                 'packaging',
                 'needs_packaging',
                 'builds',
                 'queue',
                 'add_port',
                 'create_milestone',
                 'initseries',
                 ]
        add_subscribe_link(links)
        links.append('admin')
        return links

    @enabled_with_permission('launchpad.Admin')
    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def driver(self):
        text = 'Appoint driver'
        summary = 'Someone with permission to set goals for this series'
        return Link('+driver', text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def create_milestone(self):
        text = 'Create milestone'
        summary = 'Register a new milestone for this series'
        return Link('+addmilestone', text, summary, icon='add')

    def packaging(self):
        text = 'All upstream links'
        summary = 'A listing of source packages and their upstream projects'
        return Link('+packaging', text, summary=summary, icon='info')

    def needs_packaging(self):
        text = 'Needs upstream links'
        summary = 'A listing of source packages without upstream projects'
        return Link('+needs-packaging', text, summary=summary, icon='info')

    # A search link isn't needed because the distro series overview
    # has a search form.
    def answers(self):
        text = 'Ask a question'
        url = canonical_url(self.context.distribution) + '/+addquestion'
        return Link(url, text, icon='add')

    @enabled_with_permission('launchpad.Admin')
    def add_port(self):
        text = 'Add architecture'
        return Link('+addport', text, icon='add')

    @enabled_with_permission('launchpad.Moderate')
    def admin(self):
        text = 'Administer'
        return Link('+admin', text, icon='edit')

    def builds(self):
        text = 'Show builds'
        return Link('+builds', text, icon='info')

    def queue(self):
        text = 'Show uploads'
        return Link('+queue', text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def initseries(self):
        enabled = (
             not self.context.isInitializing() and
             not self.context.isInitialized())
        text = 'Initialize series'
        return Link('+initseries', text, icon='edit', enabled=enabled)


class DistroSeriesBugsMenu(ApplicationMenu, StructuralSubscriptionMenuMixin):

    usedfor = IDistroSeries
    facet = 'bugs'

    @property
    def links(self):
        links = ['cve',
                 'nominations',
                 ]
        add_subscribe_link(links)
        return links

    def cve(self):
        return Link('+cve', 'CVE reports', icon='cve')

    def nominations(self):
        return Link('+nominations', 'Review nominations', icon='bug')


class DistroSeriesSpecificationsMenu(NavigationMenu,
                                     HasSpecificationsMenuMixin):

    usedfor = IDistroSeries
    facet = 'specifications'
    links = [
        'listall', 'listdeclined', 'assignments', 'setgoals',
        'new', 'register_sprint']


class DistroSeriesPackageSearchView(PackageSearchViewBase):
    """Customised PackageSearchView for DistroSeries"""

    def contextSpecificSearch(self):
        """See `AbstractPackageSearchView`."""
        return self.context.searchPackages(self.text)

    label = 'Search packages'


class SeriesStatusMixin:
    """A mixin that provides status field support."""

    def createStatusField(self):
        """Create the 'status' field.

        Create the status vocabulary according to the current distroseries
        status:
         * stable   -> CURRENT, SUPPORTED, OBSOLETE
         * unstable -> EXPERIMENTAL, DEVELOPMENT, FROZEN, FUTURE, CURRENT
        """
        stable_status = (
            SeriesStatus.CURRENT,
            SeriesStatus.SUPPORTED,
            SeriesStatus.OBSOLETE,
            )

        if self.context.status not in stable_status:
            terms = [status for status in SeriesStatus.items
                     if status not in stable_status]
            terms.append(SeriesStatus.CURRENT)
        else:
            terms = stable_status

        status_vocabulary = SimpleVocabulary(
            [SimpleTerm(item, item.name, item.title) for item in terms])

        return form.Fields(
            Choice(__name__='status',
                   title=_('Status'),
                   default=self.context.status,
                   vocabulary=status_vocabulary,
                   description=_("Select the distroseries status."),
                   required=True))

    def updateDateReleased(self, status):
        """Update the datereleased field if the status is set to CURRENT."""
        if (self.context.datereleased is None and
            status == SeriesStatus.CURRENT):
            self.context.datereleased = UTC_NOW


class DerivedDistroSeriesMixin:

    @cachedproperty
    def has_unique_parent(self):
        return len(self.context.getParentSeries()) == 1

    @cachedproperty
    def unique_parent(self):
        if self.has_unique_parent:
            return self.context.getParentSeries()[0]
        else:
            None

    @cachedproperty
    def number_of_parents(self):
        return len(self.context.getParentSeries())

    def getParentName(self, multiple_parent_default=None):
        if self.has_unique_parent:
            return ("parent series '%s'" %
                self.unique_parent.displayname)
        else:
            if multiple_parent_default is not None:
                return multiple_parent_default
            else:
                return 'a parent series'


def word_differences_count(count):
    """Express "`count` differences" in words.

    For example, "1 package", or "2 packages" and so on.
    """
    return get_plural_text(count, "%d package", "%d packages") % count


class DistroSeriesView(LaunchpadView, MilestoneOverlayMixin,
                       DerivedDistroSeriesMixin):

    def initialize(self):
        super(DistroSeriesView, self).initialize()
        self.displayname = '%s %s' % (
            self.context.distribution.displayname,
            self.context.version)
        expose_structural_subscription_data_to_js(
            self.context, self.request, self.user)

    @property
    def page_title(self):
        """Return the HTML page title."""
        return '%s %s in Launchpad' % (
        self.context.distribution.title, self.context.version)

    def requestCountry(self):
        return ICountry(self.request, None)

    def browserLanguages(self):
        return browser_languages(self.request)

    def redirectToDistroFileBug(self):
        """Redirect to the distribution's filebug page.

        Filing a bug on a distribution series is not directly
        permitted; we redirect to the distribution's file
        """
        distro_url = canonical_url(
            self.context.distribution, view_name='+filebug')
        if self.request.form.get('no-redirect') is not None:
            distro_url += '?no-redirect'
        return self.request.response.redirect(distro_url)

    @cachedproperty
    def num_linked_packages(self):
        """The number of linked packagings for this distroseries."""
        return self.context.packagings.count()

    @property
    def num_unlinked_packages(self):
        """The number of unlinked packagings for this distroseries."""
        return self.context.getPrioritizedUnlinkedSourcePackages().count()

    @cachedproperty
    def recently_linked(self):
        """Return the packages that were most recently linked upstream."""
        return self.context.getMostRecentlyLinkedPackagings()

    @cachedproperty
    def needs_linking(self):
        """Return a list of 10 packages most in need of upstream linking."""
        # XXX sinzui 2010-02-26 bug=528648: This method causes a timeout.
        # return self.context.getPrioritizedUnlinkedSourcePackages()[:10]
        return None

    milestone_can_release = False

    @cachedproperty
    def milestone_batch_navigator(self):
        return BatchNavigator(self.context.all_milestones, self.request)

    def countDifferences(self, difference_type, needing_attention_only=True):
        """Count the number of differences of a given kind.

        :param difference_type: Type of `DistroSeriesDifference` to look for.
        :param needing_attention_only: Restrict count to differences that need
            attention?  If not, count all that can be viewed.
        """
        if needing_attention_only:
            status = (DistroSeriesDifferenceStatus.NEEDS_ATTENTION, )
        else:
            status = None

        differences = get_dsd_source().getForDistroSeries(
            self.context, difference_type=difference_type, status=status)
        return differences.count()

    @cachedproperty
    def num_version_differences_needing_attention(self):
        return self.countDifferences(
            DistroSeriesDifferenceType.DIFFERENT_VERSIONS)

    @cachedproperty
    def num_version_differences(self):
        return self.countDifferences(
            DistroSeriesDifferenceType.DIFFERENT_VERSIONS,
            needing_attention_only=False)

    def wordVersionDifferences(self):
        return word_differences_count(self.num_version_differences)

    @cachedproperty
    def num_differences_in_parent(self):
        return self.countDifferences(
            DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES)

    def wordDifferencesInParent(self):
        return word_differences_count(self.num_differences_in_parent)

    @cachedproperty
    def num_differences_in_child(self):
        return self.countDifferences(
            DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES)

    def wordDifferencesInChild(self):
        return word_differences_count(self.num_differences_in_child)

    def alludeToParent(self):
        """Wording to refer to the series' parent(s).

        If there is a single parent, returns its display name.  Otherwise
        says "a parent series" (more vague, but we could also name parents
        if there are very few).
        """
        if self.has_unique_parent:
            return self.unique_parent.displayname
        else:
            return "a parent series"

    @cachedproperty
    def link_to_version_diffs_needing_attention(self):
        """Return URL for +localpackagediffs page."""
        return canonical_url(self.context, view_name='+localpackagediffs')

    @property
    def link_to_all_version_diffs(self):
        """Return URL for +localdiffs page for all statuses."""
        return (
            "%s?field.package_type=all"
            % self.link_to_version_diffs_needing_attention)

    @property
    def link_to_differences_in_parent(self):
        """Return URL for +missingpackages page."""
        return canonical_url(self.context, view_name='+missingpackages')

    @property
    def link_to_differences_in_child(self):
        """Return URL for +uniquepackages page."""
        return canonical_url(self.context, view_name='+uniquepackages')


class DistroSeriesEditView(LaunchpadEditFormView, SeriesStatusMixin):
    """View class that lets you edit a DistroSeries object.

    It redirects to the main distroseries page after a successful edit.
    """
    schema = IDistroSeries
    field_names = ['displayname', 'title', 'summary', 'description']
    custom_widget('status', LaunchpadDropdownWidget)

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Edit %s details' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    def setUpFields(self):
        """See `LaunchpadFormView`.

        In addition to setting schema fields, also initialize the
        'status' field. See `createStatusField` method.
        """
        LaunchpadEditFormView.setUpFields(self)
        self.is_derivative = (
            not self.context.distribution.full_functionality)
        self.has_admin = check_permission('launchpad.Admin', self.context)
        if self.has_admin or self.is_derivative:
            # The user is an admin or this is an IDerivativeDistribution.
            self.form_fields = (
                self.form_fields + self.createStatusField())

    @action("Change")
    def change_action(self, action, data):
        """Update the context and redirects to its overviw page."""
        if self.has_admin or self.is_derivative:
            self.updateDateReleased(data.get('status'))
        self.updateContextFromData(data)
        self.request.response.addInfoNotification(
            'Your changes have been applied.')
        self.next_url = canonical_url(self.context)


class DistroSeriesAdminView(LaunchpadEditFormView, SeriesStatusMixin):
    """View class for administering a DistroSeries object.

    It redirects to the main distroseries page after a successful edit.
    """
    schema = IDistroSeries
    field_names = ['name', 'version', 'changeslist']
    custom_widget('status', LaunchpadDropdownWidget)

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Administer %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    def setUpFields(self):
        """Override `LaunchpadFormView`.

        In addition to setting schema fields, also initialize the
        'status' field. See `createStatusField` method.
        """
        LaunchpadEditFormView.setUpFields(self)
        self.form_fields = (
            self.form_fields + self.createStatusField())

    @action("Change")
    def change_action(self, action, data):
        """Update the context and redirects to its overviw page.

        Also, set 'datereleased' when a unstable distroseries is made
        CURRENT.
        """
        self.updateDateReleased(data.get('status'))
        self.updateContextFromData(data)

        self.request.response.addInfoNotification(
            'Your changes have been applied.')
        self.next_url = canonical_url(self.context)


class IDistroSeriesAddForm(Interface):

    name = copy_field(
        IDistroSeries["name"], description=_(
            "The name of this series as used for URLs."))

    version = copy_field(
        IDistroSeries["version"], description=_(
            "The version of the new series."))

    displayname = copy_field(
        IDistroSeries["displayname"], description=_(
            "The name of the new series as it would "
            "appear in a paragraph."))

    summary = copy_field(IDistroSeries["summary"])


class DistroSeriesAddView(LaunchpadFormView):
    """A view to create an `IDistroSeries`."""
    schema = IDistroSeriesAddForm
    field_names = [
        'name',
        'version',
        'displayname',
        'summary',
        ]

    help_links = {
        "name": u"/+help-registry/distribution-add-series.html#codename",
        }

    label = 'Add a series'
    page_title = label

    @action(_('Add Series'), name='create')
    def createAndAdd(self, action, data):
        """Create and add a new Distribution Series"""
        # 'series' is a cached property so this won't issue 2 queries.
        if self.context.series:
            previous_series = self.context.series[0]
        else:
            previous_series = None
        # previous_series will be None if there isn't one.
        distroseries = self.context.newSeries(
            name=data['name'],
            displayname=data['displayname'],
            title=data['displayname'],
            summary=data['summary'],
            description=u"",
            version=data['version'],
            previous_series=previous_series,
            registrant=self.user)
        notify(ObjectCreatedEvent(distroseries))
        self.next_url = canonical_url(distroseries)
        return distroseries

    @property
    def cancel_url(self):
        return canonical_url(self.context)


def seriesToVocab(series):
    # Simple helper function to format series data into a dict:
    # {'value':series_id, 'api_uri': api_uri, 'title': series_title}.
    return {
        'value': series.id,
        'title': '%s: %s'
            % (series.distribution.displayname, series.title),
        'api_uri': canonical_url(
            series, path_only_if_possible=True)}


class EmptySchema(Interface):
    pass


class DistroSeriesInitializeView(LaunchpadFormView):
    """A view to initialize an `IDistroSeries`."""

    schema = EmptySchema
    label = 'Initialize series'
    page_title = label

    def initialize(self):
        super(DistroSeriesInitializeView, self).initialize()
        cache = IJSONRequestCache(self.request).objects
        distribution = self.context.distribution
        is_first_derivation = not distribution.has_published_sources
        cache['is_first_derivation'] = is_first_derivation
        if (not is_first_derivation and
            self.context.previous_series is not None):
            cache['previous_series'] = seriesToVocab(
                self.context.previous_series)
            previous_parents = self.context.previous_series.getParentSeries()
            cache['previous_parents'] = [
                seriesToVocab(series) for series in previous_parents]

    @action(u"Initialize Series", name='initialize')
    def submit(self, action, data):
        """Stub for the Javascript in the page to use."""

    @cachedproperty
    def show_derivation_form(self):
        return (
            not self.show_previous_series_empty_message and
            not self.show_already_initializing_message and
            not self.show_already_initialized_message and
            not self.show_no_publisher_message
            )

    @cachedproperty
    def show_previous_series_empty_message(self):
        # There is a problem here:
        # The distribution already has initialized series and this
        # distroseries has no previous_series.
        return (
            self.context.distribution.has_published_sources and
            self.context.previous_series is None)

    @cachedproperty
    def show_already_initialized_message(self):
        return self.context.isInitialized()

    @cachedproperty
    def show_already_initializing_message(self):
        return self.context.isInitializing()

    @cachedproperty
    def show_no_publisher_message(self):
        distribution = self.context.distribution
        publisherconfigset = getUtility(IPublisherConfigSet)
        pub_config = publisherconfigset.getByDistribution(distribution)
        return pub_config is None

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url


class DistroSeriesPackagesView(LaunchpadView):
    """A View to show series package to upstream package relationships."""

    label = 'All series packages linked to upstream project series'
    page_title = 'All upstream links'

    @cachedproperty
    def cached_packagings(self):
        """The batched upstream packaging links."""
        packagings = self.context.getPrioritizedPackagings()
        navigator = BatchNavigator(packagings, self.request, size=20)
        navigator.setHeadings('packaging', 'packagings')
        return navigator


# A helper to create package filtering radio button vocabulary.
NON_IGNORED = 'non-ignored'
HIGHER_VERSION_THAN_PARENT = 'higher-than-parent'
RESOLVED = 'resolved'
ALL = 'all'

DEFAULT_PACKAGE_TYPE = NON_IGNORED


def make_package_type_vocabulary(parent_name, higher_version_option=False):
    voc = [
        SimpleTerm(NON_IGNORED, NON_IGNORED, 'Non ignored packages'),
        SimpleTerm(RESOLVED, RESOLVED, "Resolved package differences"),
        SimpleTerm(ALL, ALL, 'All packages'),
        ]
    if higher_version_option:
        higher_term = SimpleTerm(
            HIGHER_VERSION_THAN_PARENT,
            HIGHER_VERSION_THAN_PARENT,
            "Ignored packages with a higher version than in %s"
                % parent_name)
        voc.insert(1, higher_term)
    return SimpleVocabulary(tuple(voc))


class DistroSeriesNeedsPackagesView(LaunchpadView):
    """A View to show series package to upstream package relationships."""

    label = 'Packages that need upstream packaging links'
    page_title = 'Needs upstream links'

    @cachedproperty
    def cached_unlinked_packages(self):
        """The batched `ISourcePackage`s that needs packaging links."""
        packages = self.context.getPrioritizedUnlinkedSourcePackages()
        navigator = BatchNavigator(packages, self.request, size=20)
        navigator.setHeadings('package', 'packages')
        return navigator


class IDifferencesFormSchema(Interface):
    name_filter = TextLine(
        title=_("Package name contains"), required=False)

    selected_differences = List(
        title=_('Selected differences'),
        value_type=Choice(vocabulary="DistroSeriesDifferences"),
        description=_("Select the differences for syncing."),
        required=True)

    sponsored_person = Choice(
        title=u"Person being sponsored", vocabulary='ValidPerson',
        required=False)


class DistroSeriesDifferenceBaseView(LaunchpadFormView,
                                     PackageCopyingMixin,
                                     DerivedDistroSeriesMixin):
    """Base class for all pages presenting differences between
    a derived series and its parent."""
    schema = IDifferencesFormSchema
    field_names = ['selected_differences', 'sponsored_person']
    custom_widget('selected_differences', LabeledMultiCheckBoxWidget)
    custom_widget('package_type', LaunchpadRadioWidget)
    custom_widget(
        'sponsored_person', PersonPickerWidget,
        header="Select person being sponsored", show_assign_me_button=False)

    # Differences type to display. Can be overrided by sublasses.
    differences_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
    show_parent = True
    show_parent_version = True
    show_derived_version = True
    show_package_diffs = True
    # Packagesets display.
    show_parent_packagesets = False
    show_packagesets = False
    # Search vocabulary.
    search_higher_parent_option = False

    def initialize_sync_label(self, label):
        # Owing to the design of Action/Actions in zope.formlib.form - actions
        # is actually a descriptor that copies itself and its actions when
        # accessed - this has the effect of making a shallow copy of the sync
        # action which we can modify.
        actions = self.actions
        sync_action = next(
            action for action in actions if action.name == "sync")
        sync_action.label = label
        # Mask the actions descriptor with an instance variable.
        self.actions = actions.__class__(
            *((sync_action if action.name == "sync" else action)
              for action in actions))

    @property
    def label(self):
        return NotImplementedError()

    def setupPackageFilterRadio(self):
        if self.has_unique_parent:
            parent_name = "'%s'" % self.unique_parent.displayname
        else:
            parent_name = 'parent'
        return form.Fields(Choice(
            __name__='package_type',
            vocabulary=make_package_type_vocabulary(
                parent_name,
                self.search_higher_parent_option),
            default=DEFAULT_PACKAGE_TYPE,
            required=True))

    def setUpFields(self):
        """Add the selected differences field.

        As this field depends on other search/filtering field values
        for its own vocabulary, we set it up after all the others.
        """
        super(DistroSeriesDifferenceBaseView, self).setUpFields()
        self.form_fields = (
            self.setupPackageFilterRadio() +
            self.form_fields)

    def _sync_sources(self, action, data):
        """Synchronise packages from the parent series to this one."""
        # We're doing a direct copy sync here as an interim measure
        # until we work out if it's fast enough to work reliably.  If it
        # isn't, we need to implement a way of flagging sources 'to be
        # synced' and write a job runner to do it in the background.

        selected_differences = data['selected_differences']
        sources = [
            diff.parent_source_pub
            for diff in selected_differences]

        # PackageCopyingMixin.do_copy() does the work of copying and
        # setting up on-page notifications.
        series_url = canonical_url(self.context)
        series_title = self.context.displayname

        # If the series is released, sync packages in the "updates" pocket.
        if self.context.supported:
            destination_pocket = PackagePublishingPocket.UPDATES
        else:
            destination_pocket = PackagePublishingPocket.RELEASE

        sponsored_person = data.get("sponsored_person")

        if self.do_copy(
            'selected_differences', sources, self.context.main_archive,
            self.context, destination_pocket, include_binaries=False,
            dest_url=series_url, dest_display_name=series_title,
            person=self.user, sponsored_person=sponsored_person):
            # The copy worked so we redirect back to show the results. Include
            # the query string so that the user ends up on the same batch page
            # with the same filtering parameters as before.
            self.next_url = self.request.getURL(include_query=True)

    @property
    def action_url(self):
        """The request URL including query string.

        Forms should post to the view with a query string containing the
        active batch and filtering parameters. Actions should then redirect
        using that information so that the user is left on the same batch
        page, with the same filtering parameters, as the page from which they
        submitted the form.
        """
        return self.request.getURL(include_query=True)

    def validate_sync(self, action, data):
        """Validate selected differences."""
        form.getWidgetsData(self.widgets, self.prefix, data)

        if len(data.get('selected_differences', [])) == 0:
            self.setFieldError(
                'selected_differences', 'No differences selected.')

    def canPerformSync(self, *args):
        """Return whether a sync can be performed.

        This method is used as a condition for the above sync action, as
        well as directly in the template.
        """
        archive = self.context.main_archive
        has_perm = (self.user is not None and (
                        archive.hasAnyPermission(self.user) or
                        check_permission('launchpad.Append', archive)))
        return (has_perm and
                self.cached_differences.batch.total() > 0)

    @cachedproperty
    def pending_syncs(self):
        """Pending synchronization jobs for this distroseries.

        :return: A dict mapping package names to pending sync jobs.
        """
        job_source = getUtility(IPlainPackageCopyJobSource)
        return job_source.getPendingJobsPerPackage(self.context)

    @cachedproperty
    def pending_dsd_updates(self):
        """Pending `DistroSeriesDifference` update jobs.

        :return: A `set` of `DistroSeriesDifference`s that have pending
            `DistroSeriesDifferenceJob`s.
        """
        job_source = getUtility(IDistroSeriesDifferenceJobSource)
        return job_source.getPendingJobsForDifferences(
            self.context, self.cached_differences.batch)

    def hasPendingDSDUpdate(self, dsd):
        """Have there been changes that `dsd` is still being updated for?"""
        return dsd in self.pending_dsd_updates

    def pendingSync(self, dsd):
        """Is there a package-copying job pending to resolve `dsd`?"""
        return self.pending_syncs.get(dsd.source_package_name.name)

    def isNewerThanParent(self, dsd):
        """Is the child's version of this package newer than the parent's?

        If it is, there's no point in offering to sync it.

        Any version is considered "newer" than a missing version.
        """
        # This is trickier than it looks: versions are not totally
        # ordered.  Two non-identical versions may compare as equal.
        # Only consider cases where the child's version is conclusively
        # newer, not where the relationship is in any way unclear.
        if dsd.parent_source_version is None:
            # There is nothing to sync; the child is up to date and if
            # anything needs updating, it's the parent.
            return True
        if dsd.source_version is None:
            # The child doesn't have this package.  Treat that as the
            # parent being newer.
            return False
        comparison = apt_pkg.version_compare(
            dsd.parent_source_version, dsd.source_version)
        return comparison < 0

    def canRequestSync(self, dsd):
        """Does it make sense to request a sync for this difference?"""
        # There are three conditions for this: it doesn't make sense to
        # sync if the dsd is resolved, if the child's version of the package
        # is newer than the parent's version, or if there is already a sync
        # pending.
        return (
            dsd.status != DistroSeriesDifferenceStatus.RESOLVED and
            not self.isNewerThanParent(dsd) and not self.pendingSync(dsd))

    def describeJobs(self, dsd):
        """Describe any jobs that may be pending for `dsd`.

        Shows "synchronizing..." if the entry is being synchronized,
        "updating..." if the DSD is being updated with package changes and
        "waiting in <queue>..." if the package is in the distroseries
        queues (<queue> will be NEW or UNAPPROVED and links to the
        relevant queue page).

        :param dsd: A `DistroSeriesDifference` on the page.
        :return: An HTML text describing work that is pending or in
            progress for `dsd`; or None.
        """
        has_pending_dsd_update = self.hasPendingDSDUpdate(dsd)
        pending_sync = self.pendingSync(dsd)
        if not has_pending_dsd_update and not pending_sync:
            return None

        description = []
        if has_pending_dsd_update:
            description.append("updating")
        if pending_sync is not None:
            # If the pending sync is waiting in the distroseries queues,
            # provide a handy link to there.
            queue_item = getUtility(IPackageUploadSet).getByPackageCopyJobIDs(
                (pending_sync.id,)).any()
            if queue_item is None:
                description.append("synchronizing")
            else:
                url = urlappend(
                    canonical_url(self.context), "+queue?queue_state=%s" %
                        queue_item.status.value)
                description.append('waiting in <a href="%s">%s</a>' %
                    (url, queue_item.status.name))
        return " and ".join(description) + "&hellip;"

    @property
    def specified_name_filter(self):
        """If specified, return the name filter from the GET form data."""
        requested_name_filter = self.request.query_string_params.get(
            'field.name_filter')

        if requested_name_filter and requested_name_filter[0]:
            return requested_name_filter[0]
        else:
            return None

    @property
    def specified_packagesets_filter(self):
        """If specified, return Packagesets given in the GET form data."""
        packageset_ids = (
            self.request.query_string_params.get("field.packageset", []))
        packageset_ids = set(
            int(packageset_id) for packageset_id in packageset_ids
            if packageset_id.isdigit())
        packagesets = getUtility(IPackagesetSet).getBySeries(self.context)
        packagesets = set(
            packageset for packageset in packagesets
            if packageset.id in packageset_ids)
        return None if len(packagesets) == 0 else packagesets

    @property
    def specified_changed_by_filter(self):
        """If specified, return Persons given in the GET form data."""
        get_person_by_name = getUtility(IPersonSet).getByName
        changed_by_names = set(
            self.request.query_string_params.get("field.changed_by", ()))
        changed_by = (
            get_person_by_name(name) for name in changed_by_names)
        changed_by = set(
            person for person in changed_by if person is not None)
        return None if len(changed_by) == 0 else changed_by

    @property
    def specified_package_type(self):
        """If specified, return the package type filter from the GET form
        data.
        """
        package_type = self.request.query_string_params.get(
            'field.package_type')
        if package_type and package_type[0]:
            return package_type[0]
        else:
            return DEFAULT_PACKAGE_TYPE

    @cachedproperty
    def cached_differences(self):
        """Return a batch navigator of filtered results."""
        package_type_dsd_status = {
            NON_IGNORED: DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
            HIGHER_VERSION_THAN_PARENT: (
                DistroSeriesDifferenceStatus.BLACKLISTED_CURRENT),
            RESOLVED: DistroSeriesDifferenceStatus.RESOLVED,
            ALL: None,
        }

        # If the package_type option is not supported, add an error to
        # the field and return an empty list.
        if self.specified_package_type not in package_type_dsd_status:
            self.setFieldError('package_type', 'Invalid option')
            differences = []
        else:
            status = package_type_dsd_status[self.specified_package_type]
            child_version_higher = (
                self.specified_package_type == HIGHER_VERSION_THAN_PARENT)
            differences = get_dsd_source().getForDistroSeries(
                self.context, difference_type=self.differences_type,
                name_filter=self.specified_name_filter, status=status,
                child_version_higher=child_version_higher,
                packagesets=self.specified_packagesets_filter,
                changed_by=self.specified_changed_by_filter)

        return BatchNavigator(differences, self.request)

    def parent_changelog_url(self, distroseriesdifference):
        """The URL to the /parent/series/+source/package/+changelog """
        distro = distroseriesdifference.parent_series.distribution
        dsp = distro.getSourcePackage(
            distroseriesdifference.source_package_name)
        return urlappend(canonical_url(dsp), '+changelog')


class DistroSeriesLocalDifferencesView(DistroSeriesDifferenceBaseView,
                                       LaunchpadFormView):
    """Present differences of type DIFFERENT_VERSIONS between
    a derived series and its parent.
    """
    page_title = 'Local package differences'
    differences_type = DistroSeriesDifferenceType.DIFFERENT_VERSIONS
    show_packagesets = True
    search_higher_parent_option = True

    def initialize(self):
        # Update the label for sync action.
        if self.has_unique_parent:
            parent_name = "'%s'" % self.unique_parent.displayname
        else:
            parent_name = 'Parent'
        self.initialize_sync_label(
            "Sync Selected %s Versions into %s" % (
                parent_name,
                self.context.displayname,
                ))
        super(DistroSeriesLocalDifferencesView, self).initialize()

    @property
    def explanation(self):
        return structured(
            "Source packages shown here are present in both %s "
            "and %s, but are different somehow. "
            "Changes could be in either or both series so check the "
            "versions (and the diff if necessary) before syncing the parent "
            'version (<a href="/+help-soyuz/derived-series-syncing.html" '
            'target="help">Read more about syncing from a parent series'
            '</a>).',
            self.context.displayname,
            self.getParentName())

    @property
    def label(self):
        return (
            "Source package differences between '%s' and"
            " %s" % (
                self.context.displayname,
                self.getParentName(multiple_parent_default='parent series'),
                ))

    @action(_("Sync Sources"), name="sync", validator='validate_sync',
            condition='canPerformSync')
    def sync_sources(self, action, data):
        self._sync_sources(action, data)

    def getUpgrades(self):
        """Find straightforward package upgrades.

        These are updates for packages that this distroseries shares
        with a parent series, for which there have been updates in the
        parent, and which do not have any changes in this series that
        might complicate a sync.

        :return: A result set of `DistroSeriesDifference`s.
        """
        return get_dsd_source().getSimpleUpgrades(self.context)

    @action(_("Upgrade Packages"), name="upgrade", condition='canUpgrade')
    def upgrade(self, action, data):
        """Request synchronization of straightforward package upgrades."""
        self.requestUpgrades()

    def requestUpgrades(self):
        """Request sync of packages that can be easily upgraded."""
        target_distroseries = self.context
        copies = [
            (
                dsd.source_package_name.name,
                dsd.parent_source_version,
                dsd.parent_series.main_archive,
                target_distroseries.main_archive,
                target_distroseries,
                PackagePublishingPocket.RELEASE,
            )
            for dsd in self.getUpgrades()]
        getUtility(IPlainPackageCopyJobSource).createMultiple(
            copies, self.user, copy_policy=PackageCopyPolicy.MASS_SYNC)

        self.request.response.addInfoNotification(
            (u"Upgrades of {context.displayname} packages have been "
             u"requested. Please give Launchpad some time to complete "
             u"these.").format(context=self.context))

    def canUpgrade(self, action=None):
        """Should the form offer a packages upgrade?"""
        if getFeatureFlag("soyuz.derived_series_upgrade.enabled") is None:
            return False
        elif self.context.status not in UPGRADABLE_SERIES_STATUSES:
            # A feature freeze precludes blanket updates.
            return False
        elif self.getUpgrades().is_empty():
            # There are no simple updates to perform.
            return False
        else:
            queue = PackageUploadQueue(self.context, None)
            return check_permission("launchpad.Edit", queue)


class DistroSeriesMissingPackagesView(DistroSeriesDifferenceBaseView,
                                      LaunchpadFormView):
    """Present differences of type MISSING_FROM_DERIVED_SERIES between
    a derived series and its parent.
    """
    page_title = 'Missing packages'
    differences_type = DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES
    show_derived_version = False
    show_package_diffs = False
    show_parent_packagesets = True

    def initialize(self):
        # Update the label for sync action.
        self.initialize_sync_label(
            "Include Selected packages into %s" % (
                self.context.displayname,
                ))
        super(DistroSeriesMissingPackagesView, self).initialize()

    @property
    def explanation(self):
        return structured(
            "Packages that are listed here are those that have been added to "
            "the specific packages in %s that were used to create %s. "
            "They are listed here so you can consider including them in %s.",
            self.getParentName(),
            self.context.displayname,
            self.context.displayname)

    @property
    def label(self):
        return (
            "Packages in %s but not in '%s'" % (
                self.getParentName(),
                self.context.displayname,
                ))

    @action(_("Sync Sources"), name="sync", validator='validate_sync',
            condition='canPerformSync')
    def sync_sources(self, action, data):
        self._sync_sources(action, data)


class DistroSeriesUniquePackagesView(DistroSeriesDifferenceBaseView,
                                     LaunchpadFormView):
    """Present differences of type UNIQUE_TO_DERIVED_SERIES between
    a derived series and its parent.
    """
    page_title = 'Unique packages'
    differences_type = DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES
    show_parent = True
    show_parent_version = False  # The DSDs are unique to the derived series.
    show_package_diffs = False
    show_packagesets = True

    def initialize(self):
        super(DistroSeriesUniquePackagesView, self).initialize()

    @property
    def explanation(self):
        return structured(
            "Packages that are listed here are those that have been added to "
            "%s but are not yet part of %s.",
            self.context.displayname,
            self.getParentName())

    @property
    def label(self):
        return (
            "Packages in '%s' but not in %s" % (
                self.context.displayname,
                self.getParentName(),
                ))

    def canPerformSync(self, *args):
        return False
