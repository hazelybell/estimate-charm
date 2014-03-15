# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IBug related view classes."""

__metaclass__ = type

__all__ = [
    'BugActivity',
    'BugContextMenu',
    'BugEditView',
    'BugFacets',
    'BugInformationTypePortletView',
    'BugMarkAsAffectingUserView',
    'BugMarkAsDuplicateView',
    'BugNavigation',
    'BugSecrecyEditView',
    'BugSetNavigation',
    'BugSubscriptionPortletDetails',
    'BugTextView',
    'BugURL',
    'BugView',
    'BugViewMixin',
    'BugWithoutContextView',
    'DeprecatedAssignedBugsView',
    'MaloneView',
    ]

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
import re

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
from lazr.restful import (
    EntryResource,
    ResourceJSONEncoder,
    )
from lazr.restful.interface import copy_field
from lazr.restful.interfaces import IJSONRequestCache
from simplejson import dumps
from zope import formlib
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.event import notify
from zope.formlib.widgets import TextWidget
from zope.interface import (
    implements,
    Interface,
    providedBy,
    )
from zope.publisher.defaultview import getDefaultViewName
from zope.schema import (
    Bool,
    Choice,
    )
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp import _
from lp.app.browser.informationtype import InformationTypePortletMixin
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.app.errors import NotFoundError
from lp.app.interfaces.services import IService
from lp.app.vocabularies import InformationTypeVocabulary
from lp.app.widgets.itemswidgets import LaunchpadRadioWidgetWithDescription
from lp.app.widgets.product import GhostCheckBoxWidget
from lp.app.widgets.project import ProjectScopeWidget
from lp.bugs.browser.bugsubscription import BugPortletSubscribersWithDetails
from lp.bugs.browser.widgets.bug import BugTagsWidget
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bug import (
    IBug,
    IBugSet,
    )
from lp.bugs.interfaces.bugattachment import (
    BugAttachmentType,
    IBugAttachmentSet,
    )
from lp.bugs.interfaces.bugnomination import IBugNominationSet
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTask,
    )
from lp.bugs.interfaces.bugtasksearch import (
    BugTaskSearchParams,
    IFrontPageBugTaskSearch,
    )
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.bugs.interfaces.cve import ICveSet
from lp.bugs.mail.bugnotificationbuilder import format_rfc2822_date
from lp.bugs.model.personsubscriptioninfo import PersonSubscriptions
from lp.bugs.model.structuralsubscription import (
    get_structural_subscriptions_for_bug,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.services.fields import DuplicateBug
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.mail.mailwrapper import MailWrapper
from lp.services.propertycache import cachedproperty
from lp.services.searchbuilder import (
    any,
    not_equals,
    )
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    LaunchpadView,
    Link,
    Navigation,
    StandardLaunchpadFacets,
    stepthrough,
    structured,
    )
from lp.services.webapp.authorization import (
    check_permission,
    precache_permission_for_objects,
    )
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    ILaunchBag,
    )
from lp.services.webapp.publisher import RedirectionView


class BugNavigation(Navigation):
    """Navigation for the `IBug`."""
    # It would be easier, since there is no per-bug sequence for a BugWatch
    # and we have to leak the BugWatch.id anyway, to hang bugwatches off a
    # global /bugwatchs/nnnn

    # However, we want in future to have them at /bugs/nnn/+watch/p where p
    # is not the BugWatch.id but instead a per-bug sequence number (1, 2,
    # 3...) for the 1st, 2nd and 3rd watches added for this bug,
    # respectively. So we are going ahead and hanging this off the bug to
    # which it belongs as a first step towards getting the basic URL schema
    # correct.

    usedfor = IBug

    @stepthrough('+watch')
    def traverse_watches(self, name):
        """Retrieve a BugWatch by name."""
        if name.isdigit():
            # in future this should look up by (bug.id, watch.seqnum)
            return getUtility(IBugWatchSet).get(int(name))

    @stepthrough('+subscription')
    def traverse_subscriptions(self, person_name):
        """Retrieve a BugSubscription by person name."""
        for subscription in self.context.subscriptions:
            if subscription.person.name == person_name:
                return subscription

    @stepthrough('attachments')
    def traverse_attachments(self, name):
        """Retrieve a BugAttachment by ID.

        If an attachment is found, redirect to its canonical URL.
        """
        if name.isdigit():
            attachment = getUtility(IBugAttachmentSet)[name]
            if attachment is not None and attachment.bug == self.context:
                return self.redirectSubTree(
                    canonical_url(attachment), status=301)

    @stepthrough('+attachment')
    def traverse_attachment(self, name):
        """Retrieve a BugAttachment by ID.

        Only return a attachment if it is related to this bug.
        """
        if name.isdigit():
            attachment = getUtility(IBugAttachmentSet)[name]
            if attachment is not None and attachment.bug == self.context:
                return attachment

    @stepthrough('nominations')
    def traverse_nominations(self, nomination_id):
        """Traverse to a nomination by id."""
        if nomination_id.isdigit():
            try:
                return getUtility(IBugNominationSet).get(nomination_id)
            except NotFoundError:
                return None


class BugFacets(StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an `IBug`.

    However, we never show this, but it does apply to things like
    bug nominations, by 'acquisition'.
    """

    usedfor = IBug

    enable_only = []


class BugSetNavigation(Navigation):
    """Navigation for the IBugSet."""
    usedfor = IBugSet

    @stepthrough('+text')
    def text(self, name):
        """Retrieve a bug by name."""
        try:
            return getUtility(IBugSet).getByNameOrID(name)
        except (NotFoundError, ValueError):
            return None


class BugContextMenu(ContextMenu):
    """Context menu of actions that can be performed upon a Bug."""
    usedfor = IBug
    links = [
        'editdescription', 'markduplicate', 'visibility', 'addupstream',
        'adddistro', 'subscription', 'addsubscriber', 'editsubscriptions',
        'addcomment', 'nominate', 'addbranch', 'linktocve', 'unlinkcve',
        'createquestion', 'mute_subscription', 'removequestion',
        'activitylog', 'affectsmetoo']

    def __init__(self, context):
        # Always force the context to be the current bugtask, so that we don't
        # have to duplicate menu code.
        ContextMenu.__init__(self, getUtility(ILaunchBag).bugtask)

    @cachedproperty
    def editdescription(self):
        """Return the 'Edit description/tags' Link."""
        text = 'Update description / tags'
        return Link('+edit', text, icon='edit')

    def visibility(self):
        """Return the 'Set privacy/security' Link."""
        text = 'Change privacy/security'
        return Link('+secrecy', text)

    def markduplicate(self):
        """Return the 'Mark as duplicate' Link."""
        return Link('+duplicate', 'Mark as duplicate')

    def addupstream(self):
        """Return the 'lso affects project' Link."""
        text = 'Also affects project'
        return Link('+choose-affected-product', text, icon='add')

    def adddistro(self):
        """Return the 'Also affects distribution' Link."""
        text = 'Also affects distribution'
        return Link('+distrotask', text, icon='add')

    def subscription(self):
        """Return the 'Subscribe/Unsubscribe' Link."""
        user = getUtility(ILaunchBag).user
        if user is None:
            text = 'Subscribe/Unsubscribe'
            icon = 'edit'
        elif user is not None and (
            self.context.bug.isSubscribed(user) or
            self.context.bug.isSubscribedToDupes(user)):
            if self.context.bug.isMuted(user):
                text = 'Subscribe'
                icon = 'add'
            else:
                text = 'Edit subscription'
                icon = 'edit'
        else:
            text = 'Subscribe'
            icon = 'add'
        return Link('+subscribe', text, icon=icon, summary=(
                'When you are subscribed, Launchpad will email you each time '
                'this bug changes'))

    def addsubscriber(self):
        """Return the 'Subscribe someone else' Link."""
        text = 'Subscribe someone else'
        return Link(
            '+addsubscriber', text, icon='add', summary=(
                'Launchpad will email that person whenever this bugs '
                'changes'))

    def editsubscriptions(self):
        """Return the 'Edit subscriptions' Link."""
        text = 'Edit bug mail'
        return Link(
            '+subscriptions', text, icon='edit', summary=(
                'View and change your subscriptions to this bug'))

    def mute_subscription(self):
        """Return the 'Mute subscription' Link."""
        user = getUtility(ILaunchBag).user
        if self.context.bug.isMuted(user):
            text = "Unmute bug mail"
            icon = 'unmute'
        else:
            text = "Mute bug mail"
            icon = 'mute'

        return Link(
            '+mute', text, icon=icon, summary=(
                "Mute this bug so that you will not receive emails "
                "about it."))

    def nominate(self):
        """Return the 'Target/Nominate for series' Link."""
        launchbag = getUtility(ILaunchBag)
        target = launchbag.product or launchbag.distribution
        if check_permission("launchpad.Driver", target):
            text = "Target to series"
            return Link('+nominate', text, icon='milestone')
        elif (check_permission("launchpad.BugSupervisor", target) or
            self.user is None):
            text = 'Nominate for series'
            return Link('+nominate', text, icon='milestone')
        else:
            return Link('+nominate', '', enabled=False, icon='milestone')

    def addcomment(self):
        """Return the 'Comment or attach file' Link."""
        text = 'Add attachment or patch'
        return Link('+addcomment', text, icon='add')

    def addbranch(self):
        """Return the 'Add branch' Link."""
        text = 'Link a related branch'
        return Link('+addbranch', text, icon='add')

    def linktocve(self):
        """Return the 'Link to CVE' Link."""
        text = structured(
            'Link to '
            '<abbr title="Common Vulnerabilities and Exposures Index">'
            'CVE'
            '</abbr>')
        return Link('+linkcve', text, icon='add')

    def unlinkcve(self):
        """Return 'Remove CVE link' Link."""
        enabled = self.context.bug.has_cves
        text = 'Remove CVE link'
        return Link('+unlinkcve', text, icon='remove', enabled=enabled)

    @property
    def _bug_question(self):
        return self.context.bug.getQuestionCreatedFromBug()

    def createquestion(self):
        """Create a question from this bug."""
        text = 'Convert to a question'
        enabled = self._bug_question is None
        return Link('+create-question', text, enabled=enabled, icon='add')

    def removequestion(self):
        """Remove the created question from this bug."""
        text = 'Convert back to a bug'
        enabled = self._bug_question is not None
        return Link('+remove-question', text, enabled=enabled, icon='remove')

    def activitylog(self):
        """Return the 'Activity log' Link."""
        text = 'See full activity log'
        return Link('+activity', text)

    def affectsmetoo(self):
        """Return the 'This bug affects me too' link."""
        enabled = getUtility(ILaunchBag).user is not None
        return Link('+affectsmetoo', 'change', enabled=enabled)


class MaloneView(LaunchpadFormView):
    """The Bugs front page."""

    custom_widget('searchtext', TextWidget, displayWidth=50)
    custom_widget('scope', ProjectScopeWidget)
    schema = IFrontPageBugTaskSearch
    field_names = ['searchtext', 'scope']

    # Test: standalone/xx-slash-malone-slash-bugs.txt
    error_message = None

    page_title = 'Launchpad Bugs'

    @property
    def target_css_class(self):
        """The CSS class for used in the target widget."""
        if self.target_error:
            return 'error'
        else:
            return None

    @property
    def target_error(self):
        """The error message for the target widget."""
        return self.getFieldError('scope')

    def initialize(self):
        """Initialize the view to handle the request."""
        LaunchpadFormView.initialize(self)
        bug_id = self.request.form.get("id")
        if bug_id:
            self._redirectToBug(bug_id)
        elif self.widgets['scope'].hasInput():
            self._validate(action=None, data={})

    def _redirectToBug(self, bug_id):
        """Redirect to the specified bug id."""
        if not isinstance(bug_id, basestring):
            self.error_message = "Bug %r is not registered." % bug_id
            return
        if bug_id.startswith("#"):
            # Be nice to users and chop off leading hashes
            bug_id = bug_id[1:]
        try:
            bug = getUtility(IBugSet).getByNameOrID(bug_id)
        except NotFoundError:
            self.error_message = "Bug %r is not registered." % bug_id
        else:
            return self.request.response.redirect(canonical_url(bug))

    @property
    def most_recently_fixed_bugs(self):
        """Return the five most recently fixed bugs."""
        params = BugTaskSearchParams(
            self.user, status=BugTaskStatus.FIXRELEASED,
            date_closed=not_equals(None), orderby='-date_closed')
        return getUtility(IBugSet).getDistinctBugsForBugTasks(
            self.context.searchTasks(params), self.user, limit=5)

    @property
    def most_recently_reported_bugs(self):
        """Return the five most recently reported bugs."""
        params = BugTaskSearchParams(self.user, orderby='-datecreated')
        return getUtility(IBugSet).getDistinctBugsForBugTasks(
            self.context.searchTasks(params), self.user, limit=5)

    def getCveBugLinkCount(self):
        """Return the number of links between bugs and CVEs there are."""
        return getUtility(ICveSet).getBugCveCount()


class BugViewMixin:
    """Mix-in class to share methods between bug and portlet views."""

    @cachedproperty
    def is_duplicate_active(self):
        active = True
        if self.context.duplicateof is not None:
            naked_duplicate = removeSecurityProxy(self.context.duplicateof)
            active = getattr(
                naked_duplicate.default_bugtask.target, 'active', True)
        return active

    @cachedproperty
    def subscription_info(self):
        return IBug(self.context).getSubscriptionInfo()

    @cachedproperty
    def direct_subscribers(self):
        """Return the list of direct subscribers."""
        return self.subscription_info.direct_subscribers

    @cachedproperty
    def duplicate_subscribers(self):
        """Return the list of subscribers from duplicates.

        This includes all subscribers who are also direct or indirect
        subscribers.
        """
        return self.subscription_info.duplicate_subscribers

    def getSubscriptionClassForUser(self, subscribed_person):
        """Return a set of CSS class names based on subscription status.

        For example, "subscribed-false dup-subscribed-true".
        """
        if subscribed_person in self.duplicate_subscribers:
            dup_class = 'dup-subscribed-true'
        else:
            dup_class = 'dup-subscribed-false'

        if subscribed_person in self.direct_subscribers:
            return 'subscribed-true %s' % dup_class
        else:
            return 'subscribed-false %s' % dup_class

    @cachedproperty
    def _bug_attachments(self):
        """Get a dict of attachment type -> attachments list."""
        # Note that this is duplicated with get_comments_for_bugtask
        # if you are looking to consolidate things.
        result = {
            BugAttachmentType.PATCH: [],
            'other': [],
            }
        for attachment in self.context.attachments_unpopulated:
            info = {
                'attachment': attachment,
                'file': ProxiedLibraryFileAlias(
                    attachment.libraryfile, attachment),
                }
            if attachment.type == BugAttachmentType.PATCH:
                key = attachment.type
            else:
                key = 'other'
            result[key].append(info)
        return result

    @property
    def regular_attachments(self):
        """The list of bug attachments that are not patches."""
        return self._bug_attachments['other']

    @property
    def patches(self):
        """The list of bug attachments that are patches."""
        return self._bug_attachments[BugAttachmentType.PATCH]

    @property
    def current_bugtask(self):
        """Return the current `IBugTask`.

        'current' is determined by simply looking in the ILaunchBag utility.
        """
        return getUtility(ILaunchBag).bugtask

    @property
    def specifications(self):
        return self.context.getSpecifications(self.user)


class BugInformationTypePortletView(InformationTypePortletMixin,
                                    LaunchpadView):
    """View class for the information type portlet."""


class BugView(LaunchpadView, BugViewMixin):
    """View class for presenting information about an `IBug`.

    Since all bug pages are registered on IBugTask, the context will be
    adapted to IBug in order to make the security declarations work
    properly. This has the effect that the context in the pagetemplate
    changes as well, so the bugtask (which is often used in the pages)
    is available as `current_bugtask`. This may not be all that pretty,
    but it was the best solution we came up with when deciding to hang
    all the pages off IBugTask instead of IBug.
    """

    @cachedproperty
    def page_description(self):
        return IBug(self.context).description

    @property
    def subscription(self):
        """Return whether the current user is subscribed."""
        user = self.user
        if user is None:
            return False
        return self.context.isSubscribed(user)

    def duplicates(self):
        """Return a list of dicts of duplicates.

        Each dict contains the title that should be shown and the bug
        object itself. This allows us to protect private bugs using a
        title like 'Private Bug'.
        """
        duplicate_bugs = list(self.context.duplicates)
        current_task = self.current_bugtask
        dupes_in_current_context = dict(
            (bugtask.bug, bugtask)
            for bugtask in current_task.target.searchTasks(
                BugTaskSearchParams(self.user, bug=any(*duplicate_bugs))))
        dupes = []
        for bug in duplicate_bugs:
            dupe = {}
            try:
                dupe['title'] = bug.title
            except Unauthorized:
                dupe['title'] = 'Private Bug'
            dupe['id'] = bug.id
            # If the dupe has the same context as the one we're in, link
            # to that bug task directly.
            if bug in dupes_in_current_context:
                dupe['url'] = canonical_url(dupes_in_current_context[bug])
            else:
                dupe['url'] = canonical_url(bug)
            dupes.append(dupe)

        return dupes

    def proxiedUrlForLibraryFile(self, attachment):
        """Return the proxied download URL for a Librarian file."""
        return ProxiedLibraryFileAlias(
            attachment.libraryfile, attachment).http_url


class BugActivity(BugView):

    page_title = 'Activity log'

    @property
    def activity(self):
        activity = IBug(self.context).activity
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            [a.personID for a in activity], need_validity=True))
        return activity


class BugSubscriptionPortletDetails:
    """A mixin used to collate bug subscription details for a view."""

    def extractBugSubscriptionDetails(self, user, bug, cache):
        # We are using "direct" to represent both direct and personal
        # (not team).
        self.direct_notifications = False
        self.direct_all_notifications = False
        self.direct_metadata_notifications = False
        self.direct_lifecycle_notifications = False
        self.other_subscription_notifications = False
        self.only_other_subscription_notifications = False
        self.any_subscription_notifications = False
        self.muted = False
        if user is not None:
            has_structural_subscriptions = not (
                get_structural_subscriptions_for_bug(bug, user).is_empty())
            self.muted = bug.isMuted(user)
            psi = PersonSubscriptions(user, bug)
            if psi.direct.personal:
                self.direct_notifications = True
                direct = psi.direct.personal[0]
                cache['subscription'] = direct.subscription
                level = direct.subscription.bug_notification_level
                if level == BugNotificationLevel.COMMENTS:
                    self.direct_all_notifications = True
                elif level == BugNotificationLevel.METADATA:
                    self.direct_metadata_notifications = True
                else:
                    assert level == BugNotificationLevel.LIFECYCLE
                    self.direct_lifecycle_notifications = True
            self.other_subscription_notifications = bool(
                has_structural_subscriptions or
                psi.from_duplicate.count or
                psi.as_owner.count or
                psi.as_assignee.count or
                psi.direct.as_team_member or
                psi.direct.as_team_admin)
            cache['other_subscription_notifications'] = bool(
                self.other_subscription_notifications)
            self.only_other_subscription_notifications = (
                self.other_subscription_notifications and
                not self.direct_notifications)
            self.any_subscription_notifications = (
                self.other_subscription_notifications or
                self.direct_notifications)
        self.user_should_see_mute_link = (
            self.any_subscription_notifications or self.muted)


class BugSubscriptionPortletView(LaunchpadView,
                                 BugSubscriptionPortletDetails, BugViewMixin):
    """View class for the subscription portlet."""

    # We want these strings to be available for the template and for the
    # JavaScript.
    notifications_text = {
        'not_only_other_subscription': _('You are'),
        'only_other_subscription': _(
            'You have subscriptions that may cause you to receive '
            'notifications, but you are'),
        'direct_all': _('subscribed to all notifications for this bug.'),
        'direct_metadata': _(
            'subscribed to all notifications except comments for this bug.'),
        'direct_lifecycle': _(
            'subscribed to notifications when this bug is closed or '
            'reopened.'),
        'not_direct': _(
            "not directly subscribed to this bug's notifications."),
        'muted': _(
            'Your personal email notifications from this bug are muted.'),
        }

    def initialize(self):
        """Initialize the view to handle the request."""
        LaunchpadView.initialize(self)
        cache = IJSONRequestCache(self.request).objects
        self.extractBugSubscriptionDetails(self.user, self.context, cache)
        cache['bug_is_private'] = self.context.private
        if self.user:
            cache['notifications_text'] = self.notifications_text


class BugWithoutContextView(RedirectionView):
    """View that redirects to the new bug page.

    The user is redirected, to the oldest IBugTask ('oldest' being
    defined as the IBugTask with the smallest ID.)
    """

    def __init__(self, context, request):
        redirected_context = context.default_bugtask
        viewname = getDefaultViewName(redirected_context, request)
        cache_view = getMultiAdapter(
            (redirected_context, request), name=viewname)
        super(BugWithoutContextView, self).__init__(
            canonical_url(redirected_context), request, cache_view=cache_view)


class BugEditViewBase(LaunchpadEditFormView):
    """Base class for all bug edit pages."""

    schema = IBug
    page_title = 'Edit'

    def setUpWidgets(self):
        """Set up the widgets using the bug as the context."""
        LaunchpadEditFormView.setUpWidgets(self, context=self.context.bug)

    def updateBugFromData(self, data):
        """Update the bug using the values in the data dictionary."""
        LaunchpadEditFormView.updateContextFromData(
            self, data, context=self.context.bug)

    @property
    def next_url(self):
        """Return the next URL to call when this call completes."""
        return canonical_url(self.context)

    cancel_url = next_url


class BugEditView(BugEditViewBase):
    """The view for the edit bug page."""

    field_names = ['title', 'description', 'tags']
    custom_widget('title', TextWidget, displayWidth=30)
    custom_widget('tags', BugTagsWidget)

    @property
    def label(self):
        """The form label."""
        return 'Edit details for bug #%d' % self.context.bug.id

    page_title = label

    @action('Change', name='change')
    def change_action(self, action, data):
        """Update the bug with submitted changes."""
        self.updateBugFromData(data)


class BugMarkAsDuplicateView(BugEditViewBase):
    """Page for marking a bug as a duplicate."""

    field_names = ['duplicateof']
    label = "Mark bug report as a duplicate"
    page_title = label

    def setUpFields(self):
        """Make the readonly version of duplicateof available."""
        super(BugMarkAsDuplicateView, self).setUpFields()

        duplicateof_field = DuplicateBug(
            __name__='duplicateof', title=_('Duplicate Of'), required=True)

        self.form_fields = self.form_fields.omit('duplicateof')
        self.form_fields = formlib.form.Fields(duplicateof_field)

    @property
    def initial_values(self):
        """See `LaunchpadFormView.`"""
        return {'duplicateof': self.context.bug.duplicateof}

    @property
    def next_url(self):
        """Return the next URL to call when this call completes."""
        if not self.request.is_ajax:
            return canonical_url(self.context)
        return None

    def _validate(self, action, data):
        if action.name != 'remove':
            return super(BugMarkAsDuplicateView, self)._validate(action, data)
        return []

    @action('Set Duplicate', name='change',
        failure=LaunchpadFormView.ajax_failure_handler)
    def change_action(self, action, data):
        """Update the bug."""
        data = dict(data)
        # We handle duplicate changes by hand instead of leaving it to
        # the usual machinery because we must use bug.markAsDuplicate().
        bug = self.context.bug
        bug_before_modification = Snapshot(bug, providing=providedBy(bug))
        duplicateof = data.pop('duplicateof')
        bug.markAsDuplicate(duplicateof)
        notify(
            ObjectModifiedEvent(bug, bug_before_modification, 'duplicateof'))
        # Apply other changes.
        self.updateBugFromData(data)
        return self._duplicate_action_result()

    def shouldShowRemoveButton(self, action):
        return self.context.bug.duplicateof is not None

    @action('Remove Duplicate', name='remove',
        condition=shouldShowRemoveButton)
    def remove_action(self, action, data):
        """Update the bug."""
        bug = self.context.bug
        bug_before_modification = Snapshot(bug, providing=providedBy(bug))
        bug.markAsDuplicate(None)
        notify(
            ObjectModifiedEvent(bug, bug_before_modification, 'duplicateof'))
        return self._duplicate_action_result()

    def _duplicate_action_result(self):
        if self.request.is_ajax:
            bug = self.context.bug
            launchbag = getUtility(ILaunchBag)
            launchbag.add(bug.default_bugtask)
            view = getMultiAdapter(
                (bug, self.request),
                name='+bugtasks-and-nominations-table')
            view.initialize()
            return view.render()
        return None


class BugSecrecyEditView(LaunchpadFormView, BugSubscriptionPortletDetails):
    """Form for marking a bug as a private/public."""

    @property
    def label(self):
        return 'Bug #%i - Set information type' % self.context.bug.id

    page_title = label

    field_names = ['information_type', 'validate_change']

    custom_widget('information_type', LaunchpadRadioWidgetWithDescription)
    custom_widget('validate_change', GhostCheckBoxWidget)

    @property
    def schema(self):
        """Schema for editing the information type of a `IBug`."""
        info_types = self.context.bug.getAllowedInformationTypes(self.user)

        class information_type_schema(Interface):
            information_type_field = copy_field(
                IBug['information_type'], readonly=False,
                vocabulary=InformationTypeVocabulary(types=info_types))
            # A hidden field used to determine if the new information type
            # should be validated to ensure the bug does not become invisible
            # after the change.
            validate_change = Bool(
                title=u"Validate change", required=False, default=False)
        return information_type_schema

    @property
    def next_url(self):
        """Return the next URL to call when this call completes."""
        if not self.request.is_ajax:
            return canonical_url(self.context)
        return None

    cancel_url = next_url

    @property
    def initial_values(self):
        """See `LaunchpadFormView.`"""
        return {'information_type': self.context.bug.information_type}

    @action('Change', name='change',
        failure=LaunchpadFormView.ajax_failure_handler)
    def change_action(self, action, data):
        """Update the bug."""
        data = dict(data)
        bug = self.context.bug
        information_type = data.pop('information_type')
        changed_fields = ['information_type']
        # When the user first submits the form, validate change is True and
        # so we check that the bug does not become invisible. If the user
        # confirms they really want to make the change, validate change is
        # False and we process the change as normal.
        if self.request.is_ajax:
            validate_change = data.get('validate_change', False)
            if (validate_change and
                information_type in PRIVATE_INFORMATION_TYPES and
                self._bug_will_be_invisible(information_type)):
                self.request.response.setStatus(400, "Bug Visibility")
                return ''

        user_will_be_subscribed = (
            information_type in PRIVATE_INFORMATION_TYPES and
            bug.getSubscribersForPerson(self.user).is_empty())
        bug_before_modification = Snapshot(bug, providing=providedBy(bug))
        changed = bug.transitionToInformationType(
            information_type, self.user)
        if changed:
            self._handlePrivacyChanged(user_will_be_subscribed)
            notify(
                ObjectModifiedEvent(
                    bug, bug_before_modification, changed_fields,
                    user=self.user))
        if self.request.is_ajax:
            # Avoid circular imports
            from lp.bugs.browser.bugtask import (
                can_add_package_task_to_bug,
                can_add_project_task_to_bug,
            )
            if changed:
                result_data = self._getSubscriptionDetails()
                result_data['can_add_project_task'] = (
                    can_add_project_task_to_bug(bug))
                result_data['can_add_package_task'] = (
                    can_add_package_task_to_bug(bug))
                self.request.response.setHeader(
                    'content-type', 'application/json')
                return dumps(
                    result_data, cls=ResourceJSONEncoder,
                    media_type=EntryResource.JSON_TYPE)
            else:
                return ''

    def _bug_will_be_invisible(self, information_type):
        # Return true if this bug will be totally invisible if it were to be
        # change to the specified information type.
        pillars = self.context.bug.affected_pillars
        service = getUtility(IService, 'sharing')
        for pillar in pillars:
            grant_counts = service.getAccessPolicyGrantCounts(pillar)
            for count_info in grant_counts:
                if count_info[1] > 0 and count_info[0] == information_type:
                    return False
        return True

    def _getSubscriptionDetails(self):
        cache = dict()
        # The subscription details for the current user.
        self.extractBugSubscriptionDetails(self.user, self.context.bug, cache)

        # The subscription details for other users to populate the subscribers
        # list in the portlet.
        if IBugTask.providedBy(self.context):
            bug = self.context.bug
        else:
            bug = self.context
        subscribers_portlet = BugPortletSubscribersWithDetails(
            bug, self.request)
        subscription_data = subscribers_portlet.subscriber_data
        result_data = dict(
            cache_data=cache,
            subscription_data=subscription_data)
        return result_data

    def _handlePrivacyChanged(self, user_will_be_subscribed):
        """Handle the case where the privacy of the bug has been changed.

        If the bug has been made private and the user is not a direct
        subscriber, they will be subscribed. If the bug is being made
        public or the user is already directly subscribed, this is a
        no-op.
        """
        if user_will_be_subscribed:
            notification_text = (
                    "Since you marked this bug as private you have "
                    "automatically been subscribed to it. "
                    "If you don't want to receive email about "
                    "this bug you can <a href=\"%s\">mute your "
                    "subscription</a> or <a href=\"%s\">"
                    "unsubscribe</a>." % (
                    canonical_url(
                        self.context, view_name='+mute'),
                    canonical_url(
                        self.context, view_name='+subscribe')))
            self.request.response.addInfoNotification(
                structured(notification_text))


class DeprecatedAssignedBugsView(RedirectionView):
    """Deprecate the /malone/assigned namespace.

    It's important to ensure that this namespace continues to work, to
    prevent linkrot, but since FOAF seems to be a more natural place
    to put the assigned bugs report, we'll redirect to the appropriate
    FOAF URL.
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.status = 303

    def __call__(self):
        self.target = canonical_url(
            getUtility(ILaunchBag).user, view_name='+assignedbugs')
        super(DeprecatedAssignedBugsView, self).__call__()


normalize_mime_type = re.compile(r'\s+')


class BugTextView(LaunchpadView):
    """View for simple text page displaying information for a bug."""

    def initialize(self):
        # If we have made it to here then the logged in user can see the
        # bug, hence they can see any assignees and subscribers.
        # The security adaptor will do the job also but we don't want or need
        # the expense of running several complex SQL queries.
        authorised_people = []
        for task in self.bugtasks:
            if task.assignee is not None:
                authorised_people.append(task.assignee)
        authorised_people.extend(self.subscribers)
        precache_permission_for_objects(
            self.request, 'launchpad.LimitedView', authorised_people)

    @cachedproperty
    def bugtasks(self):
        """Cache bugtasks and avoid hitting the DB twice."""
        return list(self.context.bugtasks)

    @cachedproperty
    def subscribers(self):
        """Cache subscribers and avoid hitting the DB twice."""
        return [sub.person for sub in self.context.subscriptions
                if self.user or not sub.person.private]

    def bug_text(self):

        """Return the bug information for text display."""
        bug = self.context

        text = []
        text.append('bug: %d' % bug.id)
        text.append('title: %s' % bug.title)
        text.append('date-reported: %s' %
            format_rfc2822_date(bug.datecreated))
        text.append('date-updated: %s' %
            format_rfc2822_date(bug.date_last_updated))
        text.append('reporter: %s' % bug.owner.unique_displayname)

        if bug.duplicateof:
            text.append('duplicate-of: %d' % bug.duplicateof.id)
        else:
            text.append('duplicate-of: ')

        if bug.duplicates:
            dupes = ' '.join(str(dupe.id) for dupe in bug.duplicates)
            text.append('duplicates: %s' % dupes)
        else:
            text.append('duplicates: ')

        if bug.private:
            # XXX kiko 2007-10-31: this could include date_made_private and
            # who_made_private but Bjorn doesn't let me.
            text.append('private: yes')

        if bug.security_related:
            text.append('security: yes')

        patches = []
        text.append('attachments: ')
        for attachment in bug.attachments_unpopulated:
            if attachment.type != BugAttachmentType.PATCH:
                text.append(' %s' % self.attachment_text(attachment))
            else:
                patches.append(attachment)

        text.append('patches: ')
        for attachment in patches:
            text.append(' %s' % self.attachment_text(attachment))

        text.append('tags: %s' % ' '.join(bug.tags))

        text.append('subscribers: ')
        for subscriber in self.subscribers:
            text.append(' %s' % subscriber.unique_displayname)

        return ''.join(line + '\n' for line in text)

    def bugtask_text(self, task):
        """Return a BugTask for text display."""
        text = []
        text.append('task: %s' % task.bugtargetname)
        text.append('status: %s' % task.status.title)
        text.append('date-created: %s' %
            format_rfc2822_date(task.datecreated))

        for status in ["left_new", "confirmed", "triaged", "assigned",
                       "inprogress", "closed", "incomplete",
                       "fix_committed", "fix_released", "left_closed"]:
            date = getattr(task, "date_%s" % status)
            if date:
                text.append("date-%s: %s" % (
                    status.replace('_', '-'), format_rfc2822_date(date)))

        text.append('reporter: %s' % task.owner.unique_displayname)

        if task.bugwatch:
            text.append('watch: %s' % task.bugwatch.url)

        text.append('importance: %s' % task.importance.title)

        component = task.getPackageComponent()
        if component:
            text.append('component: %s' % component.name)

        if (task.assignee
            and check_permission('launchpad.LimitedView', task.assignee)):
            text.append('assignee: %s' % task.assignee.unique_displayname)
        else:
            text.append('assignee: ')

        if task.milestone:
            text.append('milestone: %s' % task.milestone.name)
        else:
            text.append('milestone: ')

        return ''.join(line + '\n' for line in text)

    def attachment_text(self, attachment):
        """Return a text representation of a bug attachment."""
        mime_type = normalize_mime_type.sub(
            ' ', attachment.libraryfile.mimetype)
        download_url = ProxiedLibraryFileAlias(
            attachment.libraryfile, attachment).http_url
        return "%s %s" % (download_url, mime_type)

    def comment_text(self):
        """Return a text representation of bug comments."""

        def build_message(text):
            mailwrapper = MailWrapper(width=72)
            text = mailwrapper.format(text)
            message = MIMEText(text.encode('utf-8'),
                'plain', 'utf-8')
            # This is redundant and makes the template noisy
            del message['MIME-Version']
            return message

        from lp.bugs.browser.bugtask import (
            get_visible_comments, get_comments_for_bugtask)

        # XXX: kiko 2007-10-31: for some reason, get_comments_for_bugtask
        # takes a task, not a bug. For now live with it.
        first_task = self.bugtasks[0]
        all_comments = get_comments_for_bugtask(first_task)
        comments = get_visible_comments(all_comments[1:])

        comment_mime = MIMEMultipart()
        message = build_message(self.context.description)
        comment_mime.attach(message)

        for comment in comments:
            message = build_message(comment.text_for_display)
            message['Author'] = comment.owner.unique_displayname.encode(
                'utf-8')
            message['Date'] = format_rfc2822_date(comment.datecreated)
            message['Message-Id'] = comment.rfc822msgid
            comment_mime.attach(message)

        return comment_mime.as_string().decode('utf-8')

    def render(self):
        """Return a text representation of the bug."""
        self.request.response.setHeader('Content-type', 'text/plain')
        texts = [self.bug_text()]
        texts.extend(self.bugtask_text(task) for task in self.bugtasks)
        texts.append(self.comment_text())
        return "\n".join(texts)


class BugURL:
    """Bug URL creation rules."""
    implements(ICanonicalUrlData)

    inside = None
    rootsite = 'bugs'

    def __init__(self, context):
        self.context = context

    @property
    def path(self):
        """Return the path component of the URL."""
        return u"bugs/%d" % self.context.id


class BugAffectingUserChoice(EnumeratedType):
    """The choices for a bug affecting a user."""

    YES = Item("""
        Yes

        This bug affects me.
        """)

    NO = Item("""
        No

        This bug doesn't affect me.
        """)


class BugMarkAsAffectingUserForm(Interface):
    """Form schema for marking the bug as affecting the user."""
    affects = Choice(
        title=_('Does this bug affect you?'),
        vocabulary=BugAffectingUserChoice)


class BugMarkAsAffectingUserView(LaunchpadFormView):
    """Page for marking a bug as affecting the user."""

    schema = BugMarkAsAffectingUserForm

    field_names = ['affects']
    label = "Does this bug affect you?"
    page_title = label

    custom_widget('affects', LaunchpadRadioWidgetWithDescription)

    @property
    def initial_values(self):
        """See `LaunchpadFormView.`"""
        affected = self.context.bug.isUserAffected(self.user)
        if affected or affected is None:
            affects = BugAffectingUserChoice.YES
        else:
            affects = BugAffectingUserChoice.NO

        return {'affects': affects}

    @action('Change', name='change')
    def change_action(self, action, data):
        """Mark the bug according to the selection."""
        self.context.bug.markUserAffected(
            self.user, data['affects'] == BugAffectingUserChoice.YES)
        self.request.response.redirect(canonical_url(self.context.bug))
