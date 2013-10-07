# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'DistributionMirrorEditView',
    'DistributionMirrorOverviewMenu',
    'DistributionMirrorAddView',
    'DistributionMirrorView',
    'DistributionMirrorReviewView',
    'DistributionMirrorReassignmentView',
    'DistributionMirrorDeleteView',
    'DistributionMirrorProberLogView',
    'DistributionMirrorBreadcrumb',
    ]

from datetime import datetime

import pytz
from zope.event import notify
from zope.interface import implements
from zope.lifecycleevent import ObjectCreatedEvent

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.archivepublisher.debversion import Version
from lp.registry.browser.objectreassignment import ObjectReassignmentView
from lp.registry.interfaces.distribution import IDistributionMirrorMenuMarker
from lp.registry.interfaces.distributionmirror import IDistributionMirror
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import TitleBreadcrumb
from lp.services.webapp.publisher import LaunchpadView
from lp.soyuz.browser.sourceslist import (
    SourcesListEntries,
    SourcesListEntriesView,
    )


class DistributionMirrorOverviewMenu(NavigationMenu):

    usedfor = IDistributionMirror
    facet = 'overview'
    links = ['proberlogs', 'edit', 'review', 'reassign', 'delete']

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def proberlogs(self):
        text = 'Prober logs'
        enabled = self.context.last_probe_record is not None
        return Link('+prober-logs', text, icon='info', enabled=enabled)

    @enabled_with_permission('launchpad.Admin')
    def delete(self):
        enabled = self.context.last_probe_record is None
        text = 'Delete this mirror'
        return Link('+delete', text, icon='remove', enabled=enabled)

    @enabled_with_permission('launchpad.Edit')
    def reassign(self):
        text = 'Change owner'
        return Link('+reassign', text, icon='edit')

    @enabled_with_permission('launchpad.Admin')
    def review(self):
        text = 'Review mirror'
        return Link('+review', text, icon='edit')


class _FlavoursByDistroSeries:
    """A simple class to help when rendering a table of series and flavours
    mirrored by a given Distro Series mirror.
    """

    def __init__(self, distroseries, flavours):
        self.distroseries = distroseries
        self.flavours = flavours


class DistributionMirrorBreadcrumb(TitleBreadcrumb):
    """Breadcrumb for distribution mirrors."""


class DistributionMirrorView(LaunchpadView):

    @property
    def page_title(self):
        """The HTML page title."""
        values = dict(distribution=self.context.distribution.displayname,
                      name=self.context.title)
        return '%(distribution)s mirror "%(name)s"' % values

    def initialize(self):
        """Set up the sources.list entries for display."""
        valid_series = []
        # use an explicit loop to preserve ordering while getting rid of dupes
        for arch_series in self.summarized_arch_series:
            series = arch_series.distro_arch_series.distroseries
            if series not in valid_series:
                valid_series.append(series)
        entries = SourcesListEntries(self.context.distribution,
                                     self.context.base_url,
                                     valid_series)
        self.sources_list_entries = SourcesListEntriesView(
            entries, self.request, initially_without_selection=True)

    @cachedproperty
    def probe_records(self):
        return BatchNavigator(self.context.all_probe_records, self.request)

    # Cached because it is used to construct the entries in initialize()
    @cachedproperty
    def summarized_arch_series(self):
        mirrors = self.context.getSummarizedMirroredArchSeries()
        return sorted(
            mirrors, reverse=True,
            key=lambda mirror: Version(
                mirror.distro_arch_series.distroseries.version))

    @property
    def summarized_source_series(self):
        mirrors = self.context.getSummarizedMirroredSourceSeries()
        return sorted(mirrors, reverse=True,
                      key=lambda mirror: Version(mirror.distroseries.version))

    def getCDImageMirroredFlavoursBySeries(self):
        """Return a list of _FlavoursByDistroSeries objects ordered
        descending by version.
        """
        all_series = {}
        for cdimage in self.context.cdimage_series:
            series, flavour = cdimage.distroseries, cdimage.flavour
            flavours_by_series = all_series.get(series)
            if flavours_by_series is None:
                flavours_by_series = _FlavoursByDistroSeries(series, [])
                all_series[series] = flavours_by_series
            flavours_by_series.flavours.append(flavour)
        flavours_by_series = all_series.values()
        return sorted(flavours_by_series, reverse=True,
                      key=lambda item: Version(item.distroseries.version))


class DistributionMirrorDeleteView(LaunchpadFormView):

    schema = IDistributionMirror
    field_names = []

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Delete mirror %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @action(_("Delete Mirror"), name="delete")
    def delete_action(self, action, data):
        # Although users will never be able to see/submit this form for a
        # mirror which has been probed already, they may have a stale page
        # and so we do this check here.
        if self.context.last_probe_record is not None:
            self.request.response.addInfoNotification(
                "This mirror has been probed and thus can't be deleted.")
            self.next_url = canonical_url(self.context)
            return

        self.next_url = canonical_url(self.context.distribution,
            view_name='+pendingreviewmirrors')
        self.request.response.addInfoNotification(
            "Mirror %s has been deleted." % self.context.title)
        self.context.destroySelf()

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)


class DistributionMirrorAddView(LaunchpadFormView):

    implements(IDistributionMirrorMenuMarker)
    schema = IDistributionMirror
    field_names = ["displayname", "description", "whiteboard", "http_base_url",
                   "ftp_base_url", "rsync_base_url", "speed", "country",
                   "content", "official_candidate"]
    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return "Register a new mirror for %s" % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action(_("Register Mirror"), name="create")
    def create_action(self, action, data):
        mirror = self.context.newMirror(
            owner=self.user, speed=data['speed'], country=data['country'],
            content=data['content'], displayname=data['displayname'],
            description=data['description'],
            whiteboard=data['whiteboard'],
            http_base_url=data['http_base_url'],
            ftp_base_url=data['ftp_base_url'],
            rsync_base_url=data['rsync_base_url'],
            official_candidate=data['official_candidate'])

        self.next_url = canonical_url(mirror)
        notify(ObjectCreatedEvent(mirror))


class DistributionMirrorReviewView(LaunchpadEditFormView):

    schema = IDistributionMirror
    field_names = ['status', 'whiteboard']

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Review mirror %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action(_("Save"), name="save")
    def action_save(self, action, data):
        context = self.context
        if data['status'] != context.status:
            context.reviewer = self.user
            context.date_reviewed = datetime.now(pytz.timezone('UTC'))
        self.updateContextFromData(data)
        self.next_url = canonical_url(context)


class DistributionMirrorEditView(LaunchpadEditFormView):

    schema = IDistributionMirror
    field_names = ["name", "displayname", "description", "whiteboard",
                   "http_base_url", "ftp_base_url", "rsync_base_url", "speed",
                   "country", "content", "official_candidate"]
    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Edit mirror %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action(_("Save"), name="save")
    def action_save(self, action, data):
        self.updateContextFromData(data)
        self.next_url = canonical_url(self.context)


class DistributionMirrorReassignmentView(ObjectReassignmentView):

    @property
    def contextName(self):
        return self.context.title


class DistributionMirrorProberLogView(DistributionMirrorView):
    """View class for prober logs."""

    @property
    def page_title(self):
        """The HTML page title."""
        return '%s mirror prober logs' % self.context.title
