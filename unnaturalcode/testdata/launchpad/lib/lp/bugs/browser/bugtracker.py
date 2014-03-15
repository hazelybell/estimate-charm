# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug tracker views."""

__metaclass__ = type

__all__ = [
    'BugTrackerAddView',
    'BugTrackerBreadcrumb',
    'BugTrackerComponentGroupNavigation',
    'BugTrackerEditView',
    'BugTrackerEditComponentView',
    'BugTrackerNavigation',
    'BugTrackerNavigationMenu',
    'BugTrackerSetBreadcrumb',
    'BugTrackerSetContextMenu',
    'BugTrackerSetNavigation',
    'BugTrackerSetView',
    'BugTrackerView',
    'RemoteBug',
    ]

from itertools import chain

from lazr.restful.utils import smartquote
from zope.component import getUtility
from zope.formlib import form
from zope.formlib.widgets import TextAreaWidget
from zope.interface import implements
from zope.schema import Choice
from zope.schema.vocabulary import SimpleVocabulary

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators import LaunchpadValidationError
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.app.widgets.textwidgets import DelimitedListWidget
from lp.bugs.browser.widgets.bugtask import UbuntuSourcePackageNameWidget
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTracker,
    IBugTrackerComponent,
    IBugTrackerComponentGroup,
    IBugTrackerSet,
    IRemoteBug,
    )
from lp.services.database.sqlbase import flush_database_updates
from lp.services.helpers import (
    english_list,
    shortlist,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    GetitemNavigation,
    LaunchpadView,
    Link,
    Navigation,
    redirection,
    stepthrough,
    structured,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import (
    ActiveBatchNavigator,
    BatchNavigator,
    InactiveBatchNavigator,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.menu import NavigationMenu

# A set of bug tracker types for which there can only ever be one bug
# tracker.
SINGLE_INSTANCE_TRACKERS = (
    BugTrackerType.DEBBUGS,
    )

# A set of bug tracker types that we should not allow direct creation
# of.
NO_DIRECT_CREATION_TRACKERS = (
    SINGLE_INSTANCE_TRACKERS + (
        BugTrackerType.EMAILADDRESS,
        )
    )


class BugTrackerSetNavigation(GetitemNavigation):

    usedfor = IBugTrackerSet


class BugTrackerSetContextMenu(ContextMenu):

    usedfor = IBugTrackerSet

    links = ['newbugtracker']

    def newbugtracker(self):
        text = 'Register another bug tracker'
        return Link('+newbugtracker', text, icon='add')


class BugTrackerAddView(LaunchpadFormView):

    page_title = u"Register an external bug tracker"
    schema = IBugTracker
    label = page_title
    field_names = ['bugtrackertype', 'name', 'title', 'baseurl', 'summary',
                   'contactdetails']

    def setUpWidgets(self, context=None):
        # We only show those bug tracker types for which there can be
        # multiple instances in the bugtrackertype Choice widget.
        vocab_items = [
            item for item in BugTrackerType.items.items
                if item not in NO_DIRECT_CREATION_TRACKERS]
        fields = []
        for field_name in self.field_names:
            if field_name == 'bugtrackertype':
                fields.append(form.FormField(
                    Choice(__name__='bugtrackertype',
                           title=_('Bug Tracker Type'),
                           values=vocab_items,
                           default=BugTrackerType.BUGZILLA)))
            else:
                fields.append(self.form_fields[field_name])
        self.form_fields = form.Fields(*fields)
        super(BugTrackerAddView, self).setUpWidgets(context=context)

    @action(_('Add'), name='add')
    def add(self, action, data):
        """Create the IBugTracker."""
        btset = getUtility(IBugTrackerSet)
        bugtracker = btset.ensureBugTracker(
            name=data['name'],
            bugtrackertype=data['bugtrackertype'],
            title=data['title'],
            summary=data['summary'],
            baseurl=data['baseurl'],
            contactdetails=data['contactdetails'],
            owner=getUtility(ILaunchBag).user)
        self.next_url = canonical_url(bugtracker)

    @property
    def cancel_url(self):
        return canonical_url(self.context)


class BugTrackerSetView(LaunchpadView):
    """View for actions on the bugtracker index pages."""

    page_title = u"Bug trackers registered in Launchpad"
    pillar_limit = 3

    def initialize(self):
        # eager load related pillars. In future we should do this for
        # just the rendered trackers, and also use group by to get
        # bug watch counts per tracker. However the batching makes
        # the inefficiency tolerable for now. Robert Collins 20100919.
        self._pillar_cache = self.context.getPillarsForBugtrackers(
            list(self.context.getAllTrackers()), self.user)

    @property
    def inactive_tracker_count(self):
        return self.inactive_trackers.currentBatch().listlength

    @cachedproperty
    def active_trackers(self):
        results = self.context.getAllTrackers(active=True)
        navigator = ActiveBatchNavigator(results, self.request)
        navigator.setHeadings('tracker', 'trackers')
        return navigator

    @cachedproperty
    def inactive_trackers(self):
        results = self.context.getAllTrackers(active=False)
        navigator = InactiveBatchNavigator(results, self.request)
        navigator.setHeadings('tracker', 'trackers')
        return navigator

    def getPillarData(self, bugtracker):
        """Return dict of pillars and booleans indicating ellipsis.

        In more detail, the dictionary holds a list of products/projects
        and a boolean determining whether or not there we omitted
        pillars by truncating to pillar_limit.

        If no pillars are mapped to this bugtracker, returns {}.
        """
        if bugtracker not in self._pillar_cache:
            return {}
        pillars = self._pillar_cache[bugtracker]
        if len(pillars) > self.pillar_limit:
            has_more_pillars = True
        else:
            has_more_pillars = False
        return {
            'pillars': pillars[:self.pillar_limit],
            'has_more_pillars': has_more_pillars}


class BugTrackerView(LaunchpadView):

    usedfor = IBugTracker

    @property
    def page_title(self):
        return smartquote(
            u'The "%s" bug tracker in Launchpad' % self.context.title)

    def initialize(self):
        self.batchnav = BatchNavigator(self.context.watches, self.request)

    @property
    def related_projects(self):
        """Return all project groups and projects.

        This property was created for the Related projects portlet in
        the bug tracker's page.
        """
        pillars = chain(*self.context.getRelatedPillars(self.user))
        return shortlist([p for p in pillars if p.active], 100)

    @property
    def related_component_groups(self):
        """All component groups and components."""
        return self.context.getAllRemoteComponentGroups()


BUG_TRACKER_ACTIVE_VOCABULARY = SimpleVocabulary.fromItems(
    [('On', True), ('Off', False)])


class BugTrackerEditView(LaunchpadEditFormView):

    schema = IBugTracker

    custom_widget('summary', TextAreaWidget, width=30, height=5)
    custom_widget('aliases', DelimitedListWidget, height=3)
    custom_widget('active', LaunchpadRadioWidget, orientation='vertical')

    @property
    def page_title(self):
        return smartquote(
            u'Change details for the "%s" bug tracker' % self.context.title)

    @cachedproperty
    def field_names(self):
        field_names = [
            'name',
            'title',
            'bugtrackertype',
            'summary',
            'baseurl',
            'aliases',
            'contactdetails',
            ]

        # Members of the admin team can set the bug tracker's active
        # state.
        if check_permission("launchpad.Admin", self.user):
            field_names.append('active')

        return field_names

    def setUpFields(self):
        """Set up the fields for the bug tracker edit form.

        If the `active` field is to be displayed, remove the default
        Field and replace it with a Choice field for the sake of
        usability.

        See `LaunchpadFormView`.
        """
        super(BugTrackerEditView, self).setUpFields()

        # If we're displaying the 'active' field we need to swap it out
        # and replace it with a field that uses our custom vocabulary.
        if 'active' in self.field_names:
            active_field = Choice(
                __name__='active',
                title=_('Updates for this bug tracker are'),
                vocabulary=BUG_TRACKER_ACTIVE_VOCABULARY,
                required=True, default=self.context.active)

            self.form_fields = self.form_fields.omit('active')
            self.form_fields += form.Fields(active_field)

    def validate(self, data):
        # Normalise aliases to an empty list if it's None.
        if data.get('aliases') is None:
            data['aliases'] = []

        # If aliases has an error, unwrap the Dantean exception from
        # Zope so that we can tell the user something useful.
        if self.getFieldError('aliases'):
            # XXX: wgrant 2008-04-02 bug=210901: The error
            # messages may have already been escaped by
            # LaunchpadValidationError, so wrap them in structured() to
            # avoid double-escaping them. It's possible that non-LVEs
            # could also be escaped, but I can't think of any cases so
            # let's just escape them anyway.
            aliases_errors = self.widgets['aliases']._error.errors.args[0]
            maybe_structured_errors = [
                structured(error)
                if isinstance(error, LaunchpadValidationError) else error
                for error in aliases_errors]
            self.setFieldError('aliases', structured(
                    '<br />'.join(['%s'] * len(maybe_structured_errors)),
                    *maybe_structured_errors))

    @action('Change', name='change')
    def change_action(self, action, data):
        # If the baseurl is going to change, save the current baseurl
        # as an alias. Users attempting to use this URL, which is
        # presumably incorrect or out-of-date, will be captured.
        current_baseurl = self.context.baseurl
        requested_baseurl = data['baseurl']
        if requested_baseurl != current_baseurl:
            data['aliases'].append(current_baseurl)

        self.updateContextFromData(data)
        self.next_url = canonical_url(self.context)

    @cachedproperty
    def delete_not_possible_reasons(self):
        """A list of reasons why the context cannot be deleted.

        An empty list means that there are no reasons, so the delete
        can go ahead.
        """
        reasons = []
        celebrities = getUtility(ILaunchpadCelebrities)

        # We go through all of the conditions why the bug tracker
        # can't be deleted, and record reasons for all of them. We do
        # this so that users can discover the logic behind the
        # decision, and try something else, seek help, or give up as
        # appropriate. Just showing the first problem would stop users
        # from being able to help themselves.

        # Check that no products or projects use this bugtracker.
        pillars = (
            getUtility(IBugTrackerSet).getPillarsForBugtrackers(
                [self.context]).get(self.context, []))
        if len(pillars) > 0:
            reasons.append(
                'This is the bug tracker for %s.' % english_list(
                    sorted(pillar.title for pillar in pillars)))

        # Only admins and registry experts can delete bug watches en
        # masse.
        if not self.context.watches.is_empty():
            admin_teams = [celebrities.admin, celebrities.registry_experts]
            for team in admin_teams:
                if self.user.inTeam(team):
                    break
            else:
                reasons.append(
                    'There are linked bug watches and only members of %s '
                    'can delete them en masse.' % english_list(
                        sorted(team.title for team in admin_teams)))

        # Bugtrackers with imported messages cannot be deleted.
        if not self.context.imported_bug_messages.is_empty():
            reasons.append(
                'Bug comments have been imported via this bug tracker.')

        # If the bugtracker is a celebrity then we protect it from
        # deletion.
        celebrities_set = set(
            getattr(celebrities, name)
            for name in ILaunchpadCelebrities.names())
        if self.context in celebrities_set:
            reasons.append(
                'This bug tracker is protected from deletion.')

        return reasons

    def delete_condition(self, action):
        return len(self.delete_not_possible_reasons) == 0

    @action('Delete', name='delete', condition=delete_condition)
    def delete_action(self, action, data):
        # First unlink bug watches from all bugtasks, flush updates,
        # then delete the watches themselves.
        for watch in self.context.watches:
            for bugtask in watch.bugtasks:
                if len(bugtask.bug.bugtasks) < 2:
                    raise AssertionError(
                        'There should be more than one bugtask for a bug '
                        'when one of them is linked to the original bug via '
                        'a bug watch.')
                bugtask.bugwatch = None
        flush_database_updates()
        for watch in self.context.watches:
            watch.destroySelf()

        # Now delete the aliases and the bug tracker itself.
        self.context.aliases = []
        self.context.destroySelf()

        # Hey, it worked! Tell the user.
        self.request.response.addInfoNotification(
            '%s has been deleted.' % (self.context.title,))

        # Go back to the bug tracker listing.
        self.next_url = canonical_url(getUtility(IBugTrackerSet))

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def reschedule_action_condition(self, action):
        """Return True if the user can see the reschedule action."""
        user_can_reset_watches = check_permission(
            "launchpad.Admin", self.context)
        return user_can_reset_watches and not self.context.watches.is_empty()

    @action(
        'Reschedule all watches', name='reschedule',
        condition=reschedule_action_condition)
    def rescheduleAction(self, action, data):
        """Reschedule all the watches for the bugtracker."""
        self.context.resetWatches()
        self.request.response.addInfoNotification(
            "All bug watches on %s have been rescheduled." %
            self.context.title)
        self.next_url = canonical_url(self.context)


class BugTrackerNavigation(Navigation):

    usedfor = IBugTracker

    def traverse(self, remotebug):
        bugs = self.context.getBugsWatching(remotebug)
        if len(bugs) == 0:
            # no bugs watching => not found
            return None
        elif len(bugs) == 1:
            # one bug watching => redirect to that bug
            return redirection(canonical_url(bugs[0]))
        else:
            # else list the watching bugs
            return RemoteBug(self.context, remotebug, bugs)

    @stepthrough("+components")
    def component_groups(self, name_or_id):
        """Navigate by id (component group name should work too)"""
        return self.context.getRemoteComponentGroup(name_or_id)


class BugTrackerEditComponentView(LaunchpadEditFormView):
    """Provides editing form for setting source packages for components.

    This class assumes that bug tracker components are always
    linked to source packages in the Ubuntu distribution.
    """
    schema = IBugTrackerComponent
    custom_widget('sourcepackagename', UbuntuSourcePackageNameWidget)
    field_names = ['sourcepackagename']
    page_title = 'Link component'

    @property
    def label(self):
        return (
            'Link a distribution source package to %s component' %
            self.context.name)

    @property
    def initial_values(self):
        """See `LaunchpadFormView.`"""
        field_values = dict(sourcepackagename='')
        dsp = self.context.distro_source_package
        if dsp is not None:
            field_values['sourcepackagename'] = dsp.name
        return field_values

    @property
    def next_url(self):
        return canonical_url(self.context.component_group.bug_tracker)

    cancel_url = next_url

    def updateContextFromData(self, data, context=None):
        """Link component to specified distro source package.

        Get the user-provided source package name from the form widget,
        look it up in Ubuntu to retrieve the distro_source_package
        object, and link it to this component.
        """
        sourcepackagename = data['sourcepackagename']
        distribution = self.widgets['sourcepackagename'].getDistribution()
        dsp = distribution.getSourcePackage(sourcepackagename)
        bug_tracker = self.context.component_group.bug_tracker
        # Has this source package already been assigned to a component?
        component = bug_tracker.getRemoteComponentForDistroSourcePackageName(
            distribution, sourcepackagename)
        if component is not None:
            self.request.response.addNotification(
                "The %s source package is already linked to %s:%s in %s." % (
                    sourcepackagename.name,
                    component.component_group.name,
                    component.name, distribution.name))
            return
        # The submitted component can be linked to the distro source package.
        component = context or self.context
        component.distro_source_package = dsp
        if sourcepackagename is None:
            self.request.response.addNotification(
                "%s:%s is now unlinked." % (
                    component.component_group.name, component.name))
        else:
            self.request.response.addNotification(
                "%s:%s is now linked to the %s source package in %s." % (
                    component.component_group.name, component.name,
                    sourcepackagename.name, distribution.name))

    @action('Save Changes', name='save')
    def save_action(self, action, data):
        """Update the component with the form data."""
        self.updateContextFromData(data)


class BugTrackerComponentGroupNavigation(Navigation):

    usedfor = IBugTrackerComponentGroup

    def traverse(self, id):
        return self.context.getComponent(id)


class BugTrackerSetBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for the `IBugTrackerSet`."""

    rootsite = None

    @property
    def text(self):
        return u"Bug trackers"


class BugTrackerBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `IBugTracker`."""

    rootsite = None

    @property
    def text(self):
        return self.context.title


class RemoteBug:
    """Represents a bug in a remote bug tracker."""

    implements(IRemoteBug)

    def __init__(self, bugtracker, remotebug, bugs):
        self.bugtracker = bugtracker
        self.remotebug = remotebug
        self.bugs = bugs

    @property
    def title(self):
        return 'Remote Bug #%s in %s' % (self.remotebug,
                                         self.bugtracker.title)


class RemoteBugView(LaunchpadView):
    """View a remove bug."""

    @property
    def page_title(self):
        return self.context.title


class BugTrackerNavigationMenu(NavigationMenu):

    usedfor = BugTrackerView
    facet = 'bugs'
    links = ['edit']

    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')
