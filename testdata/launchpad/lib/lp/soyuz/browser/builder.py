# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for builders."""

__metaclass__ = type

__all__ = [
    'BuilderFacets',
    'BuilderOverviewMenu',
    'BuilderNavigation',
    'BuilderSetAddView',
    'BuilderSetBreadcrumb',
    'BuilderSetFacets',
    'BuilderSetOverviewMenu',
    'BuilderSetNavigation',
    'BuilderSetView',
    'BuilderView',
    ]

import operator

from lazr.restful.utils import smartquote
from zope.component import getUtility
from zope.event import notify
from zope.formlib.widgets import TextWidget
from zope.lifecycleevent import ObjectCreatedEvent

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.widgets.owner import HiddenUserWidget
from lp.buildmaster.interfaces.builder import (
    IBuilder,
    IBuilderSet,
    )
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.services.database.interfaces import IStore
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    enabled_with_permission,
    GetitemNavigation,
    LaunchpadView,
    Link,
    Navigation,
    StandardLaunchpadFacets,
    stepthrough,
    )
from lp.services.webapp.batching import StormRangeFactory
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.soyuz.browser.build import (
    BuildNavigationMixin,
    BuildRecordsView,
    )


class BuilderSetNavigation(GetitemNavigation, BuildNavigationMixin):
    """Navigation methods for IBuilderSet."""
    usedfor = IBuilderSet

    @stepthrough('+build')
    def traverse_build(self, name):
        build = super(BuilderSetNavigation, self).traverse_build(name)
        if build is None:
            return None
        else:
            return self.redirectSubTree(canonical_url(build))


class BuilderSetBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `IBuilderSet`."""
    text = 'Build Farm'


class BuilderNavigation(Navigation):
    """Navigation methods for IBuilder."""
    usedfor = IBuilder


class BuilderSetFacets(StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an IBuilderSet."""
    enable_only = ['overview']

    usedfor = IBuilderSet


class BuilderFacets(StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an IBuilder."""
    enable_only = ['overview']

    usedfor = IBuilder


class BuilderSetOverviewMenu(ApplicationMenu):
    """Overview Menu for IBuilderSet."""
    usedfor = IBuilderSet
    facet = 'overview'
    links = ['add']

    @enabled_with_permission('launchpad.Admin')
    def add(self):
        text = 'Register a new build machine'
        return Link('+new', text, icon='add')


class BuilderOverviewMenu(ApplicationMenu):
    """Overview Menu for IBuilder."""
    usedfor = IBuilder
    facet = 'overview'
    links = ['history', 'edit', 'mode']

    def history(self):
        text = 'View full history'
        return Link('+history', text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def mode(self):
        text = 'Change mode'
        return Link('+mode', text, icon='edit')


class BuilderSetView(LaunchpadView):
    """Default BuilderSet view class."""

    @property
    def label(self):
        return self.context.title

    @property
    def page_title(self):
        return self.label

    @cachedproperty
    def builders(self):
        """All active builders"""
        builders = list(self.context.getBuilders())

        # Populate builders' currentjob cachedproperty.
        queues = IStore(BuildQueue).find(
            BuildQueue,
            BuildQueue.builderID.is_in(
                builder.id for builder in builders))
        queue_builders = dict(
            (queue.builderID, queue) for queue in queues)
        for builder in builders:
            cache = get_property_cache(builder)
            cache.currentjob = queue_builders.get(builder.id, None)
        # Prefetch the jobs' data.
        BuildQueue.preloadSpecificJobData(queues)

        return builders

    @property
    def number_of_registered_builders(self):
        return len(self.builders)

    @property
    def number_of_available_builders(self):
        return len([b for b in self.builders if b.builderok])

    @property
    def number_of_disabled_builders(self):
        return len([b for b in self.builders if not b.builderok])

    @property
    def number_of_building_builders(self):
        return len([b for b in self.builders if b.currentjob is not None])

    @cachedproperty
    def build_queue_sizes(self):
        """Return the build queue sizes for all processors."""
        builderset = getUtility(IBuilderSet)
        return builderset.getBuildQueueSizes()

    @property
    def ppa_builders(self):
        """Return a BuilderCategory object for PPA builders."""
        builder_category = BuilderCategory(
            'PPA build status', virtualized=True)
        builder_category.groupBuilders(self.builders, self.build_queue_sizes)
        return builder_category

    @property
    def other_builders(self):
        """Return a BuilderCategory object for PPA builders."""
        builder_category = BuilderCategory(
            'Official distributions build status', virtualized=False)
        builder_category.groupBuilders(self.builders, self.build_queue_sizes)
        return builder_category


class BuilderGroup:
    """A group of builders for the processor.

    Also stores the corresponding 'queue_size', the number of pending jobs
    in this context.
    """
    def __init__(self, processor_name, queue_size, duration, builders):
        self.processor_name = processor_name
        self.queue_size = queue_size
        self.number_of_available_builders = len(
            [b for b in builders if b.builderok])
        if duration and self.number_of_available_builders:
            self.duration = duration / self.number_of_available_builders
        else:
            self.duration = duration


class BuilderCategory:
    """A category of builders.

    A collection of BuilderGroups as 'PPA builders' and 'Other builders'.
    """
    def __init__(self, title, virtualized):
        self.title = title
        self.virtualized = virtualized
        self._builder_groups = []

    @property
    def groups(self):
        """Return a list of BuilderGroups ordered by 'processor_name'."""
        return sorted(self._builder_groups,
                      key=operator.attrgetter('processor_name'))

    def groupBuilders(self, all_builders, build_queue_sizes):
        """Group the given builders as a collection of Buildergroups.

        A BuilderGroup will be initialized for each processor.
        """
        builders = [builder for builder in all_builders
                    if builder.virtualized is self.virtualized]

        grouped_builders = {}
        for builder in builders:
            if builder.processor in grouped_builders:
                grouped_builders[builder.processor].append(builder)
            else:
                grouped_builders[builder.processor] = [builder]

        for processor, builders in grouped_builders.iteritems():
            virt_str = 'virt' if self.virtualized else 'nonvirt'
            queue_size, duration = build_queue_sizes[virt_str].get(
                processor.name, (0, None))
            builder_group = BuilderGroup(
                processor.name, queue_size, duration,
                sorted(builders, key=operator.attrgetter('title')))
            self._builder_groups.append(builder_group)


class BuilderView(LaunchpadView):
    """Default Builder view class

    Implements useful actions for the page template.
    """

    @property
    def current_build_duration(self):
        if self.context.currentjob is None:
            return None
        else:
            return self.context.currentjob.current_build_duration

    @property
    def page_title(self):
        """Return a relevant page title for this view."""
        return smartquote(
            'Builder "%s"' % self.context.title)

    @property
    def toggle_mode_text(self):
        """Return the text to use on the toggle mode button."""
        if self.context.manual:
            return "Switch to auto-mode"
        else:
            return "Switch to manual-mode"


class BuilderHistoryView(BuildRecordsView):
    """This class exists only to override the page_title."""

    page_title = 'Build history'
    binary_only = False
    range_factory = StormRangeFactory

    @property
    def label(self):
        return smartquote(
            'Build history for "%s"' % self.context.title)

    @property
    def default_build_state(self):
        """Present all jobs by default."""
        return None

    @property
    def show_builder_info(self):
        """Hide Builder info, see BuildRecordsView for further details"""
        return False


class BuilderSetAddView(LaunchpadFormView):
    """View class for adding new Builders."""

    schema = IBuilder

    label = "Register a new build machine"

    field_names = [
        'name', 'title', 'processor', 'url', 'active', 'virtualized',
        'vm_host', 'owner'
        ]

    custom_widget('owner', HiddenUserWidget)
    custom_widget('url', TextWidget, displayWidth=30)
    custom_widget('vm_host', TextWidget, displayWidth=30)

    @action(_('Register builder'), name='register')
    def register_action(self, action, data):
        """Register a new builder."""
        builder = getUtility(IBuilderSet).new(
            processor=data.get('processor'),
            url=data.get('url'),
            name=data.get('name'),
            title=data.get('title'),
            owner=data.get('owner'),
            active=data.get('active'),
            virtualized=data.get('virtualized'),
            vm_host=data.get('vm_host'),
            )
        notify(ObjectCreatedEvent(builder))
        self.next_url = canonical_url(builder)

    @property
    def page_title(self):
        """Return a relevant page title for this view."""
        return self.label

    @property
    def cancel_url(self):
        """Canceling the add action should go back to the build farm."""
        return canonical_url(self.context)


class BuilderEditView(LaunchpadEditFormView):
    """View class for changing builder details."""

    schema = IBuilder

    field_names = [
        'name', 'title', 'processor', 'url', 'manual', 'owner',
        'virtualized', 'builderok', 'failnotes', 'vm_host', 'active',
        ]

    @action(_('Change'), name='update')
    def change_details(self, action, data):
        """Update the builder with the data from the form."""
        # notify_modified is set False here because it uses
        # lazr.lifecycle.snapshot to store the state of the object
        # before and after modification.  This is dangerous for the
        # builder model class because it causes some properties to be
        # queried that try and communicate with the slave, which cannot
        # be done from the webapp (it's generally firewalled).  We could
        # prevent snapshots for individual properties by defining the
        # interface properties with doNotSnapshot() but this doesn't
        # guard against future properties being created.
        builder_was_modified = self.updateContextFromData(
            data, notify_modified=False)

        if builder_was_modified:
            notification = 'The builder "%s" was updated successfully.' % (
                self.context.title)
            self.request.response.addNotification(notification)

        return builder_was_modified

    @property
    def next_url(self):
        """Redirect back to the builder-index page."""
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        """Return the url to which we want to go to if user cancels."""
        return self.next_url

    @property
    def page_title(self):
        """Return a relevant page title for this view."""
        return smartquote(
            'Change details for builder "%s"' % self.context.title)

    @property
    def label(self):
        """The form label should be the same as the pagetitle."""
        return self.page_title
