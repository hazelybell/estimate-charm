# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'expose_enum_to_js',
    'expose_structural_subscription_data_to_js',
    'expose_user_administered_teams_to_js',
    'expose_user_subscriptions_to_js',
    'StructuralSubscriptionMenuMixin',
    'StructuralSubscriptionTargetTraversalMixin',
    'StructuralSubscriptionView',
    'StructuralSubscribersPortletView',
    ]

from operator import (
    attrgetter,
    itemgetter,
    )

from lazr.restful.interfaces import (
    IJSONRequestCache,
    IWebServiceClientRequest,
    )
from zope.component import getUtility
from zope.formlib import form
from zope.schema import (
    Choice,
    List,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.traversing.browser import absoluteURL

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.enums import (
    InformationType,
    ServiceUsage,
    )
from lp.app.widgets.itemswidgets import LabeledMultiCheckBoxWidget
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscription,
    IStructuralSubscriptionForm,
    IStructuralSubscriptionTarget,
    IStructuralSubscriptionTargetHelper,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.milestone import IProjectGroupMilestone
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp.authorization import (
    check_permission,
    precache_permission_for_objects,
    )
from lp.services.webapp.interaction import get_current_principal
from lp.services.webapp.interfaces import NoCanonicalUrl
from lp.services.webapp.menu import (
    enabled_with_permission,
    Link,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    Navigation,
    stepthrough,
    )


class StructuralSubscriptionNavigation(Navigation):

    usedfor = IStructuralSubscription

    @stepthrough("+filter")
    def bug_filter(self, filter_id):
        bug_filter_id = int(filter_id)
        for bug_filter in self.context.bug_filters:
            if bug_filter.id == bug_filter_id:
                return bug_filter
        return None


class StructuralSubscriptionView(LaunchpadFormView):

    """View class for structural subscriptions."""

    schema = IStructuralSubscriptionForm

    custom_widget('subscriptions_team', LabeledMultiCheckBoxWidget)
    custom_widget('remove_other_subscriptions', LabeledMultiCheckBoxWidget)

    page_title = 'Subscribe'

    @property
    def label(self):
        return 'Subscribe to Bugs in %s' % self.context.title

    @property
    def next_url(self):
        return canonical_url(self.context)

    def setUpFields(self):
        """See LaunchpadFormView."""
        LaunchpadFormView.setUpFields(self)
        team_subscriptions = self._createTeamSubscriptionsField()
        if team_subscriptions:
            self.form_fields += form.Fields(team_subscriptions)
        if self.userIsDriver():
            add_other = form.Fields(self._createAddOtherSubscriptionsField())
            self.form_fields += add_other
            remove_other = self._createRemoveOtherSubscriptionsField()
            if remove_other:
                self.form_fields += form.Fields(remove_other)

    def _createTeamSubscriptionsField(self):
        """Create field with a list of the teams the user is a member of.

        Return a FormField instance, if the user is a member of at least
        one team, else return None.
        """
        teams = self.user_teams
        if not teams:
            return None
        teams.sort(key=attrgetter('displayname'))
        terms = [
            SimpleTerm(team, team.name, team.displayname)
            for team in teams]
        team_vocabulary = SimpleVocabulary(terms)
        team_subscriptions_field = List(
            __name__='subscriptions_team',
            title=u'Team subscriptions',
            description=(u'You can subscribe the teams of '
                          'which you are an administrator.'),
            value_type=Choice(vocabulary=team_vocabulary),
            required=False)
        return form.FormField(team_subscriptions_field)

    def _createRemoveOtherSubscriptionsField(self):
        """Create a field with a list of subscribers.

        Return a FormField instance, if subscriptions exist that can
        be removed, else return None.
        """
        teams = set(self.user_teams)
        other_subscriptions = set(
            subscription.subscriber
            for subscription
            in self.context.bug_subscriptions)

        # Teams and the current user have their own UI elements. Remove
        # them to avoid duplicates.
        other_subscriptions.difference_update(teams)
        other_subscriptions.discard(self.user)

        if not other_subscriptions:
            return None

        other_subscriptions = sorted(
            other_subscriptions, key=attrgetter('displayname'))

        terms = [
            SimpleTerm(subscriber, subscriber.name, subscriber.displayname)
            for subscriber in other_subscriptions]

        subscriptions_vocabulary = SimpleVocabulary(terms)
        other_subscriptions_field = List(
            __name__='remove_other_subscriptions',
            title=u'Unsubscribe',
            value_type=Choice(vocabulary=subscriptions_vocabulary),
            required=False)
        return form.FormField(other_subscriptions_field)

    def _createAddOtherSubscriptionsField(self):
        """Create a field for a new subscription."""
        new_subscription_field = Choice(
            __name__='new_subscription',
            title=u'Subscribe someone else',
            vocabulary='ValidPersonOrTeam',
            required=False)
        return form.FormField(new_subscription_field)

    @property
    def initial_values(self):
        """See `LaunchpadFormView`."""
        teams = set(self.user_teams)
        subscribed_teams = set(team
                               for team in teams
                               if self.isSubscribed(team))
        return {
            'subscribe_me': self.currentUserIsSubscribed(),
            'subscriptions_team': subscribed_teams,
            }

    def isSubscribed(self, person):
        """Is `person` subscribed to the context target?

        Returns True is the user is subscribed to bug notifications
        for the context target.
        """
        return self.context.getSubscription(person) is not None

    def currentUserIsSubscribed(self):
        """Return True, if the current user is subscribed."""
        return self.isSubscribed(self.user)

    def userCanAlter(self):
        if self.context.userCanAlterBugSubscription(self.user, self.user):
            return True

    @action(u'Save these changes', name='save')
    def save_action(self, action, data):
        """Process the subscriptions submitted by the user."""
        self._handleUserSubscription(data)
        self._handleTeamSubscriptions(data)
        self._handleDriverChanges(data)

    def _handleUserSubscription(self, data):
        """Process the subscription for the user."""
        target = self.context
        # addSubscription raises an exception if called for an already
        # subscribed person, and removeBugSubscription raises an exception
        # for a non-subscriber, hence call these methods only, if the
        # subscription status changed.
        is_subscribed = self.isSubscribed(self.user)
        subscribe = data['subscribe_me']
        if (not is_subscribed) and subscribe:
            target.addBugSubscription(self.user, self.user)
            self.request.response.addNotification(
                'You have subscribed to "%s". You will now receive an '
                'e-mail each time someone reports or changes one of '
                'its bugs.' % target.displayname)
        elif is_subscribed and not subscribe:
            target.removeBugSubscription(self.user, self.user)
            self.request.response.addNotification(
                'You have unsubscribed from "%s". You '
                'will no longer automatically receive e-mail about '
                'changes to its bugs.' % target.displayname)
        else:
            # The subscription status did not change: nothing to do.
            pass

    def _handleTeamSubscriptions(self, data):
        """Process subscriptions for teams."""
        form_selected_teams = data.get('subscriptions_team', None)
        if form_selected_teams is None:
            return

        target = self.context
        teams = set(self.user_teams)
        form_selected_teams = teams & set(form_selected_teams)
        subscriptions = set(
            team for team in teams if self.isSubscribed(team))

        for team in form_selected_teams - subscriptions:
            target.addBugSubscription(team, self.user)
            self.request.response.addNotification(
                'The %s team will now receive an e-mail each time '
                'someone reports or changes a public bug in "%s".' % (
                team.displayname, self.context.displayname))

        for team in subscriptions - form_selected_teams:
            target.removeBugSubscription(team, self.user)
            self.request.response.addNotification(
                'The %s team will no longer automatically receive '
                'e-mail about changes to public bugs in "%s".' % (
                    team.displayname, self.context.displayname))

    def _handleDriverChanges(self, data):
        """Process subscriptions for other persons."""
        if not self.userIsDriver():
            return

        target = self.context
        new_subscription = data['new_subscription']
        if new_subscription is not None:
            target.addBugSubscription(new_subscription, self.user)
            self.request.response.addNotification(
                '%s will now receive an e-mail each time someone '
                'reports or changes a public bug in "%s".' % (
                new_subscription.displayname,
                target.displayname))

        subscriptions_to_remove = data.get('remove_other_subscriptions', [])
        for subscription in subscriptions_to_remove:
            target.removeBugSubscription(subscription, self.user)
            self.request.response.addNotification(
                '%s will no longer automatically receive e-mail about '
                'public bugs in "%s".' % (
                    subscription.displayname, target.displayname))

    def userIsDriver(self):
        """Has the current user driver permissions?"""
        # We only want to look at this if the target is a
        # distribution source package, in order to maintain
        # compatibility with the obsolete bug contacts feature.
        if IDistributionSourcePackage.providedBy(self.context):
            return check_permission(
                "launchpad.Driver", self.context.distribution)
        else:
            return False

    @cachedproperty
    def user_teams(self):
        """Return the teams that the current user is an administrator of."""
        return list(self.user.getAdministratedTeams())

    @property
    def show_details_portlet(self):
        """Show details portlet?

        Returns `True` if the portlet details is available
        and should be shown for the context.
        """
        return IDistributionSourcePackage.providedBy(self.context)


class StructuralSubscriptionTargetTraversalMixin:
    """Mix-in class that provides +subscription/<SUBSCRIBER> traversal."""

    @stepthrough('+subscription')
    def traverse_structuralsubscription(self, name):
        """Traverses +subscription portions of URLs."""
        person = getUtility(IPersonSet).getByName(name)
        return self.context.getSubscription(person)


class StructuralSubscriptionMenuMixin:
    """Mix-in class providing the subscription add/edit menu link."""

    def _getSST(self):
        if IStructuralSubscriptionTarget.providedBy(self.context):
            sst = self.context
        else:
            # self.context is a view, and the target is its context
            sst = self.context.context
        return sst

    def subscribe(self):
        """The subscribe menu link.

        If the user, or any of the teams he's a member of, already has a
        subscription to the context, the link offer to edit the subscriptions
        and displays the edit icon. Otherwise, the link offers to subscribe
        and displays the add icon.
        """
        sst = self._getSST()

        if sst.userHasBugSubscriptions(self.user):
            text = 'Edit bug mail subscription'
            icon = 'edit'
        else:
            text = 'Subscribe to bug mail'
            icon = 'add'
        # ProjectGroup milestones aren't really structural subscription
        # targets as they're not real milestones, so you can't subscribe to
        # them.
        if (not IProjectGroupMilestone.providedBy(sst) and
            sst.userCanAlterBugSubscription(self.user, self.user)):
            enabled = True
        else:
            enabled = False

        return Link('+subscribe', text, icon=icon, enabled=enabled)

    @property
    def _enabled(self):
        """Should the link be enabled?

        True if the target uses Launchpad for bugs and the user can alter the
        bug subscriptions.
        """
        sst = self._getSST()
        # ProjectGroup milestones aren't really structural subscription
        # targets as they're not real milestones, so you can't subscribe to
        # them.
        if IProjectGroupMilestone.providedBy(sst):
            return False
        pillar = IStructuralSubscriptionTargetHelper(sst).pillar
        return (pillar.bug_tracking_usage == ServiceUsage.LAUNCHPAD and
                sst.userCanAlterBugSubscription(self.user, self.user))

    @enabled_with_permission('launchpad.AnyPerson')
    def subscribe_to_bug_mail(self):
        text = 'Subscribe to bug mail'
        # Clicks to this link will be intercepted by the on-page JavaScript,
        # but we want a link target for non-JS-enabled browsers.
        return Link('+subscribe', text, icon='add', hidden=True,
            enabled=self._enabled)

    @enabled_with_permission('launchpad.AnyPerson')
    def edit_bug_mail(self):
        text = 'Edit bug mail'
        return Link('+subscriptions', text, icon='edit', site='bugs',
                    enabled=self._enabled)


def expose_structural_subscription_data_to_js(context, request,
                                              user, subscriptions=None):
    """Expose all of the data for a structural subscription to JavaScript."""
    expose_user_administered_teams_to_js(request, user, context)
    expose_enum_to_js(request, BugTaskImportance, 'importances')
    expose_enum_to_js(request, BugTaskStatus, 'statuses')
    expose_enum_to_js(request, InformationType, 'information_types')
    if subscriptions is None:
        try:
            # No subscriptions, which means we are on a target
            # subscriptions page. Let's at least provide target details.
            target_info = {}
            target_info['title'] = context.title
            target_info['url'] = canonical_url(context, rootsite='mainsite')
            IJSONRequestCache(request).objects['target_info'] = target_info
        except NoCanonicalUrl:
            # We export nothing if the target implements no canonical URL.
            pass
    else:
        expose_user_subscriptions_to_js(user, subscriptions, request)


def expose_enum_to_js(request, enum, name):
    """Make a list of enum titles and value available to JavaScript."""
    IJSONRequestCache(request).objects[name] = [item.title for item in enum]


def expose_user_administered_teams_to_js(request, user, context,
        absoluteURL=absoluteURL):
    """Make the list of teams the user administers available to JavaScript."""
    # XXX: Robert Collins workaround multiple calls making this cause
    # timeouts: see bug 788510.
    objects = IJSONRequestCache(request).objects
    if 'administratedTeams' in objects:
        return
    info = []
    api_request = IWebServiceClientRequest(request)
    is_distro = IDistribution.providedBy(context)
    if is_distro:
        # If the context is a distro AND a bug supervisor is set then we only
        # allow subscriptions from members of the bug supervisor team.
        bug_supervisor = context.bug_supervisor
    else:
        bug_supervisor = None
    if user is not None:
        administrated_teams = set(user.administrated_teams)
        if administrated_teams:
            # Get this only if we need to.
            membership = set(user.teams_participated_in)
            # Only consider teams the user is both in and administers:
            #  If the user is not a member of the team itself, then
            # skip it, because structural subscriptions and their
            # filters can only be edited by the subscriber.
            # This can happen if the user is an owner but not a member.
            administers_and_in = membership.intersection(administrated_teams)
            list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
                [team.id for team in administers_and_in],
                need_preferred_email=True))

            # If the requester is the user, they're at least an admin in
            # all of these teams. Precache launchpad.(Limited)View so we
            # can see the necessary attributes.
            current_user = IPerson(get_current_principal(), None)
            if current_user is not None and user == current_user:
                for perm in ('launchpad.View', 'launchpad.LimitedView'):
                    precache_permission_for_objects(
                        None, perm, administers_and_in)

            for team in administers_and_in:
                if (bug_supervisor is not None and
                    not team.inTeam(bug_supervisor)):
                    continue
                info.append({
                    'has_preferredemail': team.preferredemail is not None,
                    'link': absoluteURL(team, api_request),
                    'title': team.title,
                    'url': canonical_url(team),
                })
    objects['administratedTeams'] = info


def expose_user_subscriptions_to_js(user, subscriptions, request):
    """Make the user's subscriptions available to JavaScript."""
    api_request = IWebServiceClientRequest(request)
    info = {}
    if user is None:
        administered_teams = []
    else:
        administered_teams = user.administrated_teams

    for subscription in subscriptions:
        target = subscription.target
        record = info.get(target)
        if record is None:
            record = dict(target_title=target.title,
                          target_url=canonical_url(
                            target, rootsite='mainsite'),
                          filters=[])
            info[target] = record
        subscriber = subscription.subscriber
        for filter in subscription.bug_filters:
            is_team = subscriber.is_team
            user_is_team_admin = (
                is_team and subscriber in administered_teams)
            team_has_contact_address = (
                is_team and subscriber.preferredemail is not None)
            mailing_list = subscriber.mailing_list
            user_is_on_team_mailing_list = (
                team_has_contact_address and
                mailing_list is not None and
                mailing_list.is_usable and
                mailing_list.getSubscription(subscriber) is not None)
            record['filters'].append(dict(
                filter=filter,
                subscriber_link=absoluteURL(subscriber, api_request),
                subscriber_url=canonical_url(
                    subscriber, rootsite='mainsite'),
                target_bugs_url=canonical_url(
                    target, rootsite='bugs'),
                subscriber_title=subscriber.title,
                subscriber_is_team=is_team,
                user_is_team_admin=user_is_team_admin,
                team_has_contact_address=team_has_contact_address,
                user_is_on_team_mailing_list=user_is_on_team_mailing_list,
                can_mute=filter.isMuteAllowed(user),
                is_muted=filter.muted(user) is not None,
                target_title=target.title))
    info = info.values()
    info.sort(key=itemgetter('target_url'))
    IJSONRequestCache(request).objects['subscription_info'] = info


class StructuralSubscribersPortletView(LaunchpadView):
    """A simple view for displaying the subscribers portlet."""

    @property
    def target_label(self):
        """Return the target label for the portlet."""
        if IDistributionSourcePackage.providedBy(self.context):
            return "To all bugs in %s" % self.context.displayname
        else:
            return "To all %s bugs" % self.context.title

    @property
    def parent_target_label(self):
        """Return the target label for the portlet."""
        return (
            "To all %s bugs" % self.context.parent_subscription_target.title)
