# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for products."""

__metaclass__ = type

__all__ = [
    'ProductAddSeriesView',
    'ProductAddView',
    'ProductAddViewBase',
    'ProductAdminView',
    'ProductBrandingView',
    'ProductBugsMenu',
    'ProductConfigureBase',
    'ProductConfigureAnswersView',
    'ProductConfigureBlueprintsView',
    'ProductDownloadFileMixin',
    'ProductDownloadFilesView',
    'ProductEditPeopleView',
    'ProductEditView',
    'ProductFacets',
    'ProductInvolvementView',
    'ProductNavigation',
    'ProductNavigationMenu',
    'ProductOverviewMenu',
    'ProductPackagesView',
    'ProductPackagesPortletView',
    'ProductPurchaseSubscriptionView',
    'ProductRdfView',
    'ProductReviewLicenseView',
    'ProductSeriesSetView',
    'ProductSetBreadcrumb',
    'ProductSetFacets',
    'ProductSetNavigation',
    'ProductSetReviewLicensesView',
    'ProductSetView',
    'ProductSpecificationsMenu',
    'ProductView',
    'SortSeriesMixin',
    'ProjectAddStepOne',
    'ProjectAddStepTwo',
    ]


from operator import attrgetter

from lazr.delegates import delegates
from lazr.restful.interface import copy_field
from lazr.restful.interfaces import IJSONRequestCache
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.event import notify
from zope.formlib import form
from zope.formlib.interfaces import WidgetInputError
from zope.formlib.widget import CustomWidgetFactory
from zope.formlib.widgets import (
    CheckBoxWidget,
    TextAreaWidget,
    TextWidget,
    )
from zope.interface import (
    implements,
    Interface,
    )
from zope.lifecycleevent import ObjectCreatedEvent
from zope.schema import (
    Bool,
    Choice,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.answers.browser.faqtarget import FAQTargetNavigationMixin
from lp.answers.browser.questiontarget import (
    QuestionTargetFacetMixin,
    QuestionTargetTraversalMixin,
    )
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    ReturnToReferrerMixin,
    safe_action,
    )
from lp.app.browser.lazrjs import (
    BooleanChoiceWidget,
    InlinePersonEditPickerWidget,
    TextLineEditorWidget,
    )
from lp.app.browser.multistep import (
    MultiStepView,
    StepView,
    )
from lp.app.browser.stringformatter import FormattersAPI
from lp.app.browser.tales import (
    format_link,
    MenuAPI,
    )
from lp.app.enums import (
    InformationType,
    PROPRIETARY_INFORMATION_TYPES,
    PUBLIC_PROPRIETARY_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.app.errors import NotFoundError
from lp.app.interfaces.headings import IEditableContextTitle
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.utilities import json_dump_information_types
from lp.app.vocabularies import InformationTypeVocabulary
from lp.app.widgets.date import DateWidget
from lp.app.widgets.itemswidgets import (
    CheckBoxMatrixWidget,
    LaunchpadRadioWidget,
    LaunchpadRadioWidgetWithDescription,
    )
from lp.app.widgets.popup import PersonPickerWidget
from lp.app.widgets.product import (
    GhostWidget,
    LicenseWidget,
    ProductNameWidget,
    )
from lp.app.widgets.textwidgets import StrippedTextWidget
from lp.blueprints.browser.specificationtarget import (
    HasSpecificationsMenuMixin,
    )
from lp.bugs.browser.bugtask import (
    BugTargetTraversalMixin,
    get_buglisting_search_filter_url,
    )
from lp.bugs.browser.structuralsubscription import (
    expose_structural_subscription_data_to_js,
    StructuralSubscriptionMenuMixin,
    StructuralSubscriptionTargetTraversalMixin,
    )
from lp.bugs.interfaces.bugtask import RESOLVED_BUGTASK_STATUSES
from lp.code.browser.branchref import BranchRef
from lp.code.browser.sourcepackagerecipelisting import HasRecipesMenuMixin
from lp.registry.browser import (
    add_subscribe_link,
    BaseRdfView,
    )
from lp.registry.browser.announcement import HasAnnouncementsView
from lp.registry.browser.branding import BrandingChangeView
from lp.registry.browser.menu import (
    IRegistryCollectionNavigationMenu,
    RegistryCollectionActionMenuBase,
    )
from lp.registry.browser.pillar import (
    PillarBugsMenu,
    PillarInvolvementView,
    PillarNavigationMixin,
    PillarViewMixin,
    )
from lp.registry.browser.productseries import get_series_branch_error
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import (
    IProduct,
    IProductReviewSearch,
    IProductSet,
    License,
    LicenseStatus,
    )
from lp.registry.interfaces.productrelease import (
    IProductRelease,
    IProductReleaseSet,
    )
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.services.config import config
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.feeds.browser import FeedsMixin
from lp.services.fields import (
    PillarAliases,
    PublicPersonChoice,
    )
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    sorted_version_numbers,
    StandardLaunchpadFacets,
    stepthrough,
    stepto,
    structured,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.interfaces import UnsafeFormGetSubmissionError
from lp.services.webapp.menu import NavigationMenu
from lp.services.worlddata.helpers import browser_languages
from lp.services.worlddata.interfaces.country import ICountry
from lp.translations.browser.customlanguagecode import (
    HasCustomLanguageCodesTraversalMixin,
    )


OR = ' OR '
SPACE = ' '


class ProductNavigation(
    Navigation, BugTargetTraversalMixin,
    FAQTargetNavigationMixin, HasCustomLanguageCodesTraversalMixin,
    QuestionTargetTraversalMixin, StructuralSubscriptionTargetTraversalMixin,
    PillarNavigationMixin):

    usedfor = IProduct

    @stepto('.bzr')
    def dotbzr(self):
        if self.context.development_focus.branch:
            return BranchRef(self.context.development_focus.branch)
        else:
            return None

    @stepthrough('+spec')
    def traverse_spec(self, name):
        spec = self.context.getSpecification(name)
        if not check_permission('launchpad.LimitedView', spec):
            return None
        return spec

    @stepthrough('+milestone')
    def traverse_milestone(self, name):
        return self.context.getMilestone(name)

    @stepthrough('+release')
    def traverse_release(self, name):
        return self.context.getRelease(name)

    @stepthrough('+announcement')
    def traverse_announcement(self, name):
        return self.context.getAnnouncement(name)

    @stepthrough('+commercialsubscription')
    def traverse_commercialsubscription(self, name):
        return self.context.commercial_subscription

    def traverse(self, name):
        return self.context.getSeries(name)


class ProductSetNavigation(Navigation):

    usedfor = IProductSet

    def traverse(self, name):
        product = self.context.getByName(name)
        if product is None:
            raise NotFoundError(name)
        return self.redirectSubTree(canonical_url(product))


class ProductLicenseMixin:
    """Adds licence validation and requests reviews of licences.

    Subclasses must inherit from Launchpad[Edit]FormView as well.

    Requires the "product" attribute be set in the child
    classes' action handler.
    """

    def validate(self, data):
        """Validate 'licenses' and 'license_info'.

        'licenses' must not be empty unless the product already
        exists and never has had a licence set.

        'license_info' must not be empty if "Other/Proprietary"
        or "Other/Open Source" is checked.
        """
        licenses = data.get('licenses', [])
        license_widget = self.widgets.get('licenses')
        if (len(licenses) == 0 and license_widget is not None):
            self.setFieldError(
                'licenses',
                'You must select at least one licence.  If you select '
                'Other/Proprietary or Other/OpenSource you must include a '
                'description of the licence.')
        elif License.OTHER_PROPRIETARY in licenses:
            if not data.get('license_info'):
                self.setFieldError(
                    'license_info',
                    'A description of the "Other/Proprietary" '
                    'licence you checked is required.')
        elif License.OTHER_OPEN_SOURCE in licenses:
            if not data.get('license_info'):
                self.setFieldError(
                    'license_info',
                    'A description of the "Other/Open Source" '
                    'licence you checked is required.')
        else:
            # Launchpad is ok with all licenses used in this project.
            pass


class ProductFacets(QuestionTargetFacetMixin, StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an IProduct."""

    usedfor = IProduct

    enable_only = ['overview', 'bugs', 'answers', 'specifications',
                   'translations', 'branches']

    links = StandardLaunchpadFacets.links

    def overview(self):
        text = 'Overview'
        summary = 'General information about %s' % self.context.displayname
        return Link('', text, summary)

    def bugs(self):
        text = 'Bugs'
        summary = 'Bugs reported about %s' % self.context.displayname
        return Link('', text, summary)

    def branches(self):
        text = 'Code'
        summary = 'Branches for %s' % self.context.displayname
        return Link('', text, summary)

    def specifications(self):
        text = 'Blueprints'
        summary = 'Feature specifications for %s' % self.context.displayname
        return Link('', text, summary)

    def translations(self):
        text = 'Translations'
        summary = 'Translations of %s in Launchpad' % self.context.displayname
        return Link('', text, summary)


class ProductInvolvementView(PillarInvolvementView):
    """Encourage configuration of involvement links for projects."""

    has_involvement = True

    @property
    def visible_disabled_link_names(self):
        """Show all disabled links...except blueprints"""
        involved_menu = MenuAPI(self).navigation
        all_links = involved_menu.keys()
        # The register blueprints link should not be shown since its use is
        # not encouraged.
        all_links.remove('register_blueprint')
        return all_links

    @cachedproperty
    def configuration_states(self):
        """Create a dictionary indicating the configuration statuses.

        Each app area will be represented in the return dictionary, except
        blueprints which we are not currently promoting.
        """
        states = {}
        states['configure_bugtracker'] = (
            self.context.bug_tracking_usage != ServiceUsage.UNKNOWN)
        states['configure_answers'] = (
            self.context.answers_usage != ServiceUsage.UNKNOWN)
        states['configure_translations'] = (
            self.context.translations_usage != ServiceUsage.UNKNOWN)
        states['configure_codehosting'] = (
            self.context.codehosting_usage != ServiceUsage.UNKNOWN)
        return states

    @property
    def configuration_links(self):
        """The enabled involvement links.

        Returns a list of dicts keyed by:
        'link' -- the menu link, and
        'configured' -- a boolean representing the configuration status.
        """
        overview_menu = MenuAPI(self.context).overview
        series_menu = MenuAPI(self.context.development_focus).overview
        configuration_names = [
            'configure_bugtracker',
            'configure_answers',
            'configure_translations',
            #'configure_blueprints',
            ]
        config_list = []
        config_statuses = self.configuration_states
        for key in configuration_names:
            config_list.append(dict(link=overview_menu[key],
                                    configured=config_statuses[key]))

        # Add the branch configuration in separately.
        set_branch = series_menu['set_branch']
        set_branch.text = 'Configure project branch'
        set_branch.summary = "Specify the location of this project's code."
        config_list.append(
            dict(link=set_branch,
                 configured=config_statuses['configure_codehosting']))
        return config_list

    @property
    def registration_completeness(self):
        """The percent complete for registration."""
        config_statuses = self.configuration_states
        configured = sum(1 for val in config_statuses.values() if val)
        scale = 100
        done = int(float(configured) / len(config_statuses) * scale)
        undone = scale - done
        return dict(done=done, undone=undone)

    @property
    def registration_done(self):
        """A boolean indicating that the services are fully configured."""
        return (self.registration_completeness['done'] == 100)


class ProductNavigationMenu(NavigationMenu):

    usedfor = IProduct
    facet = 'overview'
    links = [
        'details',
        'announcements',
        'downloads',
        ]

    def details(self):
        text = 'Details'
        return Link('', text)

    def announcements(self):
        text = 'Announcements'
        return Link('+announcements', text)

    def downloads(self):
        text = 'Downloads'
        return Link('+download', text)


class ProductEditLinksMixin(StructuralSubscriptionMenuMixin):
    """A mixin class for menus that need Product edit links."""

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')

    @enabled_with_permission('launchpad.BugSupervisor')
    def configure_bugtracker(self):
        text = 'Configure bug tracker'
        summary = 'Specify where bugs are tracked for this project'
        return Link('+configure-bugtracker', text, summary, icon='edit')

    @enabled_with_permission('launchpad.TranslationsAdmin')
    def configure_translations(self):
        text = 'Configure translations'
        summary = 'Allow users to submit translations for this project'
        return Link('+configure-translations', text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def configure_answers(self):
        text = 'Configure support tracker'
        summary = 'Allow users to ask questions on this project'
        return Link('+configure-answers', text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def configure_blueprints(self):
        text = 'Configure blueprints'
        summary = 'Enable tracking of feature planning.'
        return Link('+configure-blueprints', text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def branding(self):
        text = 'Change branding'
        return Link('+branding', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def reassign(self):
        text = 'Change people'
        return Link('+edit-people', text, icon='edit')

    @enabled_with_permission('launchpad.Moderate')
    def review_license(self):
        text = 'Review project'
        return Link('+review-license', text, icon='edit')

    @enabled_with_permission('launchpad.Moderate')
    def administer(self):
        text = 'Administer'
        return Link('+admin', text, icon='edit')

    @enabled_with_permission('launchpad.Driver')
    def sharing(self):
        return Link('+sharing', 'Sharing', icon='edit')


class IProductEditMenu(Interface):
    """A marker interface for the 'Change details' navigation menu."""


class IProductActionMenu(Interface):
    """A marker interface for the global action navigation menu."""


class ProductActionNavigationMenu(NavigationMenu, ProductEditLinksMixin):
    """A sub-menu for acting upon a Product."""

    usedfor = IProductActionMenu
    facet = 'overview'
    title = 'Actions'

    @cachedproperty
    def links(self):
        links = ['edit', 'review_license', 'administer', 'sharing']
        add_subscribe_link(links)
        return links


class ProductOverviewMenu(ApplicationMenu, ProductEditLinksMixin,
                          HasRecipesMenuMixin):

    usedfor = IProduct
    facet = 'overview'
    links = [
        'edit',
        'configure_answers',
        'configure_blueprints',
        'configure_bugtracker',
        'configure_translations',
        'reassign',
        'top_contributors',
        'distributions',
        'packages',
        'series',
        'series_add',
        'milestones',
        'downloads',
        'announce',
        'announcements',
        'administer',
        'review_license',
        'rdf',
        'branding',
        'view_recipes',
        ]

    def top_contributors(self):
        text = 'More contributors'
        return Link('+topcontributors', text, icon='info')

    def distributions(self):
        text = 'Distribution packaging information'
        return Link('+distributions', text, icon='info')

    def packages(self):
        text = 'Show distribution packages'
        return Link('+packages', text, icon='info')

    def series(self):
        text = 'View full history'
        return Link('+series', text, icon='info')

    @enabled_with_permission('launchpad.Driver')
    def series_add(self):
        text = 'Register a series'
        return Link('+addseries', text, icon='add')

    def milestones(self):
        text = 'View milestones'
        return Link('+milestones', text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def announce(self):
        text = 'Make announcement'
        summary = 'Publish an item of news for this project'
        return Link('+announce', text, summary, icon='add')

    def announcements(self):
        text = 'Read all announcements'
        enabled = bool(self.context.getAnnouncements())
        return Link('+announcements', text, icon='info', enabled=enabled)

    def rdf(self):
        text = structured(
            '<abbr title="Resource Description Framework">'
            'RDF</abbr> metadata')
        return Link('+rdf', text, icon='download')

    def downloads(self):
        text = 'Downloads'
        return Link('+download', text, icon='info')


class ProductBugsMenu(PillarBugsMenu, ProductEditLinksMixin):

    usedfor = IProduct
    facet = 'bugs'
    configurable_bugtracker = True

    @cachedproperty
    def links(self):
        links = ['filebug', 'bugsupervisor', 'cve']
        add_subscribe_link(links)
        links.append('configure_bugtracker')
        return links


class ProductSpecificationsMenu(NavigationMenu, ProductEditLinksMixin,
                                HasSpecificationsMenuMixin):
    usedfor = IProduct
    facet = 'specifications'
    links = ['configure_blueprints', 'listall', 'doc', 'assignments', 'new',
             'register_sprint']


def _cmp_distros(a, b):
    """Put Ubuntu first, otherwise in alpha order."""
    if a == 'ubuntu':
        return -1
    elif b == 'ubuntu':
        return 1
    else:
        return cmp(a, b)


class ProductSetBreadcrumb(Breadcrumb):
    """Return a breadcrumb for an `IProductSet`."""
    text = "Projects"


class ProductSetFacets(StandardLaunchpadFacets):
    """The links that will appear in the facet menu for the IProductSet."""

    usedfor = IProductSet

    enable_only = ['overview', 'branches']


class SortSeriesMixin:
    """Provide access to helpers for series."""

    def _sorted_filtered_list(self, filter=None):
        """Return a sorted, filtered list of series.

        The series list is sorted by version in reverse order.  It is also
        filtered by calling `filter` on every series.  If the `filter`
        function returns False, don't include the series.  With None (the
        default, include everything).

        The development focus is always first in the list.
        """
        series_list = []
        for series in self.product.series:
            if filter is None or filter(series):
                series_list.append(series)
        # In production data, there exist development focus series that are
        # obsolete.  This may be caused by bad data, or it may be intended
        # functionality.  In either case, ensure that the development focus
        # branch is first in the list.
        if self.product.development_focus in series_list:
            series_list.remove(self.product.development_focus)
        # Now sort the list by name with newer versions before older.
        series_list = sorted_version_numbers(series_list,
                                             key=attrgetter('name'))
        series_list.insert(0, self.product.development_focus)
        return series_list

    @property
    def sorted_series_list(self):
        """Return a sorted list of series.

        The series list is sorted by version in reverse order.
        The development focus is always first in the list.
        """
        return self._sorted_filtered_list()

    @property
    def sorted_active_series_list(self):
        """Like `sorted_series_list()` but filters out OBSOLETE series."""
        # Callback for the filter which only allows series that have not been
        # marked obsolete.
        def check_active(series):
            return series.status != SeriesStatus.OBSOLETE
        return self._sorted_filtered_list(check_active)


class ProductWithSeries:
    """A decorated product that includes series data.

    The extra data is included in this class to avoid repeated
    database queries.  Rather than hitting the database, the data is
    cached locally and simply returned.
    """

    # `series` and `development_focus` need to be declared as class
    # attributes so that this class will not delegate the actual instance
    # variables to self.product, which would bypass the caching.
    series = None
    development_focus = None
    delegates(IProduct, 'product')

    def __init__(self, product):
        self.product = product
        self.series = []
        for series in self.product.series:
            series_with_releases = SeriesWithReleases(series, parent=self)
            self.series.append(series_with_releases)
            if self.product.development_focus == series:
                self.development_focus = series_with_releases

        # Get all of the releases for all of the series in a single
        # query.  The query sorts the releases properly so we know the
        # resulting list is sorted correctly.
        series_by_id = dict((series.id, series) for series in self.series)
        self.release_by_id = {}
        milestones_and_releases = list(
            self.product.getMilestonesAndReleases())
        for milestone, release in milestones_and_releases:
            series = series_by_id[milestone.productseries.id]
            release_delegate = ReleaseWithFiles(release, parent=series)
            series.addRelease(release_delegate)
            self.release_by_id[release.id] = release_delegate


class DecoratedSeries:
    """A decorated series that includes helper attributes for templates."""
    delegates(IProductSeries, 'series')

    def __init__(self, series):
        self.series = series

    @property
    def css_class(self):
        """The highlight, lowlight, or normal CSS class."""
        if self.is_development_focus:
            return 'highlight'
        elif self.status == SeriesStatus.OBSOLETE:
            return 'lowlight'
        else:
            # This is normal presentation.
            return ''

    @cachedproperty
    def packagings(self):
        """Convert packagings to list to prevent multiple evaluations."""
        return list(self.series.packagings)


class SeriesWithReleases(DecoratedSeries):
    """A decorated series that includes releases.

    The extra data is included in this class to avoid repeated
    database queries.  Rather than hitting the database, the data is
    cached locally and simply returned.
    """

    # `parent` and `releases` need to be declared as class attributes so that
    # this class will not delegate the actual instance variables to
    # self.series, which would bypass the caching for self.releases and would
    # raise an AttributeError for self.parent.
    parent = None
    releases = None

    def __init__(self, series, parent):
        super(SeriesWithReleases, self).__init__(series)
        self.parent = parent
        self.releases = []

    def addRelease(self, release):
        self.releases.append(release)

    @cachedproperty
    def has_release_files(self):
        for release in self.releases:
            if len(release.files) > 0:
                return True
        return False


class ReleaseWithFiles:
    """A decorated release that includes product release files.

    The extra data is included in this class to avoid repeated
    database queries.  Rather than hitting the database, the data is
    cached locally and simply returned.
    """

    # `parent` needs to be declared as class attributes so that
    # this class will not delegate the actual instance variables to
    # self.release, which would raise an AttributeError.
    parent = None
    delegates(IProductRelease, 'release')

    def __init__(self, release, parent):
        self.release = release
        self.parent = parent
        self._files = None

    @property
    def files(self):
        """Cache the release files for all the releases in the product."""
        if self._files is None:
            # Get all of the files for all of the releases.  The query
            # returns all releases sorted properly.
            product = self.parent.parent
            release_delegates = product.release_by_id.values()
            files = getUtility(IProductReleaseSet).getFilesForReleases(
                release_delegates)
            for release_delegate in release_delegates:
                release_delegate._files = []
            for file in files:
                id = file.productrelease.id
                release_delegate = product.release_by_id[id]
                release_delegate._files.append(file)

        # self._files was set above, since self is actually in the
        # release_delegates variable.
        return self._files

    @property
    def name_with_codename(self):
        milestone = self.release.milestone
        if milestone.code_name:
            return "%s (%s)" % (milestone.name, milestone.code_name)
        else:
            return milestone.name

    @cachedproperty
    def total_downloads(self):
        """Total downloads of files associated with this release."""
        return sum(file.libraryfile.hits for file in self.files)


class ProductDownloadFileMixin:
    """Provides methods for managing download files."""

    @cachedproperty
    def product(self):
        """Product with all series, release and file data cached.

        Decorated classes are created, and they contain cached data
        obtained with a few queries rather than many iterated queries.
        """
        return ProductWithSeries(self.context)

    def deleteFiles(self, releases):
        """Delete the selected files from the set of releases.

        :param releases: A set of releases in the view.
        :return: The number of files deleted.
        """
        del_count = 0
        for release in releases:
            for release_file in release.files:
                if release_file.libraryfile.id in self.delete_ids:
                    release_file.destroySelf()
                    self.delete_ids.remove(release_file.libraryfile.id)
                    del_count += 1
        return del_count

    def getReleases(self):
        """Find the releases with download files for view."""
        raise NotImplementedError

    def processDeleteFiles(self):
        """If the 'delete_files' button was pressed, process the deletions."""
        del_count = None
        if 'delete_files' in self.form:
            if self.request.method == 'POST':
                self.delete_ids = [
                    int(value) for key, value in self.form.items()
                    if key.startswith('checkbox')]
                del(self.form['delete_files'])
                releases = self.getReleases()
                del_count = self.deleteFiles(releases)
            else:
                # If there is a form submission and it is not a POST then
                # raise an error.  This is to protect against XSS exploits.
                raise UnsafeFormGetSubmissionError(self.form['delete_files'])
        if del_count is not None:
            if del_count <= 0:
                self.request.response.addNotification(
                    "No files were deleted.")
            elif del_count == 1:
                self.request.response.addNotification(
                    "1 file has been deleted.")
            else:
                self.request.response.addNotification(
                    "%d files have been deleted." %
                    del_count)

    @cachedproperty
    def latest_release_with_download_files(self):
        """Return the latest release with download files."""
        for series in self.sorted_active_series_list:
            for release in series.releases:
                if len(list(release.files)) > 0:
                    return release
        return None

    @cachedproperty
    def has_download_files(self):
        for series in self.context.series:
            if series.status == SeriesStatus.OBSOLETE:
                continue
            for release in series.getCachedReleases():
                if len(list(release.files)) > 0:
                    return True
        return False


class ProductView(PillarViewMixin, HasAnnouncementsView, SortSeriesMixin,
                  FeedsMixin, ProductDownloadFileMixin):

    implements(IProductActionMenu, IEditableContextTitle)

    @property
    def maintainer_widget(self):
        return InlinePersonEditPickerWidget(
            self.context, IProduct['owner'],
            format_link(self.context.owner),
            header='Change maintainer', edit_view='+edit-people',
            step_title='Select a new maintainer', show_create_team=True)

    @property
    def driver_widget(self):
        return InlinePersonEditPickerWidget(
            self.context, IProduct['driver'],
            format_link(self.context.driver, empty_value="Not yet selected"),
            header='Change driver', edit_view='+edit-people',
            step_title='Select a new driver', show_create_team=True,
            null_display_value="Not yet selected",
            help_link="/+help-registry/driver.html")

    def __init__(self, context, request):
        HasAnnouncementsView.__init__(self, context, request)
        self.form = request.form_ng

    def initialize(self):
        super(ProductView, self).initialize()
        self.status_message = None
        product = self.context
        title_field = IProduct['title']
        title = "Edit this title"
        self.title_edit_widget = TextLineEditorWidget(
            product, title_field, title, 'h1', max_width='95%',
            truncate_lines=2)
        programming_lang = IProduct['programminglang']
        title = 'Edit programming languages'
        additional_arguments = {
            'width': '9em',
            'css_class': 'nowrap'}
        if self.context.programminglang is None:
            additional_arguments.update(dict(
                default_text='Not yet specified',
                initial_value_override='',
                ))
        self.languages_edit_widget = TextLineEditorWidget(
            product, programming_lang, title, 'span', **additional_arguments)
        self.show_programming_languages = bool(
            self.context.programminglang or
            check_permission('launchpad.Edit', self.context))
        expose_structural_subscription_data_to_js(
            self.context, self.request, self.user)

    @property
    def page_title(self):
        return '%s in Launchpad' % self.context.displayname

    @property
    def page_description(self):
        return '\n'.filter(
            None,
            [self.context.summary, self.context.description])

    @property
    def show_license_status(self):
        return self.context.license_status != LicenseStatus.OPEN_SOURCE

    @property
    def freshmeat_url(self):
        if self.context.freshmeatproject:
            return ("http://freshmeat.net/projects/%s"
                % self.context.freshmeatproject)
        return None

    @property
    def sourceforge_url(self):
        if self.context.sourceforgeproject:
            return ("http://sourceforge.net/projects/%s"
                % self.context.sourceforgeproject)
        return None

    @property
    def has_external_links(self):
        return (self.context.homepageurl or
                self.context.sourceforgeproject or
                self.context.freshmeatproject or
                self.context.wikiurl or
                self.context.screenshotsurl or
                self.context.downloadurl)

    @property
    def external_links(self):
        """The project's external links.

        The home page link is not included because its link must have the
        rel=nofollow attribute.
        """
        from lp.services.webapp.menu import MenuLink
        urls = [
            ('Sourceforge project', self.sourceforge_url),
            ('Freshmeat record', self.freshmeat_url),
            ('Wiki', self.context.wikiurl),
            ('Screenshots', self.context.screenshotsurl),
            ('External downloads', self.context.downloadurl),
            ]
        links = []
        for (text, url) in urls:
            if url is not None:
                menu_link = MenuLink(
                    Link(url, text, icon='external-link', enabled=True))
                menu_link.url = url
                links.append(menu_link)
        return links

    @property
    def should_display_homepage(self):
        return (self.context.homepageurl and
                self.context.homepageurl not in
                    [self.freshmeat_url, self.sourceforge_url])

    def requestCountry(self):
        return ICountry(self.request, None)

    def browserLanguages(self):
        return browser_languages(self.request)

    def getClosedBugsURL(self, series):
        status = [status.title for status in RESOLVED_BUGTASK_STATUSES]
        url = canonical_url(series) + '/+bugs'
        return get_buglisting_search_filter_url(url, status=status)

    @property
    def can_purchase_subscription(self):
        return (check_permission('launchpad.Edit', self.context)
                and not self.context.qualifies_for_free_hosting)

    @cachedproperty
    def effective_driver(self):
        """Return the product driver or the project driver."""
        if self.context.driver is not None:
            driver = self.context.driver
        elif (self.context.project is not None and
              self.context.project.driver is not None):
            driver = self.context.project.driver
        else:
            driver = None
        return driver

    @cachedproperty
    def show_commercial_subscription_info(self):
        """Should subscription information be shown?

        Subscription information is only shown to the project maintainers,
        Launchpad admins, and members of the Launchpad commercial team.  The
        first two are allowed via the Launchpad.Edit permission.  The latter
        is allowed via Launchpad.Commercial.
        """
        return (check_permission('launchpad.Edit', self.context) or
                check_permission('launchpad.Commercial', self.context))

    @cachedproperty
    def show_license_info(self):
        """Should the view show the extra licence information."""
        return (
            License.OTHER_OPEN_SOURCE in self.context.licenses
            or License.OTHER_PROPRIETARY in self.context.licenses)

    @cachedproperty
    def is_proprietary(self):
        """Is the project proprietary."""
        return License.OTHER_PROPRIETARY in self.context.licenses

    @property
    def active_widget(self):
        return BooleanChoiceWidget(
            self.context, IProduct['active'],
            content_box_id='%s-edit-active' % FormattersAPI(
                self.context.name).css_id(),
            edit_view='+review-license',
            tag='span',
            false_text='Deactivated',
            true_text='Active',
            header='Is this project active and usable by the community?')

    @property
    def project_reviewed_widget(self):
        return BooleanChoiceWidget(
            self.context, IProduct['project_reviewed'],
            content_box_id='%s-edit-project-reviewed' % FormattersAPI(
                self.context.name).css_id(),
            edit_view='+review-license',
            tag='span',
            false_text='Unreviewed',
            true_text='Reviewed',
            header='Have you reviewed the project?')

    @property
    def license_approved_widget(self):
        licenses = list(self.context.licenses)
        if License.OTHER_PROPRIETARY in licenses:
            return 'Commercial subscription required'
        elif [License.DONT_KNOW] == licenses or [] == licenses:
            return 'Licence required'
        return BooleanChoiceWidget(
            self.context, IProduct['license_approved'],
            content_box_id='%s-edit-license-approved' % FormattersAPI(
                self.context.name).css_id(),
            edit_view='+review-license',
            tag='span',
            false_text='Unapproved',
            true_text='Approved',
            header='Does the licence qualifiy the project for free hosting?')


class ProductPurchaseSubscriptionView(ProductView):
    """View the instructions to purchase a commercial subscription."""
    page_title = 'Purchase subscription'


class ProductPackagesView(LaunchpadView):
    """View for displaying product packaging"""

    label = 'Linked packages'
    page_title = label

    @cachedproperty
    def series_batch(self):
        """A batch of series that are active or have packages."""
        decorated_series = DecoratedResultSet(
            self.context.active_or_packaged_series, DecoratedSeries)
        return BatchNavigator(decorated_series, self.request)

    @property
    def distro_packaging(self):
        """This method returns a representation of the product packagings
        for this product, in a special structure used for the
        product-distros.pt page template.

        Specifically, it is a list of "distro" objects, each of which has a
        title, and an attribute "packagings" which is a list of the relevant
        packagings for this distro and product.
        """
        distros = {}
        for packaging in self.context.packagings:
            distribution = packaging.distroseries.distribution
            if distribution.name in distros:
                distro = distros[distribution.name]
            else:
                # Create a dictionary for the distribution.
                distro = dict(
                    distribution=distribution,
                    packagings=[])
                distros[distribution.name] = distro
            distro['packagings'].append(packaging)
        # Now we sort the resulting list of "distro" objects, and return that.
        distro_names = distros.keys()
        distro_names.sort(cmp=_cmp_distros)
        results = [distros[name] for name in distro_names]
        return results


class ProductPackagesPortletView(LaunchpadView):
    """View class for product packaging portlet."""

    schema = Interface

    @cachedproperty
    def sourcepackages(self):
        """The project's latest source packages."""
        current_packages = [
            sp for sp in self.context.sourcepackages
            if sp.currentrelease is not None]
        current_packages.reverse()
        return current_packages[0:5]

    @cachedproperty
    def can_show_portlet(self):
        """Are there packages, or can packages be suggested."""
        if len(self.sourcepackages) > 0:
            return True


class SeriesReleasePair:
    """Class for holding a series and release.

    Replaces the use of a (series, release) tuple so that it can be more
    clearly addressed in the view class.
    """

    def __init__(self, series, release):
        self.series = series
        self.release = release


class ProductDownloadFilesView(LaunchpadView,
                               SortSeriesMixin,
                               ProductDownloadFileMixin):
    """View class for the product's file downloads page."""

    batch_size = config.launchpad.download_batch_size

    @property
    def page_title(self):
        return "%s project files" % self.context.displayname

    def initialize(self):
        """See `LaunchpadFormView`."""
        self.form = self.request.form
        # Manually process action for the 'Delete' button.
        self.processDeleteFiles()

    def getReleases(self):
        """See `ProductDownloadFileMixin`."""
        releases = set()
        for series in self.product.series:
            releases.update(series.releases)
        return releases

    @cachedproperty
    def series_and_releases_batch(self):
        """Get a batch of series and release

        Each entry returned is a tuple of (series, release).
        """
        series_and_releases = []
        for series in self.sorted_series_list:
            for release in series.releases:
                if len(release.files) > 0:
                    pair = SeriesReleasePair(series, release)
                    if pair not in series_and_releases:
                        series_and_releases.append(pair)
        batch = BatchNavigator(series_and_releases, self.request,
                               size=self.batch_size)
        batch.setHeadings("release", "releases")
        return batch

    @cachedproperty
    def has_download_files(self):
        """Across series and releases do any download files exist?"""
        for series in self.product.series:
            if series.has_release_files:
                return True
        return False

    @cachedproperty
    def any_download_files_with_signatures(self):
        """Do any series or release download files have signatures?"""
        for series in self.product.series:
            for release in series.releases:
                for file in release.files:
                    if file.signature:
                        return True
        return False

    @cachedproperty
    def milestones(self):
        """A mapping between series and releases that are milestones."""
        result = dict()
        for series in self.product.series:
            result[series.name] = set()
            milestone_list = [m.name for m in series.milestones]
            for release in series.releases:
                if release.version in milestone_list:
                    result[series.name].add(release.version)
        return result

    def is_milestone(self, series, release):
        """Determine whether a release is milestone for the series."""
        return (series.name in self.milestones and
                release.version in self.milestones[series.name])


class ProductBrandingView(BrandingChangeView):
    """A view to set branding."""
    implements(IProductEditMenu)

    label = "Change branding"
    schema = IProduct
    field_names = ['icon', 'logo', 'mugshot']

    @property
    def page_title(self):
        """The HTML page title."""
        return "Change %s's branding" % self.context.title

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)


class ProductConfigureBase(ReturnToReferrerMixin, LaunchpadEditFormView):
    implements(IProductEditMenu)
    schema = IProduct
    usage_fieldname = None

    def setUpFields(self):
        super(ProductConfigureBase, self).setUpFields()
        if self.usage_fieldname is not None:
            # The usage fields are shared among pillars.  But when referring
            # to an individual object in Launchpad it is better to call it by
            # its real name, i.e. 'project' instead of 'pillar'.
            usage_field = self.form_fields.get(self.usage_fieldname)
            if usage_field:
                usage_field.custom_widget = CustomWidgetFactory(
                    LaunchpadRadioWidget, orientation='vertical')
                # Copy the field or else the description in the interface will
                # be modified in-place.
                field = copy_field(usage_field.field)
                field.description = (
                    field.description.replace('pillar', 'project'))
                usage_field.field = field
                if (self.usage_fieldname in
                    ('answers_usage', 'translations_usage') and
                    self.context.information_type in
                    PROPRIETARY_INFORMATION_TYPES):
                    values = usage_field.field.vocabulary.items
                    terms = [SimpleTerm(value, value.name, value.title)
                             for value in values
                             if value != ServiceUsage.LAUNCHPAD]
                    usage_field.field.vocabulary = SimpleVocabulary(terms)

    @property
    def field_names(self):
        return [self.usage_fieldname]

    @property
    def page_title(self):
        return self.label

    @action("Change", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)


class ProductConfigureBlueprintsView(ProductConfigureBase):
    """View class to configure the Launchpad Blueprints for a project."""

    label = "Configure blueprints"
    usage_fieldname = 'blueprints_usage'


class ProductConfigureAnswersView(ProductConfigureBase):
    """View class to configure the Launchpad Answers for a project."""

    label = "Configure answers"
    usage_fieldname = 'answers_usage'


class ProductEditView(ProductLicenseMixin, LaunchpadEditFormView):
    """View class that lets you edit a Product object."""

    implements(IProductEditMenu)

    label = "Edit details"
    schema = IProduct
    field_names = [
        "displayname",
        "title",
        "summary",
        "description",
        "project",
        "homepageurl",
        "information_type",
        "sourceforgeproject",
        "freshmeatproject",
        "wikiurl",
        "screenshotsurl",
        "downloadurl",
        "programminglang",
        "development_focus",
        "licenses",
        "license_info",
        ]
    custom_widget('licenses', LicenseWidget)
    custom_widget('license_info', GhostWidget)
    custom_widget(
        'information_type', LaunchpadRadioWidgetWithDescription,
        vocabulary=InformationTypeVocabulary(
            types=PUBLIC_PROPRIETARY_INFORMATION_TYPES))

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        if self.context.active:
            if len(self.errors) > 0:
                return None
            return canonical_url(self.context)
        else:
            return canonical_url(getUtility(IProductSet))

    cancel_url = next_url

    @property
    def page_title(self):
        """The HTML page title."""
        return "Change %s's details" % self.context.title

    def initialize(self):
        # The JSON cache must be populated before the super call, since
        # the form is rendered during LaunchpadFormView's initialize()
        # when an action is invoked.
        cache = IJSONRequestCache(self.request)
        json_dump_information_types(
            cache, PUBLIC_PROPRIETARY_INFORMATION_TYPES)
        super(ProductEditView, self).initialize()

    def validate(self, data):
        """Validate 'licenses' and 'license_info'.

        'licenses' must not be empty unless the product already
        exists and never has had a licence set.

        'license_info' must not be empty if "Other/Proprietary"
        or "Other/Open Source" is checked.
        """
        super(ProductEditView, self).validate(data)
        information_type = data.get('information_type')
        if information_type:
            errors = [
                str(e) for e in self.context.checkInformationType(
                    information_type)]
            if len(errors) > 0:
                self.setFieldError('information_type', ' '.join(errors))

    def showOptionalMarker(self, field_name):
        """See `LaunchpadFormView`."""
        # This has the effect of suppressing the ": (Optional)" stuff for the
        # license_info widget.  It's the last piece of the puzzle for
        # manipulating the license_info widget into the table for the
        # LicenseWidget instead of the enclosing form.
        if field_name == 'license_info':
            return False
        return super(ProductEditView, self).showOptionalMarker(field_name)

    @action("Change", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)


class ProductValidationMixin:

    def validate_deactivation(self, data):
        """Verify whether a product can be safely deactivated."""
        if data['active'] == False and self.context.active == True:
            if len(self.context.sourcepackages) > 0:
                self.setFieldError('active',
                    structured(
                        'This project cannot be deactivated since it is '
                        'linked to one or more '
                        '<a href="%s">source packages</a>.',
                        canonical_url(self.context, view_name='+packages')))


class ProductAdminView(ProductEditView, ProductValidationMixin):
    """View for $project/+admin"""
    label = "Administer project details"
    default_field_names = [
        "name",
        "owner",
        "active",
        "autoupdate",
        ]

    @property
    def page_title(self):
        """The HTML page title."""
        return 'Administer %s' % self.context.title

    def setUpFields(self):
        """Setup the normal fields from the schema plus adds 'Registrant'.

        The registrant is normally a read-only field and thus does not have a
        proper widget created by default.  Even though it is read-only, admins
        need the ability to change it.
        """
        self.field_names = self.default_field_names[:]
        admin = check_permission('launchpad.Admin', self.context)
        if not admin:
            self.field_names.remove('owner')
            self.field_names.remove('autoupdate')
        super(ProductAdminView, self).setUpFields()
        self.form_fields = self._createAliasesField() + self.form_fields
        if admin:
            self.form_fields = (
                self.form_fields + self._createRegistrantField())

    def _createAliasesField(self):
        """Return a PillarAliases field for IProduct.aliases."""
        return form.Fields(
            PillarAliases(
                __name__='aliases', title=_('Aliases'),
                description=_('Other names (separated by space) under which '
                              'this project is known.'),
                required=False, readonly=False),
            render_context=self.render_context)

    def _createRegistrantField(self):
        """Return a popup widget person selector for the registrant.

        This custom field is necessary because *normally* the registrant is
        read-only but we want the admins to have the ability to correct legacy
        data that was set before the registrant field existed.
        """
        return form.Fields(
            PublicPersonChoice(
                __name__='registrant',
                title=_('Project Registrant'),
                description=_('The person who originally registered the '
                              'product.  Distinct from the current '
                              'owner.  This is historical data and should '
                              'not be changed without good cause.'),
                vocabulary='ValidPersonOrTeam',
                required=True,
                readonly=False,
                ),
            render_context=self.render_context
            )

    def validate(self, data):
        """See `LaunchpadFormView`."""
        super(ProductAdminView, self).validate(data)
        self.validate_deactivation(data)

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)


class ProductReviewLicenseView(ReturnToReferrerMixin, ProductEditView,
                               ProductValidationMixin):
    """A view to review a project and change project privileges."""
    label = "Review project"
    field_names = [
        "project_reviewed",
        "license_approved",
        "active",
        "reviewer_whiteboard",
        ]

    @property
    def page_title(self):
        """The HTML page title."""
        return 'Review %s' % self.context.title

    def validate(self, data):
        """See `LaunchpadFormView`."""

        super(ProductReviewLicenseView, self).validate(data)
        # A project can only be approved if it has OTHER_OPEN_SOURCE as one of
        # its licenses and not OTHER_PROPRIETARY.
        licenses = self.context.licenses
        license_approved = data.get('license_approved', False)
        if license_approved:
            if License.OTHER_PROPRIETARY in licenses:
                self.setFieldError(
                    'license_approved',
                    'Proprietary projects may not be manually '
                    'approved to use Launchpad.  Proprietary projects '
                    'must use the commercial subscription voucher system '
                    'to be allowed to use Launchpad.')
            else:
                # An Other/Open Source licence was specified so it may be
                # approved.
                pass

        self.validate_deactivation(data)


class ProductAddSeriesView(LaunchpadFormView):
    """A form to add new product series"""

    schema = IProductSeries
    field_names = ['name', 'summary', 'branch', 'releasefileglob']
    custom_widget('summary', TextAreaWidget, height=7, width=62)
    custom_widget('releasefileglob', StrippedTextWidget, displayWidth=40)

    series = None

    @property
    def label(self):
        """The form label."""
        return 'Register a new %s release series' % (
            self.context.displayname)

    @property
    def page_title(self):
        """The page title."""
        return self.label

    def validate(self, data):
        """See `LaunchpadFormView`."""
        branch = data.get('branch')
        if branch is not None:
            message = get_series_branch_error(self.context, branch)
            if message:
                self.setFieldError('branch', message)

    @action(_('Register Series'), name='add')
    def add_action(self, action, data):
        self.series = self.context.newSeries(
            owner=self.user,
            name=data['name'],
            summary=data['summary'],
            branch=data['branch'],
            releasefileglob=data['releasefileglob'])

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        assert self.series is not None, 'No series has been created'
        return canonical_url(self.series)

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)


class ProductSeriesSetView(ProductView):
    """A view for showing a product's series."""

    label = 'timeline'
    page_title = label

    @cachedproperty
    def batched_series(self):
        decorated_result = DecoratedResultSet(
            self.context.getVersionSortedSeries(), DecoratedSeries)
        return BatchNavigator(decorated_result, self.request)


class ProductRdfView(BaseRdfView):
    """A view that sets its mime-type to application/rdf+xml"""

    template = ViewPageTemplateFile(
        '../templates/product-rdf.pt')

    @property
    def filename(self):
        return '%s.rdf' % self.context.name


class Icon:
    """An icon for use with image:icon."""

    def __init__(self, library_id):
        self.library_alias = getUtility(ILibraryFileAliasSet)[library_id]

    def getURL(self):
        return self.library_alias.getURL()


class ProductSetNavigationMenu(RegistryCollectionActionMenuBase):
    """Action menu for products index."""
    usedfor = IProductSet
    links = [
        'register_team',
        'register_project',
        'create_account',
        'review_licenses',
        'view_all_projects',
        ]

    @enabled_with_permission('launchpad.Moderate')
    def review_licenses(self):
        return Link('+review-licenses', 'Review projects', icon='edit')

    def view_all_projects(self):
        return Link('+all', 'Show all projects', icon='list')


class ProductSetView(LaunchpadView):
    """View for products index page."""

    implements(IRegistryCollectionNavigationMenu)

    page_title = 'Projects registered in Launchpad'

    max_results_to_display = config.launchpad.default_batch_size
    results = None
    search_requested = False

    def initialize(self):
        """See `LaunchpadView`."""
        form = self.request.form_ng
        self.search_string = form.getOne('text')
        if self.search_string is not None:
            self.search_requested = True

    @cachedproperty
    def all_batched(self):
        return BatchNavigator(self.context.get_all_active(self.user),
                              self.request)

    @cachedproperty
    def matches(self):
        if not self.search_requested:
            return None
        pillarset = getUtility(IPillarNameSet)
        return pillarset.count_search_matches(self.search_string)

    @cachedproperty
    def search_results(self):
        search_string = self.search_string.lower()
        limit = self.max_results_to_display
        return getUtility(IPillarNameSet).search(search_string, limit)

    def tooManyResultsFound(self):
        return self.matches > self.max_results_to_display

    def latest(self):
        return self.context.get_all_active(self.user)[:5]


class ProductSetReviewLicensesView(LaunchpadFormView):
    """View for searching products to be reviewed."""

    schema = IProductReviewSearch
    label = 'Review projects'
    page_title = label

    full_row_field_names = [
        'search_text',
        'active',
        'project_reviewed',
        'license_approved',
        'licenses',
        'has_subscription',
        ]

    side_by_side_field_names = [
        ('created_after', 'created_before'),
        ('subscription_expires_after', 'subscription_expires_before'),
        ('subscription_modified_after', 'subscription_modified_before'),
        ]

    custom_widget(
        'licenses', CheckBoxMatrixWidget, column_count=4,
        orientation='vertical')
    custom_widget('active', LaunchpadRadioWidget,
                  _messageNoValue="(do not filter)")
    custom_widget('project_reviewed', LaunchpadRadioWidget,
                  _messageNoValue="(do not filter)")
    custom_widget('license_approved', LaunchpadRadioWidget,
                  _messageNoValue="(do not filter)")
    custom_widget('has_subscription', LaunchpadRadioWidget,
                  _messageNoValue="(do not filter)")
    custom_widget('created_after', DateWidget)
    custom_widget('created_before', DateWidget)
    custom_widget('subscription_expires_after', DateWidget)
    custom_widget('subscription_expires_before', DateWidget)
    custom_widget('subscription_modified_after', DateWidget)
    custom_widget('subscription_modified_before', DateWidget)

    @property
    def left_side_widgets(self):
        """Return the widgets for the left column."""
        return (self.widgets.get(left)
                for left, right in self.side_by_side_field_names)

    @property
    def right_side_widgets(self):
        """Return the widgets for the right column."""
        return (self.widgets.get(right)
                for left, right in self.side_by_side_field_names)

    @property
    def full_row_widgets(self):
        """Return all widgets that span all columns."""
        return (self.widgets[name] for name in self.full_row_field_names)

    @property
    def initial_values(self):
        """See `ILaunchpadFormView`."""
        search_params = {}
        for name in self.schema:
            search_params[name] = self.schema[name].default
        return search_params

    def forReviewBatched(self):
        """Return a `BatchNavigator` to review the matching projects."""
        # Calling _validate populates the data dictionary as a side-effect
        # of validation.
        data = {}
        self._validate(None, data)
        search_params = self.initial_values
        # Override the defaults with the form values if available.
        search_params.update(data)
        result = self.context.forReview(self.user, **search_params)
        return BatchNavigator(result, self.request, size=50)


class ProductAddViewBase(ProductLicenseMixin, LaunchpadFormView):
    """Abstract class for adding a new product.

    ProductLicenseMixin requires the "product" attribute be set in the
    child classes' action handler.
    """

    schema = IProduct
    product = None
    field_names = ['name', 'displayname', 'title', 'summary',
                   'description', 'homepageurl', 'sourceforgeproject',
                   'freshmeatproject', 'wikiurl', 'screenshotsurl',
                   'downloadurl', 'programminglang',
                   'licenses', 'license_info']
    custom_widget(
        'licenses', LicenseWidget, column_count=3, orientation='vertical')
    custom_widget('homepageurl', TextWidget, displayWidth=30)
    custom_widget('screenshotsurl', TextWidget, displayWidth=30)
    custom_widget('wikiurl', TextWidget, displayWidth=30)
    custom_widget('downloadurl', TextWidget, displayWidth=30)

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        assert self.product is not None, 'No product has been created'
        return canonical_url(self.product)


def create_source_package_fields():
    return form.Fields(
        Choice(__name__='source_package_name',
               vocabulary='SourcePackageName',
               required=False),
        Choice(__name__='distroseries',
               vocabulary='DistroSeries',
               required=False),
        )


class ProjectAddStepOne(StepView):
    """product/+new view class for creating a new project."""

    _field_names = ['displayname', 'name', 'title', 'summary']
    label = "Register a project in Launchpad"
    schema = IProduct
    step_name = 'projectaddstep1'
    template = ViewPageTemplateFile('../templates/product-new.pt')
    page_title = "Register a project in Launchpad"

    custom_widget('displayname', TextWidget, displayWidth=50, label='Name')
    custom_widget('name', ProductNameWidget, label='URL')

    step_description = 'Project basics'
    search_results_count = 0

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(ProjectAddStepOne, self).setUpFields()
        self.form_fields = (self.form_fields + create_source_package_fields())

    def setUpWidgets(self):
        """See `LaunchpadFormView`."""
        super(ProjectAddStepOne, self).setUpWidgets()
        self.widgets['source_package_name'].visible = False
        self.widgets['distroseries'].visible = False

    @property
    def _return_url(self):
        """This view is using the hidden _return_url field.

        It is not using the `ReturnToReferrerMixin`, since none
        of its other code is used, because multistep views can't
        have next_url set until the form submission succeeds.
        """
        return self.request.form.get('_return_url')

    @property
    def _next_step(self):
        """Define the next step.

        Subclasses can override this method to avoid having to override the
        more complicated `main_action` method for customization.  The actual
        property `next_step` must not be set before `main_action` is called.
        """
        return ProjectAddStepTwo

    def main_action(self, data):
        """See `MultiStepView`."""
        self.next_step = self._next_step

    # Make this a safe_action, so that the sourcepackage page can skip
    # the first step with a link (GET request) providing form values.
    continue_action = safe_action(StepView.continue_action)


class ProjectAddStepTwo(StepView, ProductLicenseMixin, ReturnToReferrerMixin):
    """Step 2 (of 2) in the +new project add wizard."""

    _field_names = ['displayname', 'name', 'title', 'summary', 'description',
                    'homepageurl', 'information_type', 'licenses',
                    'license_info', 'driver', 'bug_supervisor', 'owner']
    schema = IProduct
    step_name = 'projectaddstep2'
    template = ViewPageTemplateFile('../templates/product-new.pt')
    page_title = ProjectAddStepOne.page_title

    product = None

    custom_widget('displayname', TextWidget, displayWidth=50, label='Name')
    custom_widget('name', ProductNameWidget, label='URL')
    custom_widget('homepageurl', TextWidget, displayWidth=30)
    custom_widget('licenses', LicenseWidget)
    custom_widget('license_info', GhostWidget)
    custom_widget(
        'information_type',
        LaunchpadRadioWidgetWithDescription,
        vocabulary=InformationTypeVocabulary(
            types=PUBLIC_PROPRIETARY_INFORMATION_TYPES))

    custom_widget(
        'owner', PersonPickerWidget, header="Select the maintainer",
        show_create_team_link=True)
    custom_widget(
        'bug_supervisor', PersonPickerWidget, header="Set a bug supervisor",
        required=True, show_create_team_link=True)
    custom_widget(
        'driver', PersonPickerWidget, header="Set a driver",
        required=True, show_create_team_link=True)
    custom_widget(
        'disclaim_maintainer', CheckBoxWidget, cssClass="subordinate")

    def initialize(self):
        # The JSON cache must be populated before the super call, since
        # the form is rendered during LaunchpadFormView's initialize()
        # when an action is invoked.
        cache = IJSONRequestCache(self.request)
        json_dump_information_types(
            cache, PUBLIC_PROPRIETARY_INFORMATION_TYPES)
        super(ProjectAddStepTwo, self).initialize()

    @property
    def main_action_label(self):
        if self.source_package_name is None:
            return u'Complete Registration'
        else:
            return u'Complete registration and link to %s package' % (
                self.source_package_name.name)

    @property
    def _return_url(self):
        """This view is using the hidden _return_url field.

        It is not using the `ReturnToReferrerMixin`, since none
        of its other code is used, because multistep views can't
        have next_url set until the form submission succeeds.
        """
        return self.request.form.get('_return_url')

    @property
    def step_description(self):
        """See `MultiStepView`."""
        if self.search_results_count > 0:
            return 'Check for duplicate projects'
        return 'Registration details'

    @property
    def initial_values(self):
        return {
            'driver': self.user.name,
            'bug_supervisor': self.user.name,
            'owner': self.user.name,
            'information_type': InformationType.PUBLIC,
        }

    @property
    def enable_information_type(self):
        return not self.source_package_name

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(ProjectAddStepTwo, self).setUpFields()
        hidden_names = ['__visited_steps__', 'license_info']
        hidden_fields = self.form_fields.select(*hidden_names)

        if not self.enable_information_type:
            hidden_names.extend(
                ['information_type', 'bug_supervisor', 'driver'])

        visible_fields = self.form_fields.omit(*hidden_names)
        self.form_fields = (
            visible_fields + self._createDisclaimMaintainerField() +
            create_source_package_fields() + hidden_fields)

    def _createDisclaimMaintainerField(self):
        """Return a Bool field for disclaiming maintainer.

        If the registrant does not want to maintain the project she can select
        this checkbox and the ownership will be transfered to the registry
        admins team.
        """
        return form.Fields(
            Bool(__name__='disclaim_maintainer',
                 title=_("I do not want to maintain this project"),
                 description=_(
                     "Select if you are registering this project "
                     "for the purpose of taking an action (such as "
                     "reporting a bug) but you don't want to actually "
                     "maintain the project in Launchpad.  "
                     "The Registry Administrators team will become "
                     "the maintainers until a community maintainer "
                     "can be found.")),
            render_context=self.render_context)

    def setUpWidgets(self):
        """See `LaunchpadFormView`."""
        super(ProjectAddStepTwo, self).setUpWidgets()
        self.widgets['name'].read_only = True
        # The "hint" is really more of an explanation at this point, but the
        # phrasing is different.
        self.widgets['name'].hint = (
            "When published, this will be the project's URL.")
        self.widgets['displayname'].visible = False
        self.widgets['source_package_name'].visible = False
        self.widgets['distroseries'].visible = False

        if (self.enable_information_type and
            IProductSet.providedBy(self.context)):
            self.widgets['information_type'].value = InformationType.PUBLIC

        # Set the source_package_release attribute on the licenses
        # widget, so that the source package's copyright info can be
        # displayed.
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        if self.source_package_name is not None:
            release_list = ubuntu.getCurrentSourceReleases(
                [self.source_package_name])
            if len(release_list) != 0:
                self.widgets['licenses'].source_package_release = (
                    release_list.items()[0][1])

    @property
    def source_package_name(self):
        # setUpWidgets() doesn't have access to the data dictionary,
        # so the source package name needs to be converted from a string
        # into an object here.
        package_name_string = self.request.form.get(
            'field.source_package_name')
        if package_name_string is None:
            return None
        else:
            return getUtility(ISourcePackageNameSet).queryByName(
                package_name_string)

    @cachedproperty
    def _search_string(self):
        """Return the ORed terms to match."""
        search_text = SPACE.join((self.request.form['field.name'],
                                  self.request.form['field.displayname'],
                                  self.request.form['field.summary']))
        # OR all the terms together.
        return OR.join(search_text.split())

    @cachedproperty
    def search_results(self):
        """The full text search results.

        Search the pillars for any match on the name, display name, or
        summary.
        """
        # XXX BarryWarsaw 16-Apr-2009 do we need batching and should we return
        # more than 7 hits?
        return getUtility(IPillarNameSet).search(self._search_string, 7)

    @cachedproperty
    def search_results_count(self):
        """Return the count of matching `IPillar`s."""
        return getUtility(IPillarNameSet).count_search_matches(
            self._search_string)

    # StepView requires that its validate() method not be overridden, so make
    # sure this calls the right method.  validateStep() will call the licence
    # validation code.
    def validate(self, data):
        """See `MultiStepView`."""
        StepView.validate(self, data)

    def validateStep(self, data):
        """See `MultiStepView`."""
        ProductLicenseMixin.validate(self, data)
        if data.get('disclaim_maintainer') and self.errors:
            # The checkbox supersedes the owner text input.
            errors = [error for error in self.errors if error[0] == 'owner']
            for error in errors:
                self.errors.remove(error)

        if self.enable_information_type:
            if data.get('information_type') != InformationType.PUBLIC:
                for required_field in ('bug_supervisor', 'driver'):
                    if data.get(required_field) is None:
                        self.setFieldError(
                            required_field, 'Select a user or team.')

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Register %s (%s) in Launchpad' % (
                self.request.form['field.displayname'],
                self.request.form['field.name'])

    def create_product(self, data):
        """Create the product from the user data."""
        # Get optional data.
        project = data.get('project')
        description = data.get('description')
        disclaim_maintainer = data.get('disclaim_maintainer', False)
        if disclaim_maintainer:
            owner = getUtility(ILaunchpadCelebrities).registry_experts
        else:
            owner = data.get('owner')

        return getUtility(IProductSet).createProduct(
            registrant=self.user,
            bug_supervisor=data.get('bug_supervisor', None),
            driver=data.get('driver', None),
            owner=owner,
            name=data['name'],
            displayname=data['displayname'],
            title=data['title'],
            summary=data['summary'],
            description=description,
            homepageurl=data.get('homepageurl'),
            licenses=data['licenses'],
            license_info=data['license_info'],
            information_type=data.get('information_type'),
            project=project)

    def link_source_package(self, product, data):
        if (data.get('distroseries') is not None
            and self.source_package_name is not None):
            source_package = data['distroseries'].getSourcePackage(
                self.source_package_name)
            source_package.setPackaging(
                product.development_focus, self.user)
            self.request.response.addInfoNotification(
                'Linked %s project to %s source package.' % (
                    product.displayname, self.source_package_name.name))

    def main_action(self, data):
        """See `MultiStepView`."""
        self.product = self.create_product(data)
        notify(ObjectCreatedEvent(self.product))
        self.link_source_package(self.product, data)

        if self._return_url is None:
            self.next_url = canonical_url(self.product)
        else:
            self.next_url = self._return_url


class ProductAddView(PillarViewMixin, MultiStepView):
    """The controlling view for product/+new."""

    page_title = ProjectAddStepOne.page_title
    total_steps = 2

    @property
    def first_step(self):
        """See `MultiStepView`."""
        return ProjectAddStepOne


class IProductEditPeopleSchema(Interface):
    """Defines the fields for the edit form.

    Specifically adds a new checkbox for transferring the maintainer role to
    Registry Administrators and makes the owner optional.
    """
    owner = copy_field(IProduct['owner'])
    owner.required = False

    driver = copy_field(IProduct['driver'])

    transfer_to_registry = Bool(
        title=_("I do not want to maintain this project"),
        required=False,
        description=_(
            "Select this if you no longer want to maintain this project in "
            "Launchpad.  Launchpad's Registry Administrators team will "
            "become the project's new maintainers."))


class ProductEditPeopleView(LaunchpadEditFormView):
    """Enable editing of important people on the project."""

    implements(IProductEditMenu)

    label = "Change the roles of people"
    schema = IProductEditPeopleSchema
    field_names = [
        'owner',
        'transfer_to_registry',
        'driver',
        ]

    for_input = True

    # Initial value must be provided for the 'transfer_to_registry' field to
    # avoid having the non-existent attribute queried on the context and
    # failing.
    initial_values = {'transfer_to_registry': False}

    custom_widget('owner', PersonPickerWidget, header="Select the maintainer",
                  show_create_team_link=True)
    custom_widget('transfer_to_registry', CheckBoxWidget,
                  widget_class='field subordinate')
    custom_widget('driver', PersonPickerWidget, header="Select the driver",
                  show_create_team_link=True)

    @property
    def page_title(self):
        """The HTML page title."""
        return "Change the roles of %s's people" % self.context.title

    def validate(self, data):
        """Validate owner and transfer_to_registry are consistent.

        At most one may be specified.
        """
        xfer = data.get('transfer_to_registry', False)
        owner = data.get('owner')
        error = None
        if xfer:
            if owner:
                error = (
                    'You may not specify a new owner if you select the '
                    'checkbox.')
            else:
                celebrities = getUtility(ILaunchpadCelebrities)
                data['owner'] = celebrities.registry_experts
        else:
            if not owner:
                if self.errors and isinstance(
                    self.errors[0], WidgetInputError):
                    del self.errors[0]
                    error = (
                        'You must choose a valid person or team to be the '
                        'owner for %s.' % self.context.displayname)
                else:
                    error = (
                        'You must specify a maintainer or select the '
                        'checkbox.')
        if error:
            self.setFieldError('owner', error)

    @action(_('Save changes'), name='save')
    def save_action(self, action, data):
        """Save the changes to the associated people."""
        # Since 'transfer_to_registry' is not a real attribute on a Product,
        # it must be removed from data before the context is updated.
        if 'transfer_to_registry' in data:
            del data['transfer_to_registry']
        self.updateContextFromData(data)

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @property
    def adapters(self):
        """See `LaunchpadFormView`"""
        return {IProductEditPeopleSchema: self.context}
