# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for archive."""

__metaclass__ = type

__all__ = [
    'ArchiveAdminView',
    'ArchiveActivateView',
    'ArchiveBadges',
    'ArchiveBuildsView',
    'ArchiveDeleteView',
    'ArchiveEditDependenciesView',
    'ArchiveEditView',
    'ArchiveIndexActionsMenu',
    'ArchiveNavigation',
    'ArchiveNavigationMenu',
    'ArchivePackageCopyingView',
    'ArchivePackageDeletionView',
    'ArchivePackagesActionMenu',
    'ArchivePackagesView',
    'ArchiveView',
    'ArchiveViewBase',
    'EnableRestrictedProcessorsMixin',
    'make_archive_vocabulary',
    'PackageCopyingMixin',
    'traverse_named_ppa',
    ]


from datetime import (
    datetime,
    timedelta,
    )

from lazr.restful.utils import smartquote
import pytz
from sqlobject import SQLObjectNotFound
from storm.expr import Desc
from zope.component import getUtility
from zope.formlib import form
from zope.formlib.widgets import TextAreaWidget
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    List,
    TextLine,
    )
from zope.schema.interfaces import IContextSourceBinder
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.proxy import removeSecurityProxy

from lp import _
from lp.app.browser.badge import HasBadgeBase
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.browser.lazrjs import (
    TextAreaEditorWidget,
    TextLineEditorWidget,
    )
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.widgets.itemswidgets import (
    LabeledMultiCheckBoxWidget,
    LaunchpadDropdownWidget,
    LaunchpadRadioWidget,
    PlainMultiCheckBoxWidget,
    )
from lp.app.widgets.textwidgets import StrippedTextWidget
from lp.buildmaster.enums import BuildStatus
from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.model.person import Person
from lp.services.browser_helpers import (
    get_plural_text,
    get_user_agent_distroseries,
    )
from lp.services.database.bulk import load_related
from lp.services.helpers import english_list
from lp.services.job.model.job import Job
from lp.services.librarian.browser import FileNavigationMixin
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    stepthrough,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    IStructuredString,
    )
from lp.services.webapp.menu import NavigationMenu
from lp.services.worlddata.interfaces.country import ICountrySet
from lp.soyuz.adapters.archivedependencies import (
    default_component_dependency_name,
    default_pocket_dependency,
    )
from lp.soyuz.adapters.archivesourcepublication import (
    ArchiveSourcePublications,
    )
from lp.soyuz.browser.build import (
    BuildNavigationMixin,
    BuildRecordsView,
    )
from lp.soyuz.browser.sourceslist import SourcesListEntriesWidget
from lp.soyuz.browser.widgets.archive import PPANameWidget
from lp.soyuz.enums import (
    ArchivePermissionType,
    ArchiveStatus,
    PackageCopyPolicy,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.archive import (
    ArchiveDependencyError,
    CannotCopy,
    IArchive,
    IArchiveEditDependenciesForm,
    IArchiveSet,
    NoSuchPPA,
    validate_external_dependencies,
    )
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.archivesubscriber import IArchiveSubscriberSet
from lp.soyuz.interfaces.binarypackagebuild import BuildSetStatus
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageNameSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.soyuz.interfaces.packagecopyrequest import IPackageCopyRequestSet
from lp.soyuz.interfaces.packageset import IPackagesetSet
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.interfaces.publishing import (
    active_publishing_status,
    inactive_publishing_status,
    IPublishingSet,
    )
from lp.soyuz.model.archive import (
    Archive,
    validate_ppa,
    )
from lp.soyuz.model.publishing import SourcePackagePublishingHistory
from lp.soyuz.scripts.packagecopier import check_copy_permissions


class ArchiveBadges(HasBadgeBase):
    """Provides `IHasBadges` for `IArchive`."""

    def getPrivateBadgeTitle(self):
        """Return private badge info useful for a tooltip."""
        return "This archive is private."


def traverse_named_ppa(person_name, ppa_name):
    """For PPAs, traverse the right place.

    :param person_name: The person part of the URL
    :param ppa_name: The PPA name part of the URL
    """
    person = getUtility(IPersonSet).getByName(person_name)
    try:
        archive = person.getPPAByName(ppa_name)
    except NoSuchPPA:
        raise NotFoundError("%s/%s", (person_name, ppa_name))

    return archive


class DistributionArchiveURL:
    """Dynamic URL declaration for `IDistributionArchive`.

    When dealing with distribution archives we want to present them under
    IDistribution as /<distro>/+archive/<name>, for example:
    /ubuntu/+archive/partner
    """
    implements(ICanonicalUrlData)
    rootsite = None

    def __init__(self, context):
        self.context = context

    @property
    def inside(self):
        return self.context.distribution

    @property
    def path(self):
        return u"+archive/%s" % self.context.name


class PPAURL:
    """Dynamic URL declaration for named PPAs."""
    implements(ICanonicalUrlData)
    rootsite = None

    def __init__(self, context):
        self.context = context

    @property
    def inside(self):
        return self.context.owner

    @property
    def path(self):
        return u"+archive/%s" % self.context.name


class ArchiveNavigation(Navigation, FileNavigationMixin,
                        BuildNavigationMixin):
    """Navigation methods for IArchive."""

    usedfor = IArchive

    @stepthrough('+sourcepub')
    def traverse_sourcepub(self, name):
        return self._traverse_publication(name, source=True)

    @stepthrough('+binarypub')
    def traverse_binarypub(self, name):
        return self._traverse_publication(name, source=False)

    def _traverse_publication(self, name, source):
        try:
            pub_id = int(name)
        except ValueError:
            return None

        # The ID is not enough on its own to identify the publication,
        # we need to make sure it matches the context archive as well.
        return getUtility(IPublishingSet).getByIdAndArchive(
            pub_id, self.context, source)

    @stepthrough('+binaryhits')
    def traverse_binaryhits(self, name_str):
        """Traverse to an `IBinaryPackageReleaseDownloadCount`.

        A matching path is something like this:

          +binaryhits/foopkg/1.0/i386/2010-03-11/AU

        To reach one where the country is None, use:

          +binaryhits/foopkg/1.0/i386/2010-03-11/unknown
        """

        if len(self.request.stepstogo) < 4:
            return None

        version = self.request.stepstogo.consume()
        archtag = self.request.stepstogo.consume()
        date_str = self.request.stepstogo.consume()
        country_str = self.request.stepstogo.consume()

        try:
            name = getUtility(IBinaryPackageNameSet)[name_str]
        except NotFoundError:
            return None

        # This will return None if there are multiple BPRs with the same
        # name in the archive's history, but in that case downloads
        # won't be counted either.
        bpr = self.context.getBinaryPackageRelease(name, version, archtag)
        if bpr is None:
            return None

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return None

        # 'unknown' should always be safe, since the key is the two letter
        # ISO code, and 'unknown' has more than two letters.
        if country_str == 'unknown':
            country = None
        else:
            try:
                country = getUtility(ICountrySet)[country_str]
            except NotFoundError:
                return None

        return self.context.getPackageDownloadCount(bpr, date, country)

    @stepthrough('+subscriptions')
    def traverse_subscription(self, person_name):
        person = getUtility(IPersonSet).getByName(person_name)
        if person is None:
            return None

        subscriptions = getUtility(IArchiveSubscriberSet).getBySubscriber(
            person, archive=self.context)

        # If a person is subscribed with a direct subscription as well as
        # via a team, subscriptions will contain both, so need to grab
        # the direct subscription:
        for subscription in subscriptions:
            if subscription.subscriber == person:
                return subscription

        return None

    @stepthrough('+upload')
    def traverse_upload_permission(self, name):
        """Traverse the data part of the URL for upload permissions."""
        return self._traverse_permission(name, ArchivePermissionType.UPLOAD)

    @stepthrough('+queue-admin')
    def traverse_queue_admin_permission(self, name):
        """Traverse the data part of the URL for queue admin permissions."""
        return self._traverse_permission(
            name, ArchivePermissionType.QUEUE_ADMIN)

    def _traverse_permission(self, name, permission_type):
        """Traversal helper function.

        The data part ("name") is a compound value of the format:
        user.item
        where item is a component or a source package name,
        """

        def get_url_param(param_name):
            """Return the URL parameter with the given name or None."""
            param_seq = self.request.query_string_params.get(param_name)
            if param_seq is None or len(param_seq) == 0:
                return None
            else:
                # Return whatever value was specified last in the URL.
                return param_seq.pop()

        # Look up the principal first.
        user = getUtility(IPersonSet).getByName(name)
        if user is None:
            return None

        # Obtain the item type and name from the URL parameters.
        item_type = get_url_param('type')
        item = get_url_param('item')

        if item_type is None or item is None:
            return None

        the_item = None
        kwargs = {}
        if item_type == 'component':
            # See if "item" is a component name.
            try:
                the_item = getUtility(IComponentSet)[item]
            except NotFoundError:
                pass
        elif item_type == 'packagename':
            # See if "item" is a source package name.
            the_item = getUtility(ISourcePackageNameSet).queryByName(item)
        elif item_type == 'packageset':
            the_item = None
            # Was a 'series' URL param passed?
            series = get_url_param('series')
            if series is not None:
                # Get the requested distro series.
                try:
                    series = self.context.distribution[series]
                except NotFoundError:
                    series = None
            if series is not None:
                the_item = getUtility(IPackagesetSet).getByName(
                    item, distroseries=series)
        elif item_type == 'pocket':
            # See if "item" is a pocket name.
            try:
                the_item = PackagePublishingPocket.items[item]
                # Was a 'series' URL param passed?
                series = get_url_param('series')
                if series is not None:
                    # Get the requested distro series.
                    try:
                        series = self.context.distribution[series]
                        kwargs["distroseries"] = series
                    except NotFoundError:
                        pass
            except KeyError:
                pass
        else:
            the_item = None

        if the_item is not None:
            result_set = getUtility(IArchivePermissionSet).checkAuthenticated(
                user, self.context, permission_type, the_item, **kwargs)
            try:
                return result_set[0]
            except IndexError:
                return None
        else:
            return None

    @stepthrough('+dependency')
    def traverse_dependency(self, id):
        """Traverse to an archive dependency by archive ID.

        We use IArchive.getArchiveDependency here, which is protected by
        launchpad.View, so you cannot get to a dependency of a private
        archive that you can't see.
        """
        try:
            id = int(id)
        except ValueError:
            # Not a number.
            return None

        try:
            archive = getUtility(IArchiveSet).get(id)
        except SQLObjectNotFound:
            return None

        return self.context.getArchiveDependency(archive)


class ArchiveMenuMixin:

    def ppa(self):
        text = 'View PPA'
        return Link(canonical_url(self.context), text, icon='info')

    @enabled_with_permission('launchpad.Admin')
    def admin(self):
        text = 'Administer archive'
        return Link('+admin', text, icon='edit')

    @enabled_with_permission('launchpad.Append')
    def manage_subscribers(self):
        text = 'Manage access'
        link = Link('+subscriptions', text, icon='edit')

        # This link should only be available for private archives:
        view = self.context
        archive = view.context
        if not archive.private or not archive.is_active:
            link.enabled = False
        return link

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change details'
        view = self.context
        return Link(
            '+edit', text, icon='edit', enabled=view.context.is_active)

    @enabled_with_permission('launchpad.Edit')
    def delete_ppa(self):
        text = 'Delete PPA'
        view = self.context
        return Link(
            '+delete', text, icon='trash-icon',
            enabled=view.context.is_active)

    def builds(self):
        text = 'View all builds'
        return Link('+builds', text, icon='info')

    def builds_successful(self):
        text = 'View successful builds'
        return Link('+builds?build_state=built', text, icon='info')

    def builds_pending(self):
        text = 'View pending builds'
        return Link('+builds?build_state=pending', text, icon='info')

    def builds_building(self):
        text = 'View in-progress builds'
        return Link('+builds?build_state=building', text, icon='info')

    def packages(self):
        text = 'View package details'
        link = Link('+packages', text, icon='info')
        # Disable the link for P3As if they don't have upload rights,
        # except if the user is a commercial admin.
        if self.context.private:
            if not check_permission('launchpad.Append', self.context):
                admins = getUtility(ILaunchpadCelebrities).commercial_admin
                if not self.user.inTeam(admins):
                    link.enabled = False
        return link

    @enabled_with_permission('launchpad.Edit')
    def delete(self):
        """Display a delete menu option for non-copy archives."""
        text = 'Delete packages'
        link = Link('+delete-packages', text, icon='trash-icon')

        # This link should not be available for copy archives or
        # archives without any sources.
        if self.context.is_copy or not self.context.has_sources:
            link.enabled = False
        view = self.context
        if not view.context.is_active:
            link.enabled = False
        return link

    @enabled_with_permission('launchpad.AnyPerson')
    def copy(self):
        """Display a copy menu option for non-copy archives."""
        text = 'Copy packages'
        link = Link('+copy-packages', text, icon='package-sync')

        # This link should not be available for copy archives.
        if self.context.is_copy:
            link.enabled = False
        return link

    @enabled_with_permission('launchpad.Edit')
    def edit_dependencies(self):
        text = 'Edit PPA dependencies'
        view = self.context
        return Link(
            '+edit-dependencies', text, icon='edit',
            enabled=view.context.is_active)


class ArchiveNavigationMenu(NavigationMenu, ArchiveMenuMixin):
    """Overview Menu for IArchive."""

    usedfor = IArchive
    facet = 'overview'
    links = ['admin', 'builds', 'builds_building',
             'builds_pending', 'builds_successful',
             'packages', 'ppa']


class IArchiveIndexActionsMenu(Interface):
    """A marker interface for the ppa index actions menu."""


class ArchiveIndexActionsMenu(NavigationMenu, ArchiveMenuMixin):
    """Archive index navigation menu."""
    usedfor = IArchiveIndexActionsMenu
    facet = 'overview'
    links = ['admin', 'edit', 'edit_dependencies',
             'manage_subscribers', 'packages', 'delete_ppa']


class IArchivePackagesActionMenu(Interface):
    """A marker interface for the packages action menu."""


class ArchivePackagesActionMenu(NavigationMenu, ArchiveMenuMixin):
    """An action menu for archive package-related actions."""
    usedfor = IArchivePackagesActionMenu
    facet = 'overview'
    links = ['copy', 'delete']


class ArchiveViewBase(LaunchpadView, SourcesListEntriesWidget):
    """Common features for Archive view classes."""

    def initialize(self):
        # If the archive has publishing disabled, present a warning.  If
        # the current user has lp.Edit then add a link to +edit to fix
        # this.
        if not self.context.publish and self.context.is_active:
            can_edit = check_permission('launchpad.Edit', self.context)
            notification = "Publishing has been disabled for this archive."
            if can_edit:
                edit_url = canonical_url(self.context) + '/+edit'
                notification += (
                    " <a href=%s>(re-enable publishing)</a>" % edit_url)
            if self.context.private:
                notification += (
                    " Since this archive is private, no builds are "
                    "being dispatched.")
            self.request.response.addNotification(structured(notification))
        super(ArchiveViewBase, self).initialize()
        # Set properties for SourcesListEntriesWidget.
        self.archive = self.context
        self.sources_list_user = self.user

    @cachedproperty
    def private(self):
        return self.context.private

    @cachedproperty
    def repository_usage(self):
        """Return a dictionary with usage details of this repository."""

        def package_plural(control):
            if control == 1:
                return 'package'
            return 'packages'

        # Calculate the label for the package counters respecting
        # singular/plural forms.
        number_of_sources = self.context.number_of_sources
        source_label = '%s source %s' % (
            number_of_sources, package_plural(number_of_sources))

        number_of_binaries = self.context.number_of_binaries
        binary_label = '%s binary %s' % (
            number_of_binaries, package_plural(number_of_binaries))

        used = self.context.estimated_size
        if self.context.authorized_size:
            # Quota is stored in MiB, convert it to bytes.
            quota = self.context.authorized_size * (2 ** 20)
            # Calculate the usage factor and limit it to 100%.
            used_factor = (float(used) / quota)
            if used_factor > 1:
                used_factor = 1
        else:
            quota = 0
            used_factor = 0

        # Calculate the appropriate CSS class to be used with the usage
        # factor. Highlight it (in red) if usage is over 90% of the quota.
        if used_factor > 0.90:
            used_css_class = 'red'
        else:
            used_css_class = 'green'

        # Usage percentage with 2 degrees of precision (more than enough
        # for humans).
        used_percentage = "%0.2f" % (used_factor * 100)

        return dict(
            source_label=source_label,
            sources_size=self.context.sources_size,
            binary_label=binary_label,
            binaries_size=self.context.binaries_size,
            used=used,
            used_percentage=used_percentage,
            used_css_class=used_css_class,
            quota=quota)

    @property
    def archive_label(self):
        """Return either 'PPA' or 'Archive' as the label for archives.

        It is desired to use the name 'PPA' for branding reasons where
        appropriate, even though the template logic is the same (and hence
        not worth splitting off into a separate template or macro)
        """
        if self.context.is_ppa:
            return 'PPA'
        else:
            return 'archive'

    @cachedproperty
    def build_counters(self):
        """Return a dict representation of the build counters."""
        return self.context.getBuildCounters()

    @cachedproperty
    def dependencies(self):
        return list(self.context.dependencies)

    @property
    def show_dependencies(self):
        """Whether or not to present the archive-dependencies section.

        The dependencies section is presented if there are any dependency set
        or if the user has permission to change it.
        """
        can_edit = check_permission('launchpad.Edit', self.context)
        return can_edit or len(self.dependencies) > 0

    @property
    def has_disabled_dependencies(self):
        """Whether this archive has disabled archive dependencies or not.

        Although, it will be True only if the requester has permission
        to edit the context archive (i.e. if the user can do something
        about it).
        """
        disabled_dependencies = [
            archive_dependency
            for archive_dependency in self.dependencies
            if not archive_dependency.dependency.enabled]
        can_edit = check_permission('launchpad.Edit', self.context)
        return can_edit and len(disabled_dependencies) > 0

    @cachedproperty
    def package_copy_requests(self):
        """Return any package copy requests associated with this archive."""
        copy_requests = getUtility(
            IPackageCopyRequestSet).getByTargetArchive(self.context)
        return list(copy_requests)

    @property
    def disabled_warning_message(self):
        """Return an appropriate message if the archive is disabled."""
        if self.context.enabled:
            return None

        if self.context.status in (
            ArchiveStatus.DELETED, ArchiveStatus.DELETING):
            return "This %s has been deleted." % self.archive_label
        else:
            return "This %s has been disabled." % self.archive_label


class ArchiveSeriesVocabularyFactory:
    """A factory for generating vocabularies of an archive's series."""

    implements(IContextSourceBinder)

    def __call__(self, context):
        """Return a vocabulary created dynamically from the context archive.

        :param context: The context used to generate the vocabulary. This
            is passed automatically by the zope machinery. Therefore
            this factory can only be used in a class where the context is
            an IArchive.
        """
        series_terms = []
        for distroseries in context.series_with_sources:
            series_terms.append(
                SimpleTerm(distroseries, token=distroseries.name,
                           title=distroseries.displayname))
        return SimpleVocabulary(series_terms)


class SeriesFilterWidget(LaunchpadDropdownWidget):
    """Redefining default display value as 'Any series'."""
    _messageNoValue = _("any", "Any series")


class StatusFilterWidget(LaunchpadDropdownWidget):
    """Redefining default display value as 'Any status'."""
    _messageNoValue = _("any", "Any status")


class IPPAPackageFilter(Interface):
    """The interface used as the schema for the package filtering form."""
    name_filter = TextLine(
        title=_("Package name contains"), required=False)

    series_filter = Choice(
        source=ArchiveSeriesVocabularyFactory(), required=False)

    status_filter = Choice(vocabulary=SimpleVocabulary((
        SimpleTerm(active_publishing_status, 'published', 'Published'),
        SimpleTerm(inactive_publishing_status, 'superseded', 'Superseded'),
        )), required=False)


class ArchiveSourcePackageListViewBase(ArchiveViewBase, LaunchpadFormView):
    """A Form view for filtering and batching source packages."""

    schema = IPPAPackageFilter
    custom_widget('series_filter', SeriesFilterWidget)
    custom_widget('status_filter', StatusFilterWidget)

    # By default this view will not display the sources with selectable
    # checkboxes, but subclasses can override as needed.
    selectable_sources = False

    @cachedproperty
    def series_with_sources(self):
        """Cache the context's series with sources."""
        return self.context.series_with_sources

    @property
    def specified_name_filter(self):
        """Return the specified name filter if one was specified """
        requested_name_filter = self.request.query_string_params.get(
            'field.name_filter')

        if requested_name_filter and requested_name_filter[0]:
            return requested_name_filter[0]
        else:
            return None

    def getSelectedFilterValue(self, filter_name):
        """Return the selected filter or the default, given a filter name.

        This is needed because zope's form library does not consider
        query string params (GET params) during a post request.
        """
        field_name = 'field.' + filter_name
        requested_filter = self.request.query_string_params.get(field_name)

        # If an empty filter was specified, then it's explicitly
        # been set to empty - so we use None.
        if requested_filter == ['']:
            return None

        # If the requested filter is none, then we use the default.
        default_filter_attr = 'default_' + filter_name
        if requested_filter is None:
            return getattr(self, default_filter_attr)

        # If the request included a filter, try to use it - if it's
        # invalid we use the default instead.
        vocab = self.widgets[filter_name].vocabulary
        if requested_filter[0] in vocab.by_token:
            return vocab.getTermByToken(requested_filter[0]).value
        else:
            return getattr(self, default_filter_attr)

    @property
    def plain_status_filter_widget(self):
        """Render a <select> control with no <div>s around it."""
        return self.widgets['status_filter'].renderValue(
            self.getSelectedFilterValue('status_filter'))

    @property
    def plain_series_filter_widget(self):
        """Render a <select> control with no <div>s around it."""
        return self.widgets['series_filter'].renderValue(
            self.getSelectedFilterValue('series_filter'))

    @property
    def filtered_sources(self):
        """Return the source results for display after filtering."""
        return self.context.getPublishedSources(
            name=self.specified_name_filter,
            status=self.getSelectedFilterValue('status_filter'),
            distroseries=self.getSelectedFilterValue('series_filter'),
            eager_load=True)

    @property
    def default_status_filter(self):
        """Return the default status_filter value.

        Subclasses of ArchiveViewBase can override this when required.
        """
        return self.widgets['status_filter'].vocabulary.getTermByToken(
            'published').value

    @property
    def default_series_filter(self):
        """Return the default series_filter value.

        Subclasses of ArchiveViewBase can override this when required.
        """
        return None

    @cachedproperty
    def batchnav(self):
        """Return a batch navigator of the filtered sources."""
        return BatchNavigator(self.filtered_sources, self.request)

    @cachedproperty
    def batched_sources(self):
        """Return the current batch of archive source publications."""
        results = list(self.batchnav.currentBatch())
        return ArchiveSourcePublications(results)

    @cachedproperty
    def has_sources_for_display(self):
        """Whether or not the PPA has any source packages for display.

        This is after any filtering or overriding of the sources() method.
        """
        return not self.filtered_sources.is_empty()


class ArchiveView(ArchiveSourcePackageListViewBase):
    """Default Archive view class.

    Implements useful actions and collects useful sets for the page template.
    """

    implements(IArchiveIndexActionsMenu)

    def initialize(self):
        """Redirect if our context is a main archive."""
        if self.context.is_main:
            self.request.response.redirect(
                canonical_url(self.context.distribution))
            return
        super(ArchiveView, self).initialize()

    @property
    def displayname_edit_widget(self):
        display_name = IArchive['displayname']
        title = "Edit the displayname"
        return TextLineEditorWidget(
            self.context, display_name, title, 'h1', max_width='95%',
            truncate_lines=1)

    @property
    def default_series_filter(self):
        """Return the distroseries identified by the user-agent."""
        version_number = get_user_agent_distroseries(
            self.request.getHeader('HTTP_USER_AGENT'))

        # Check if this version is one of the available
        # distroseries for this archive:
        vocabulary = self.widgets['series_filter'].vocabulary
        for term in vocabulary:
            if (term.value is not None and
                term.value.version == version_number):
                return term.value

        # Otherwise we default to 'any'
        return None

    @property
    def archive_description_html(self):
        """The archive's description as HTML."""
        linkify_text = True
        if self.context.is_ppa:
            linkify_text = not self.context.owner.is_probationary
        archive = self.context
        description = IArchive['description']
        title = self.archive_label + " description"
        # Don't hide empty archive descriptions.  Even though the interface
        # says they are required, the model doesn't.
        return TextAreaEditorWidget(
            archive, description, title, hide_empty=False,
            linkify_text=linkify_text)

    @cachedproperty
    def latest_updates(self):
        """Return the last five published sources for this archive."""
        sources = self.context.getPublishedSources(
            status=PackagePublishingStatus.PUBLISHED)
        sources.order_by(Desc(SourcePackagePublishingHistory.datepublished))
        result_tuples = sources[:5]

        # We want to return a list of dicts for easy template rendering.
        latest_updates_list = []

        # The status.title is not presentable and the description for
        # each status is too long for use here, so define a dict of
        # concise status descriptions that will fit in a small area.
        status_names = {
            'FULLYBUILT': 'Successfully built',
            'FULLYBUILT_PENDING': 'Successfully built',
            'NEEDSBUILD': 'Waiting to build',
            'FAILEDTOBUILD': 'Failed to build:',
            'BUILDING': 'Currently building',
            'UPLOADING': 'Currently uploading',
            }

        now = datetime.now(tz=pytz.UTC)
        source_ids = [result_tuple.id for result_tuple in result_tuples]
        summaries = getUtility(
            IPublishingSet).getBuildStatusSummariesForSourceIdsAndArchive(
                source_ids, self.context)
        for source_id, status_summary in summaries.items():
            date_published = status_summary['date_published']
            source_package_name = status_summary['source_package_name']
            current_status = status_summary['status']
            duration = now - date_published

            # We'd like to include the builds in the latest updates
            # iff the build failed.
            builds = []
            if current_status == BuildSetStatus.FAILEDTOBUILD:
                builds = status_summary['builds']

            latest_updates_list.append({
                'date_published': date_published,
                'title': source_package_name,
                'status': status_names[current_status.title],
                'status_class': current_status.title,
                'duration': duration,
                'builds': builds,
                })

        latest_updates_list.sort(
            key=lambda x: x['date_published'], reverse=True)
        return latest_updates_list

    def num_updates_over_last_days(self, num_days=30):
        """Return the number of updates over the past days."""
        now = datetime.now(tz=pytz.UTC)
        created_since = now - timedelta(num_days)
        return self.context.getPublishedSources(
            created_since_date=created_since).count()

    @property
    def num_pkgs_building(self):
        """Return the number of building/waiting to build packages."""
        pkgs_building_count, pkgs_waiting_count = (
            self.context.num_pkgs_building)
        # The total is just used for conditionals in the template.
        return {
            'building': pkgs_building_count,
            'waiting': pkgs_waiting_count,
            'total': pkgs_building_count + pkgs_waiting_count,
            }


class ArchivePackagesView(ArchiveSourcePackageListViewBase):
    """Detailed packages view for an archive."""
    implements(IArchivePackagesActionMenu)

    @property
    def page_title(self):
        return smartquote('Packages in "%s"' % self.context.displayname)

    @property
    def label(self):
        return self.page_title

    @property
    def series_list_string(self):
        """Return an English string of the distroseries."""
        return english_list(
            series.displayname for series in self.series_with_sources)

    @property
    def is_copy(self):
        """Return whether the context of this view is a copy archive."""
        # This property enables menu items to be shared between
        # context and view menues.
        return self.context.is_copy

    @cachedproperty
    def package_copy_jobs(self):
        """Return incomplete PCJs targeted at this archive."""
        job_source = getUtility(IPlainPackageCopyJobSource)
        ppcjs = job_source.getIncompleteJobsForArchive(self.context)

        # Convert PPCJ into PCJ.
        # removeSecurityProxy is only used to fetch pcjs objects and preload
        # related objects.
        pcjs = [removeSecurityProxy(ppcj).context for ppcj in ppcjs]
        # Pre-load related Jobs.
        jobs = load_related(Job, pcjs, ['job_id'])
        # Pre-load related requesters.
        load_related(Person, jobs, ['requester_id'])
        # Pre-load related source archives.
        load_related(Archive, pcjs, ['source_archive_id'])

        return ppcjs.config(limit=5)

    @cachedproperty
    def has_pending_copy_jobs(self):
        return self.package_copy_jobs.any()

    @cachedproperty
    def pending_copy_jobs_text(self):
        job_source = getUtility(IPlainPackageCopyJobSource)
        count = job_source.getIncompleteJobsForArchive(self.context).count()
        if count > 5:
            return 'Showing 5 of %s' % count
    
    @cachedproperty
    def has_append_perm(self):
        return check_permission('launchpad.Append', self.context)


class ArchiveSourceSelectionFormView(ArchiveSourcePackageListViewBase):
    """Base class to implement a source selection widget for PPAs."""

    custom_widget('selected_sources', LabeledMultiCheckBoxWidget)

    selectable_sources = True

    def setNextURL(self):
        """Set self.next_url based on current context.

        This should be called during actions of subclasses.
        """
        query_string = self.request.get('QUERY_STRING', '')
        if query_string:
            self.next_url = "%s?%s" % (self.request.URL, query_string)
        else:
            self.next_url = self.request.URL

    def setUpWidgets(self, context=None):
        """Setup our custom widget which depends on the filter widget values.
        """
        # To create the selected sources field, we need to define a
        # vocabulary based on the currently selected sources (using self
        # batched_sources) but this itself requires the current values of
        # the filtering widgets. So we setup the widgets, then add the
        # extra field and create its widget too.
        super(ArchiveSourceSelectionFormView, self).setUpWidgets()

        self.form_fields += self.createSelectedSourcesField()

        self.widgets += form.setUpWidgets(
            self.form_fields.select('selected_sources'),
            self.prefix, self.context, self.request,
            data=self.initial_values, ignore_request=False)

    def focusedElementScript(self):
        """Override `LaunchpadFormView`.

        Ensure focus is only set if there are sources actually presented.
        """
        if not self.has_sources_for_display:
            return ''
        return LaunchpadFormView.focusedElementScript(self)

    def createSelectedSourcesField(self):
        """Creates the 'selected_sources' field.

        'selected_sources' is a list of elements of a vocabulary based on
        the source publications that will be presented. This way zope
        infrastructure will do the validation for us.
        """
        terms = []

        for pub in self.batched_sources:
            terms.append(SimpleTerm(pub, str(pub.id), pub.displayname))
        return form.Fields(
            List(__name__='selected_sources',
                 title=_('Available sources'),
                 value_type=Choice(vocabulary=SimpleVocabulary(terms)),
                 required=False,
                 default=[],
                 description=_('Select one or more sources to be submitted '
                               'to an action.')))

    @property
    def action_url(self):
        """The forms should post to themselves, including GET params."""
        return "%s?%s" % (self.request.getURL(), self.request['QUERY_STRING'])


class IArchivePackageDeletionForm(IPPAPackageFilter):
    """Schema used to delete packages within an archive."""

    deletion_comment = TextLine(
        title=_("Deletion comment"), required=False,
        description=_("The reason why the package is being deleted."))


class ArchivePackageDeletionView(ArchiveSourceSelectionFormView):
    """Archive package deletion view class.

    This view presents a package selection slot in a POST form implementing
    a deletion action that can be performed upon a set of selected packages.
    """

    schema = IArchivePackageDeletionForm
    custom_widget('deletion_comment', StrippedTextWidget, displayWidth=50)
    label = 'Delete packages'

    @property
    def label(self):
        return 'Delete packages from %s' % self.context.displayname

    @property
    def default_status_filter(self):
        """Present records in any status by default."""
        return None

    @cachedproperty
    def filtered_sources(self):
        """Return the filtered results of publishing records for deletion.

        This overrides ArchiveViewBase.filtered_sources to use a
        different method on the context specific to deletion records.
        """
        return self.context.getSourcesForDeletion(
            name=self.specified_name_filter,
            status=self.getSelectedFilterValue('status_filter'),
            distroseries=self.getSelectedFilterValue('series_filter'))

    @cachedproperty
    def has_sources(self):
        """Whether or not this PPA has any sources before filtering.

        Overrides the ArchiveViewBase.has_sources
        to ensure that it only returns true if there are sources
        that can be deleted in this archive.
        """
        return not self.context.getSourcesForDeletion().is_empty()

    def validate_delete(self, action, data):
        """Validate deletion parameters.

        Ensure we have, at least, one source selected and deletion_comment
        is given.
        """
        form.getWidgetsData(self.widgets, 'field', data)

        if len(data.get('selected_sources', [])) == 0:
            self.setFieldError('selected_sources', 'No sources selected.')

    @action(_("Request Deletion"), name="delete", validator="validate_delete")
    def delete_action(self, action, data):
        """Perform the deletion of the selected packages.

        The deletion will be performed upon the 'selected_sources' contents
        storing the given 'deletion_comment'.
        """
        if len(self.errors) != 0:
            return

        comment = data.get('deletion_comment')
        selected_sources = data.get('selected_sources')

        # Perform deletion of the source and its binaries.
        publishing_set = getUtility(IPublishingSet)
        publishing_set.requestDeletion(selected_sources, self.user, comment)

        # Present a page notification describing the action.
        messages = [structured(
            '<p>Source and binaries deleted by %s:', self.user.displayname)]
        for source in selected_sources:
            messages.append(structured('<br/>%s', source.displayname))
        messages.append(structured(
            '</p>\n<p>Deletion comment: %s</p>', comment))
        notification = structured(
            '\n'.join([msg.escapedtext for msg in messages]))
        self.request.response.addNotification(notification)

        self.setNextURL()


class DestinationArchiveDropdownWidget(LaunchpadDropdownWidget):
    """Redefining default display value as 'This PPA'."""
    _messageNoValue = _("vocabulary-copy-to-context-ppa", "This PPA")


class DestinationSeriesDropdownWidget(LaunchpadDropdownWidget):
    """Redefining default display value as 'The same series'."""
    _messageNoValue = _("vocabulary-copy-to-same-series", "The same series")


def copy_asynchronously(source_pubs, dest_archive, dest_series, dest_pocket,
                        include_binaries, dest_url=None,
                        dest_display_name=None, person=None,
                        check_permissions=True, sponsored=None):
    """Schedule jobs to copy packages later.

    :return: A `structured` with human-readable feedback about the
        operation.
    :raises CannotCopy: If `check_permissions` is True and the copy is
        not permitted.
    """
    if check_permissions:
        check_copy_permissions(
            person, dest_archive, dest_series, dest_pocket, source_pubs)

    job_source = getUtility(IPlainPackageCopyJobSource)
    for spph in source_pubs:
        job_source.create(
            spph.source_package_name, spph.archive, dest_archive,
            dest_series if dest_series is not None else spph.distroseries,
            dest_pocket, include_binaries=include_binaries,
            package_version=spph.sourcepackagerelease.version,
            copy_policy=PackageCopyPolicy.INSECURE,
            requester=person, sponsored=sponsored, unembargo=True,
            source_distroseries=spph.distroseries, source_pocket=spph.pocket)

    return copy_asynchronously_message(
        len(source_pubs), dest_archive, dest_url, dest_display_name)


def copy_asynchronously_message(source_pubs_count, dest_archive, dest_url=None,
                                dest_display_name=None):
    """Return a message detailing the sync action.

    :param source_pubs_count: The number of source pubs requested for syncing.
    :param dest_archive: The destination IArchive.
    :param dest_url: The URL of the destination to display in the
        notification box.  Defaults to the target archive.
    :param dest_display_name: The text to use for the dest_url link.
        Defaults to the target archive's display name.
    """
    if dest_url is None:
        dest_url = canonical_url(dest_archive) + '/+packages'

    if dest_display_name is None:
        dest_display_name = dest_archive.displayname

    package_or_packages = get_plural_text(
        source_pubs_count, "package", "packages")
    if source_pubs_count == 0:
        return structured(
            'Requested sync of %s %s to <a href="%s">%s</a>.',
            source_pubs_count, package_or_packages, dest_url,
            dest_display_name)
    else:
        this_or_these = get_plural_text(
            source_pubs_count, "this", "these")
        return structured(
            'Requested sync of %s %s to <a href="%s">%s</a>.<br />'
            "Please allow some time for %s to be processed.",
            source_pubs_count, package_or_packages, dest_url,
            dest_display_name, this_or_these)


def render_cannotcopy_as_html(cannotcopy_exception):
    """Render `CannotCopy` exception as HTML for display in the page."""
    error_lines = str(cannotcopy_exception).splitlines()

    if len(error_lines) == 1:
        intro = "The following source cannot be copied:"
    else:
        intro = "The following sources cannot be copied:"

    # Produce structured HTML.  Include <li>%s</li> placeholders for
    # each error line, but have "structured" interpolate the actual
    # package names.  It will escape them as needed.
    html_text = """
        <p>%s</p>
        <ul>
        %s
        </ul>
        """ % (intro, "<li>%s</li>" * len(error_lines))
    return structured(html_text, *error_lines)


class PackageCopyingMixin:
    """A mixin class that adds helpers for package copying."""

    def do_copy(self, sources_field_name, source_pubs, dest_archive,
                dest_series, dest_pocket, include_binaries,
                dest_url=None, dest_display_name=None, person=None,
                check_permissions=True, sponsored_person=None):
        """Copy packages and add appropriate feedback to the browser page.

        This will copy asynchronously, scheduling jobs that will be
        processed by a script.

        :param sources_field_name: The name of the form field to set errors
            on when the copy fails
        :param source_pubs: A list of SourcePackagePublishingHistory to copy
        :param dest_archive: The destination IArchive
        :param dest_series: The destination IDistroSeries
        :param dest_pocket: The destination PackagePublishingPocket
        :param include_binaries: Boolean, whether to copy binaries with the
            sources
        :param dest_url: The URL of the destination to display in the
            notification box.  Defaults to the target archive and will be
            automatically escaped for inclusion in the output.
        :param dest_display_name: The text to use for the dest_url link.
            Defaults to the target archive's display name and will be
            automatically escaped for inclusion in the output.
        :param person: The person requesting the copy.
        :param: check_permissions: boolean indicating whether or not the
            requester's permissions to copy should be checked.
        :param sponsored_person: An IPerson representing the person being
            sponsored.

        :return: True if the copying worked, False otherwise.
        """
        try:
            notification = copy_asynchronously(
                source_pubs, dest_archive, dest_series, dest_pocket,
                include_binaries, dest_url=dest_url,
                dest_display_name=dest_display_name, person=person,
                check_permissions=check_permissions,
                sponsored=sponsored_person)
        except CannotCopy as error:
            self.setFieldError(
                sources_field_name, render_cannotcopy_as_html(error))
            return False

        self.request.response.addNotification(notification)
        return True


def make_archive_vocabulary(archives):
    terms = []
    for archive in archives:
        token = '%s/%s' % (archive.owner.name, archive.name)
        label = '%s [~%s]' % (archive.displayname, token)
        terms.append(SimpleTerm(archive, token, label))
    return SimpleVocabulary(terms)


class ArchivePackageCopyingView(ArchiveSourceSelectionFormView,
                                PackageCopyingMixin):
    """Archive package copying view class.

    This view presents a package selection slot in a POST form implementing
    a copying action that can be performed upon a set of selected packages.
    """
    schema = IPPAPackageFilter
    custom_widget('destination_archive', DestinationArchiveDropdownWidget)
    custom_widget('destination_series', DestinationSeriesDropdownWidget)
    custom_widget('include_binaries', LaunchpadRadioWidget)
    label = 'Copy packages'

    @property
    def label(self):
        return 'Copy packages from %s' % self.context.displayname

    default_pocket = PackagePublishingPocket.RELEASE

    @property
    def default_status_filter(self):
        """Present published records by default."""
        return self.widgets['status_filter'].vocabulary.getTermByToken(
            'published').value

    def setUpFields(self):
        """Override `ArchiveSourceSelectionFormView`.

        See `createDestinationFields` method.
        """
        ArchiveSourceSelectionFormView.setUpFields(self)
        self.form_fields = (
            self.createDestinationArchiveField() +
            self.createDestinationSeriesField() +
            self.createIncludeBinariesField() +
            self.form_fields)

    @cachedproperty
    def ppas_for_user(self):
        """Return all PPAs for which the user accessing the page can copy."""
        return list(
            ppa
            for ppa in getUtility(IArchiveSet).getPPAsForUser(self.user)
            if check_permission('launchpad.Append', ppa))

    @cachedproperty
    def can_copy(self):
        """Whether or not the current user can copy packages to any PPA."""
        return len(self.ppas_for_user) > 0

    @cachedproperty
    def can_copy_to_context_ppa(self):
        """Whether or not the current user can copy to the context PPA.

        It's always False for non-PPA archives, copies to non-PPA archives
        are explicitly denied in the UI.
        """
        # XXX cprov 2009-07-17 bug=385503: copies cannot be properly traced
        # that's why we explicitly don't allow them do be done via the UI
        # in main archives, only PPAs.
        return (self.context.is_ppa and
                self.context.checkArchivePermission(self.user))

    def createDestinationArchiveField(self):
        """Create the 'destination_archive' field."""
        # Do not include the context PPA in the dropdown widget.
        ppas = [ppa for ppa in self.ppas_for_user if self.context != ppa]
        return form.Fields(
            Choice(__name__='destination_archive',
                   title=_('Destination PPA'),
                   vocabulary=make_archive_vocabulary(ppas),
                   description=_("Select the destination PPA."),
                   missing_value=self.context,
                   required=not self.can_copy_to_context_ppa))

    def createDestinationSeriesField(self):
        """Create the 'destination_series' field."""
        terms = []
        # XXX cprov 20080408: this code uses the context PPA series instead
        # of targeted or all series available in Launchpad. It might become
        # a problem when we support PPAs for other distribution. If we do
        # it will be probably simpler to use the DistroSeries vocabulary
        # and validate the selected value before copying.
        for series in self.context.distribution.series:
            if series.status == SeriesStatus.OBSOLETE:
                continue
            terms.append(
                SimpleTerm(series, str(series.name), series.displayname))
        return form.Fields(
            Choice(__name__='destination_series',
                   title=_('Destination series'),
                   vocabulary=SimpleVocabulary(terms),
                   description=_("Select the destination series."),
                   required=False))

    def createIncludeBinariesField(self):
        """Create the 'include_binaries' field.

        'include_binaries' widget is a choice, rendered as radio-buttons,
        with two options that provides a Boolean as its value:

         ||      Option     || Value ||
         || REBUILD_SOURCES || False ||
         || COPY_BINARIES   || True  ||

        When omitted in the form, this widget defaults for REBUILD_SOURCES
        option when rendered.
        """
        rebuild_sources = SimpleTerm(
                False, 'REBUILD_SOURCES', _('Rebuild the copied sources'))
        copy_binaries = SimpleTerm(
            True, 'COPY_BINARIES', _('Copy existing binaries'))
        terms = [rebuild_sources, copy_binaries]

        return form.Fields(
            Choice(__name__='include_binaries',
                   title=_('Copy options'),
                   vocabulary=SimpleVocabulary(terms),
                   description=_("How the selected sources should be copied "
                                 "to the destination archive."),
                   missing_value=rebuild_sources,
                   default=False,
                   required=True))

    @action(_("Update"), name="update")
    def update_action(self, action, data):
        """Simply re-issue the form with the new values."""
        pass

    @action(_("Copy Packages"), name="copy")
    def copy_action(self, action, data):
        """Perform the copy of the selected packages.

        Ensure that at least one source is selected. Executes `do_copy`
        for all the selected sources.

        If `do_copy` raises `CannotCopy` the error content is set as
        the 'selected_sources' field error.

        if `do_copy` succeeds, an informational messages is set containing
        the copied packages.
        """
        selected_sources = data.get('selected_sources')
        destination_archive = data.get('destination_archive')
        destination_series = data.get('destination_series')
        include_binaries = data.get('include_binaries')
        destination_pocket = self.default_pocket

        if len(selected_sources) == 0:
            self.setFieldError('selected_sources', 'No sources selected.')
            return

        # PackageCopyingMixin.do_copy() does the work of copying and
        # setting up on-page notifications.
        if self.do_copy(
            'selected_sources', selected_sources, destination_archive,
            destination_series, destination_pocket, include_binaries,
            person=self.user):
            # The copy worked so we can redirect back to the page to
            # show the result.
            self.setNextURL()


def get_escapedtext(message):
    """Return escapedtext if message is an `IStructuredString`."""
    if IStructuredString.providedBy(message):
        return message.escapedtext
    else:
        return message


class ArchiveEditDependenciesView(ArchiveViewBase, LaunchpadFormView):
    """Archive dependencies view class."""

    schema = IArchiveEditDependenciesForm

    custom_widget('selected_dependencies', PlainMultiCheckBoxWidget,
                  cssClass='line-through-when-checked ppa-dependencies')
    custom_widget('primary_dependencies', LaunchpadRadioWidget,
                  cssClass='highlight-selected')
    custom_widget('primary_components', LaunchpadRadioWidget,
                  cssClass='highlight-selected')

    label = "Edit PPA dependencies"
    page_title = label

    def initialize(self):
        self.cancel_url = canonical_url(self.context)
        self._messages = []
        LaunchpadFormView.initialize(self)

    def setUpFields(self):
        """Override `LaunchpadFormView`.

        In addition to setting schema fields, also initialize the
        'selected_dependencies' field.

        See `createSelectedSourcesField` method.
        """
        LaunchpadFormView.setUpFields(self)

        self.form_fields = (
            self.createSelectedDependenciesField() +
            self.createPrimaryDependenciesField() +
            self.createPrimaryComponentsField() +
            self.form_fields)

    def focusedElementScript(self):
        """Override `LaunchpadFormView`.

        Move focus to the 'dependency_candidate' input field when there is
        no recorded dependency to present. Otherwise it will default to
        the first recorded dependency checkbox.
        """
        if not self.has_dependencies:
            self.initial_focus_widget = "dependency_candidate"
        return LaunchpadFormView.focusedElementScript(self)

    def createSelectedDependenciesField(self):
        """Creates the 'selected_dependencies' field.

        'selected_dependencies' is a list of elements of a vocabulary
        containing all the current recorded dependencies for the context
        PPA.
        """
        terms = []
        for archive_dependency in self.context.dependencies:
            dependency = archive_dependency.dependency
            if not dependency.is_ppa:
                continue
            if check_permission('launchpad.View', dependency):
                dependency_label = structured(
                    '<a href="%s">%s</a>',
                    canonical_url(dependency), archive_dependency.title)
            else:
                dependency_label = archive_dependency.title
            dependency_token = '%s/%s' % (
                dependency.owner.name, dependency.name)
            term = SimpleTerm(
                dependency, dependency_token, dependency_label)
            terms.append(term)
        return form.Fields(
            List(__name__='selected_dependencies',
                 title=_('Extra dependencies'),
                 value_type=Choice(vocabulary=SimpleVocabulary(terms)),
                 required=False,
                 default=[],
                 description=_(
                    'Select one or more dependencies to be removed.')))

    def createPrimaryDependenciesField(self):
        """Create the 'primary_dependencies' field.

        'primary_dependency' widget is a choice, rendered as radio-buttons,
        with 5 options that provides `PackagePublishingPocket` as result:

         || Option    || Value     ||
         || Release   || RELEASE   ||
         || Security  || SECURITY  ||
         || Default   || UPDATES   ||
         || Proposed  || PROPOSED  ||
         || Backports || BACKPORTS ||

        When omitted in the form, this widget defaults for 'Default'
        option when rendered.
        """
        release = SimpleTerm(
            PackagePublishingPocket.RELEASE, 'RELEASE',
            _('Basic (only released packages).'))
        security = SimpleTerm(
            PackagePublishingPocket.SECURITY, 'SECURITY',
            _('Security (basic dependencies and important security '
              'updates).'))
        updates = SimpleTerm(
            PackagePublishingPocket.UPDATES, 'UPDATES',
            _('Default (security dependencies and recommended updates).'))
        proposed = SimpleTerm(
            PackagePublishingPocket.PROPOSED, 'PROPOSED',
            _('Proposed (default dependencies and proposed updates).'))
        backports = SimpleTerm(
            PackagePublishingPocket.BACKPORTS, 'BACKPORTS',
            _('Backports (default dependencies and unsupported updates).'))

        terms = [release, security, updates, proposed, backports]

        primary_dependency = self.context.getArchiveDependency(
            self.context.distribution.main_archive)
        if primary_dependency is None:
            default_value = default_pocket_dependency
        else:
            default_value = primary_dependency.pocket

        primary_dependency_vocabulary = SimpleVocabulary(terms)
        current_term = primary_dependency_vocabulary.getTerm(
            default_value)

        return form.Fields(
            Choice(__name__='primary_dependencies',
                   title=_(
                    "%s dependencies"
                    % self.context.distribution.displayname),
                   vocabulary=primary_dependency_vocabulary,
                   description=_(
                    "Select which packages of the %s primary archive "
                    "should be used as build-dependencies when building "
                    "sources in this PPA."
                    % self.context.distribution.displayname),
                   missing_value=current_term,
                   default=default_value,
                   required=True))

    def createPrimaryComponentsField(self):
        """Create the 'primary_components' field.

        'primary_components' widget is a choice, rendered as radio-buttons,
        with two options that provides an IComponent as its value:

         ||      Option    ||   Value    ||
         || ALL_COMPONENTS || multiverse ||
         || FOLLOW_PRIMARY ||    None    ||

        When omitted in the form, this widget defaults to 'All ubuntu
        components' option when rendered. Other components, such as 'main',
        or 'contrib' will be added to the list of options if they are used.
        """
        multiverse = getUtility(IComponentSet)['multiverse']

        all_components = SimpleTerm(
            multiverse, 'ALL_COMPONENTS',
            _('Use all %s components available.' %
              self.context.distribution.displayname))
        follow_primary = SimpleTerm(
            None, 'FOLLOW_PRIMARY',
            _('Use the same components used for each source in the %s '
              'primary archive.' % self.context.distribution.displayname))

        primary_dependency = self.context.getArchiveDependency(
            self.context.distribution.main_archive)
        if primary_dependency is None:
            default_value = getUtility(IComponentSet)[
                default_component_dependency_name]
        else:
            default_value = primary_dependency.component

        terms = [all_components, follow_primary]
        if default_value and default_value != multiverse:
            current_component = SimpleTerm(
                default_value, 'OTHER_COMPONENT',
                _('Unsupported component (%s)' % default_value.name))
            terms.append(current_component)
        primary_components_vocabulary = SimpleVocabulary(terms)
        current_term = primary_components_vocabulary.getTerm(default_value)

        return form.Fields(
            Choice(__name__='primary_components',
                   title=_('%s components' %
                           self.context.distribution.displayname),
                   vocabulary=primary_components_vocabulary,
                   description=_("Which %s components of the archive pool "
                                 "should be used when fetching build "
                                 "dependencies." %
                                 self.context.distribution.displayname),
                   missing_value=current_term,
                   default=default_value,
                   required=True))

    @cachedproperty
    def has_dependencies(self):
        """Whether or not the PPA has recorded dependencies."""
        return bool(self.context.dependencies)

    @property
    def messages(self):
        return '\n'.join(map(get_escapedtext, self._messages))

    def _remove_dependencies(self, data):
        """Perform the removal of the selected dependencies."""
        selected_dependencies = data.get('selected_dependencies', [])

        if len(selected_dependencies) == 0:
            return

        # Perform deletion of the source and its binaries.
        for dependency in selected_dependencies:
            self.context.removeArchiveDependency(dependency)

        # Present a page notification describing the action.
        self._messages.append('<p>Dependencies removed:')
        for dependency in selected_dependencies:
            self._messages.append(
                structured('<br/>%s', dependency.displayname))
        self._messages.append('</p>')

    def _add_ppa_dependencies(self, data):
        """Record the selected dependency."""
        dependency_candidate = data.get('dependency_candidate')
        if dependency_candidate is None:
            return

        self.context.addArchiveDependency(
            dependency_candidate, PackagePublishingPocket.RELEASE,
            getUtility(IComponentSet)['main'])

        self._messages.append(structured(
            '<p>Dependency added: %s</p>', dependency_candidate.displayname))

    def _add_primary_dependencies(self, data):
        """Record the selected dependency."""
        # Received values.
        dependency_pocket = data.get('primary_dependencies')
        dependency_component = data.get('primary_components')

        # Check if the given values correspond to the default scenario
        # for the context archive.
        default_component_dependency = getUtility(IComponentSet)[
            default_component_dependency_name]
        is_default_dependency = (
            dependency_pocket == default_pocket_dependency and
            dependency_component == default_component_dependency)

        primary_dependency = self.context.getArchiveDependency(
            self.context.distribution.main_archive)

        # No action is required if there is no primary_dependency
        # override set and the given values match it.
        if primary_dependency is None and is_default_dependency:
            return

        # Similarly, no action is required if the given values match
        # the existing primary_dependency override.
        if (primary_dependency is not None and
            primary_dependency.pocket == dependency_pocket and
            primary_dependency.component == dependency_component):
            return

        # Remove any primary dependencies overrides.
        if primary_dependency is not None:
            self.context.removeArchiveDependency(
                self.context.distribution.main_archive)

        if is_default_dependency:
            self._messages.append(
                '<p>Default primary dependencies restored.</p>')
            return

        # Install the required primary archive dependency override.
        primary_dependency = self.context.addArchiveDependency(
            self.context.distribution.main_archive, dependency_pocket,
            dependency_component)
        self._messages.append(structured(
            '<p>Primary dependency added: %s</p>', primary_dependency.title))

    @action(_("Save"), name="save")
    def save_action(self, action, data):
        """Save dependency configuration changes.

        See `_remove_dependencies`, `_add_ppa_dependencies` and
        `_add_primary_dependencies`.

        Redirect to the same page once the form is processed, to avoid widget
        refreshing. And render a page notification with the summary of the
        changes made.
        """
        # Process the form.
        self._add_primary_dependencies(data)
        try:
            self._add_ppa_dependencies(data)
        except ArchiveDependencyError as e:
            self.setFieldError('dependency_candidate', str(e))
            return
        self._remove_dependencies(data)

        # Issue a notification if anything was changed.
        if len(self.messages) > 0:
            self.request.response.addNotification(
                structured(self.messages))
        # Redirect after POST.
        self.next_url = self.request.URL


class ArchiveActivateView(LaunchpadFormView):
    """PPA activation view class."""

    schema = IArchive
    field_names = ('name', 'displayname', 'description')
    custom_widget('description', TextAreaWidget, height=3)
    custom_widget('name', PPANameWidget, label="URL")
    label = 'Activate a Personal Package Archive'
    page_title = 'Activate PPA'

    @property
    def ubuntu(self):
        return getUtility(ILaunchpadCelebrities).ubuntu

    @cachedproperty
    def visible_ppas(self):
        return self.context.getVisiblePPAs(self.user)

    @property
    def initial_values(self):
        """Set up default values for form fields."""
        # Suggest a default value of "ppa" for the name for the
        # first PPA activation.
        if self.context.archive is None:
            return {'name': 'ppa'}
        return {}

    def setUpFields(self):
        """Override `LaunchpadFormView`.

        Reorder the fields in a way the make more sense to users and also
        present a checkbox for acknowledging the PPA-ToS if the user is
        creating his first PPA.
        """
        LaunchpadFormView.setUpFields(self)

        if self.context.archive is None:
            accepted = Bool(
                __name__='accepted',
                title=_("I have read and accepted the PPA Terms of Use."),
                required=True, default=False)
            self.form_fields += form.Fields(accepted)

    def validate(self, data):
        """Ensure user has checked the 'accepted' checkbox."""
        if len(self.errors) > 0:
            return

        default_ppa = self.context.archive

        proposed_name = data.get('name')
        if proposed_name is None and default_ppa is not None:
            self.addError(
                'The default PPA is already activated. Please specify a '
                'name for the new PPA and resubmit the form.')

        errors = validate_ppa(
            self.context, proposed_name, private=self.is_private_team)
        if errors is not None:
            self.addError(errors)

        if default_ppa is None and not data.get('accepted'):
            self.setFieldError(
                'accepted',
                "PPA Terms of Service must be accepted to activate a PPA.")

    @action(_("Activate"), name="activate")
    def save_action(self, action, data):
        """Activate a PPA and moves to its page."""
        # 'name' field is omitted from the form data for default PPAs and
        # it's dealt with by IArchive.new(), which will use the default
        # PPA name.
        name = data.get('name', None)
        displayname = data['displayname']
        description = data['description']
        ppa = self.context.createPPA(
            name, displayname, description, private=self.is_private_team)
        self.next_url = canonical_url(ppa)

    @property
    def is_private_team(self):
        """Is the person a private team?

        :return: True only if visibility is PRIVATE.
        :rtype: bool
        """
        return self.context.visibility == PersonVisibility.PRIVATE


class ArchiveBuildsView(ArchiveViewBase, BuildRecordsView):
    """Build Records View for IArchive."""

    # The archive builds view presents all package builds (binary
    # or source package recipe builds).
    binary_only = False

    @property
    def default_build_state(self):
        """See `IBuildRecordsView`.

        Present NEEDSBUILD build records by default for PPAs.
        """
        return BuildStatus.NEEDSBUILD


class BaseArchiveEditView(LaunchpadEditFormView, ArchiveViewBase):

    schema = IArchive
    field_names = []

    @action(_("Save"), name="save", validator="validate_save")
    def save_action(self, action, data):
        # Archive is enabled and user wants it disabled.
        if self.context.enabled == True and data['enabled'] == False:
            self.context.disable()
        # Archive is disabled and user wants it enabled.
        if self.context.enabled == False and data['enabled'] == True:
            self.context.enable()
        # IArchive.enabled is a read-only property that cannot be set
        # directly.
        del(data['enabled'])
        self.updateContextFromData(data)
        self.next_url = canonical_url(self.context)

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def validate_save(self, action, data):
        """Check that we're not reenabling a deleted archive.."""
        form.getWidgetsData(self.widgets, 'field', data)

        # Deleted PPAs can't be reactivated.
        if ((data.get('enabled') or data.get('publish'))
            and not self.context.is_active):
            self.setFieldError(
                "enabled", "Deleted PPAs can't be enabled.")


class ArchiveEditView(BaseArchiveEditView):

    field_names = ['displayname', 'description', 'enabled', 'publish']
    custom_widget(
        'description', TextAreaWidget, height=10, width=30)
    page_title = 'Change details'

    @property
    def label(self):
        return 'Edit %s' % self.context.displayname


class EnableRestrictedProcessorsMixin:
    """A mixin that provides enabled_restricted_processors field support"""

    def createEnabledRestrictedProcessors(self, description=None):
        """Creates the 'enabled_restricted_processors' field."""
        terms = []
        for processor in getUtility(IProcessorSet).getRestricted():
            terms.append(SimpleTerm(
                processor, token=processor.name, title=processor.title))
        old_field = IArchive['enabled_restricted_processors']
        return form.Fields(
            List(__name__=old_field.__name__,
                 title=old_field.title,
                 value_type=Choice(vocabulary=SimpleVocabulary(terms)),
                 required=False,
                 description=old_field.description if description is None
                     else description),
                 render_context=self.render_context)


class ArchiveAdminView(BaseArchiveEditView, EnableRestrictedProcessorsMixin):

    field_names = [
        'enabled',
        'private',
        'suppress_subscription_notifications',
        'require_virtualized',
        'build_debug_symbols',
        'publish_debug_symbols',
        'permit_obsolete_series_uploads',
        'authorized_size',
        'relative_build_score',
        'external_dependencies',
        ]
    custom_widget('external_dependencies', TextAreaWidget, height=3)
    custom_widget('enabled_restricted_processors', LabeledMultiCheckBoxWidget)
    page_title = 'Administer'

    @property
    def label(self):
        return 'Administer %s' % self.context.displayname

    def validate_save(self, action, data):
        """Validate the save action on ArchiveAdminView."""
        super(ArchiveAdminView, self).validate_save(action, data)

        if data.get('private') != self.context.private:
            # The privacy is being switched.
            if not self.context.getPublishedSources().is_empty():
                self.setFieldError(
                    'private',
                    'This archive already has published sources. It is '
                    'not possible to switch the privacy.')

        if self.owner_is_private_team and not data['private']:
            self.setFieldError(
                'private',
                'Private teams may not have public archives.')

        # Check the external_dependencies field.
        ext_deps = data.get('external_dependencies')
        if ext_deps is not None:
            errors = validate_external_dependencies(ext_deps)
            if len(errors) != 0:
                error_text = "\n".join(errors)
                self.setFieldError('external_dependencies', error_text)

    @property
    def owner_is_private_team(self):
        """Is the owner a private team?

        :return: True only if visibility is PRIVATE.
        :rtype: bool
        """
        return self.context.owner.visibility == PersonVisibility.PRIVATE

    @property
    def initial_values(self):
        return {
            'enabled_restricted_processors':
                self.context.enabled_restricted_processors,
            }

    def setUpFields(self):
        """Override `LaunchpadEditFormView`.

        See `createEnabledRestrictedProcessors` method.
        """
        super(ArchiveAdminView, self).setUpFields()
        self.form_fields += self.createEnabledRestrictedProcessors()


class ArchiveDeleteView(LaunchpadFormView):
    """View class for deleting `IArchive`s"""

    schema = Interface

    @property
    def page_title(self):
        return smartquote('Delete "%s"' % self.context.displayname)

    @property
    def label(self):
        return self.page_title

    @property
    def can_be_deleted(self):
        return self.context.status not in (
            ArchiveStatus.DELETING, ArchiveStatus.DELETED)

    @property
    def waiting_for_deletion(self):
        return self.context.status == ArchiveStatus.DELETING

    @property
    def next_url(self):
        # We redirect back to the PPA owner's profile page on a
        # successful action.
        return canonical_url(self.context.owner)

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @action(_("Permanently delete PPA"), name="delete_ppa")
    def action_delete_ppa(self, action, data):
        self.context.delete(self.user)
        self.request.response.addInfoNotification(
            "Deletion of '%s' has been requested and the repository will be "
            "removed shortly." % self.context.title)
