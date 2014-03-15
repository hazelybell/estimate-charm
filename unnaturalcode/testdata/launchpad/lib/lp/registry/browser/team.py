# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'HasRenewalPolicyMixin',
    'ProposedTeamMembersEditView',
    'TeamAddMyTeamsView',
    'TeamAddView',
    'TeamBadges',
    'TeamBrandingView',
    'TeamBreadcrumb',
    'TeamContactAddressView',
    'TeamEditMenu',
    'TeamEditView',
    'TeamIndexMenu',
    'TeamJoinView',
    'TeamLeaveView',
    'TeamMailingListConfigurationView',
    'TeamMailingListModerationView',
    'TeamMailingListSubscribersView',
    'TeamMailingListArchiveView',
    'TeamMemberAddView',
    'TeamMembershipSelfRenewalView',
    'TeamMembershipView',
    'TeamMugshotView',
    'TeamNavigation',
    'TeamOverviewMenu',
    'TeamOverviewNavigationMenu',
    'TeamPrivacyAdapter',
    'TeamReassignmentView',
    ]


from datetime import (
    datetime,
    timedelta,
    )
import math
from urllib import unquote

from lazr.restful.interface import copy_field
from lazr.restful.interfaces import IJSONRequestCache
from lazr.restful.utils import smartquote
import pytz
import simplejson
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib.form import (
    Fields,
    FormField,
    FormFields,
    )
from zope.formlib.textwidgets import IntWidget
from zope.formlib.widgets import TextAreaWidget
from zope.interface import (
    classImplements,
    implements,
    Interface,
    )
from zope.publisher.interfaces.browser import IBrowserPublisher
from zope.schema import (
    Bool,
    Choice,
    List,
    Text,
    )
from zope.schema.vocabulary import (
    getVocabularyRegistry,
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.app.browser.badge import HasBadgeBase
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.browser.tales import PersonFormatterAPI
from lp.app.errors import UnexpectedFormData
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.validation import validate_new_team_email
from lp.app.widgets.itemswidgets import (
    LabeledMultiCheckBoxWidget,
    LaunchpadDropdownWidget,
    LaunchpadRadioWidget,
    LaunchpadRadioWidgetWithDescription,
    )
from lp.app.widgets.owner import HiddenUserWidget
from lp.app.widgets.popup import PersonPickerWidget
from lp.code.browser.sourcepackagerecipelisting import HasRecipesMenuMixin
from lp.registry.browser.branding import BrandingChangeView
from lp.registry.browser.mailinglists import enabled_with_active_mailing_list
from lp.registry.browser.objectreassignment import ObjectReassignmentView
from lp.registry.browser.person import (
    CommonMenuLinks,
    PersonAdministerView,
    PersonIndexView,
    PersonNavigation,
    PersonRenameFormMixin,
    PPANavigationMenuMixIn,
    )
from lp.registry.browser.teamjoin import (
    TeamJoinMixin,
    userIsActiveTeamMember,
    )
from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    PersonVisibility,
    TeamMembershipPolicy,
    TeamMembershipRenewalPolicy,
    )
from lp.registry.errors import TeamMembershipPolicyError
from lp.registry.interfaces.mailinglist import (
    IMailingList,
    IMailingListSet,
    MailingListStatus,
    PostedMessageStatus,
    PURGE_STATES,
    )
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.person import (
    ImmutableVisibilityError,
    IPersonSet,
    ITeam,
    ITeamContactAddressForm,
    ITeamReassignment,
    PRIVATE_TEAM_PREFIX,
    TeamContactMethod,
    )
from lp.registry.interfaces.poll import IPollSet
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.teammembership import (
    CyclicalTeamMembershipError,
    DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT,
    ITeamMembership,
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.security import ModerateByRegistryExpertsOrAdmins
from lp.services.config import config
from lp.services.features import getFeatureFlag
from lp.services.fields import PersonChoice
from lp.services.identity.interfaces.emailaddress import IEmailAddressSet
from lp.services.privacy.interfaces import IObjectPrivacy
from lp.services.propertycache import cachedproperty
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import ILoginTokenSet
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    NavigationMenu,
    stepthrough,
    )
from lp.services.webapp.authorization import (
    check_permission,
    clear_cache,
    )
from lp.services.webapp.batching import (
    ActiveBatchNavigator,
    BatchNavigator,
    InactiveBatchNavigator,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag


class TeamPrivacyAdapter:
    """Provides `IObjectPrivacy` for `ITeam`."""

    implements(IObjectPrivacy)

    def __init__(self, context):
        self.context = context

    @property
    def is_private(self):
        """Return True if the team is private, otherwise False."""
        return self.context.visibility != PersonVisibility.PUBLIC


class TeamBadges(HasBadgeBase):
    """Provides `IHasBadges` for `ITeam`."""

    def getPrivateBadgeTitle(self):
        """Return private badge info useful for a tooltip."""
        return "This is a %s team" % self.context.visibility.title.lower()


class HasRenewalPolicyMixin:
    """Mixin to be used on forms which contain ITeam.renewal_policy.

    This mixin will short-circuit Launchpad*FormView when defining whether
    the renewal_policy widget should be displayed in a single or multi-line
    layout. We need that because that field has a very long title, thus
    breaking the page layout.

    Since this mixin short-circuits Launchpad*FormView in some cases, it must
    always precede Launchpad*FormView in the inheritance list.
    """

    def isMultiLineLayout(self, field_name):
        if field_name == 'renewal_policy':
            return True
        return super(HasRenewalPolicyMixin, self).isMultiLineLayout(
            field_name)

    def isSingleLineLayout(self, field_name):
        if field_name == 'renewal_policy':
            return False
        return super(HasRenewalPolicyMixin, self).isSingleLineLayout(
            field_name)


class TeamFormMixin:
    """Form to be used on forms which conditionally display team visibility.

    The visibility field is shown if
    * The user has launchpad.Commercial permission.
    * The user has a current commercial subscription.
    """
    field_names = [
        "name", "visibility", "displayname",
        "description", "membership_policy",
        "defaultmembershipperiod", "renewal_policy",
        "defaultrenewalperiod", "teamowner",
        ]
    private_prefix = PRIVATE_TEAM_PREFIX

    def _validateVisibilityConsistency(self, value):
        """Perform a consistency check regarding visibility.

        This property must be overridden if the current context is not an
        IPerson.
        """
        return self.context.visibilityConsistencyWarning(value)

    @property
    def _visibility(self):
        """Return the visibility for the object."""
        return self.context.visibility

    @property
    def _name(self):
        return self.context.name

    def validate(self, data):
        visibility = data.get('visibility', self._visibility)
        if visibility != PersonVisibility.PUBLIC:
            if visibility != self._visibility:
                # If the user is attempting to change the team visibility
                # ensure that there are no constraints being violated.
                warning = self._validateVisibilityConsistency(visibility)
                if warning is not None:
                    self.setFieldError('visibility', warning)
            if (data['membership_policy']
                != TeamMembershipPolicy.RESTRICTED):
                self.setFieldError(
                    'membership_policy',
                    'Private teams must have a Restricted membership policy.')

    def setUpVisibilityField(self, render_context=False):
        """Set the visibility field to read-write, or remove it."""
        self.form_fields = self.form_fields.omit('visibility')
        if self.user and self.user.checkAllowVisibility():
            visibility = copy_field(ITeam['visibility'], readonly=False)
            self.form_fields += Fields(
                visibility, render_context=render_context)
            # Shift visibility to be the third field.
            field_names = [field.__name__ for field in self.form_fields]
            field = field_names.pop()
            field_names.insert(2, field)
            self.form_fields = self.form_fields.select(*field_names)


class TeamEditView(TeamFormMixin, PersonRenameFormMixin,
                   HasRenewalPolicyMixin):
    """View for editing team details."""
    schema = ITeam

    @property
    def label(self):
        """The form label."""
        return 'Edit "%s" team' % self.context.displayname

    page_title = label

    custom_widget(
        'renewal_policy', LaunchpadRadioWidget, orientation='vertical')
    custom_widget('defaultrenewalperiod', IntWidget,
        widget_class='field subordinate')
    custom_widget(
        'membership_policy', LaunchpadRadioWidgetWithDescription,
        orientation='vertical')
    custom_widget('description', TextAreaWidget, height=10, width=30)

    def setUpFields(self):
        """See `LaunchpadViewForm`."""
        # Make an instance copy of field_names so as to not modify the single
        # class list.
        self.field_names = list(self.field_names)
        self.field_names.remove('teamowner')
        super(TeamEditView, self).setUpFields()
        self.setUpVisibilityField(render_context=True)

    def setUpWidgets(self):
        super(TeamEditView, self).setUpWidgets()
        team = self.context
        # Do we need to only show open membership policy choices?
        try:
            team.checkExclusiveMembershipPolicyAllowed()
        except TeamMembershipPolicyError as e:
            # Ideally SimpleVocabulary.fromItems() would accept 3-tuples but
            # it doesn't so we need to be a bit more verbose.
            self.widgets['membership_policy'].vocabulary = (
                SimpleVocabulary([SimpleVocabulary.createTerm(
                    policy, policy.name, policy.title)
                    for policy in INCLUSIVE_TEAM_POLICY])
                )
            self.widgets['membership_policy'].extra_hint_class = (
                'sprite info')
            self.widgets['membership_policy'].extra_hint = e.message

        # Do we need to only show closed membership policy choices?
        try:
            team.checkInclusiveMembershipPolicyAllowed()
        except TeamMembershipPolicyError as e:
            # Ideally SimpleVocabulary.fromItems() would accept 3-tuples but
            # it doesn't so we need to be a bit more verbose.
            self.widgets['membership_policy'].vocabulary = (
                SimpleVocabulary([SimpleVocabulary.createTerm(
                    policy, policy.name, policy.title)
                    for policy in EXCLUSIVE_TEAM_POLICY])
                )
            self.widgets['membership_policy'].extra_hint_class = (
                'sprite info')
            self.widgets['membership_policy'].extra_hint = e.message

    @action('Save', name='save')
    def action_save(self, action, data):
        try:
            visibility = data.get('visibility')
            if visibility:
                self.context.transitionVisibility(visibility, self.user)
                del data['visibility']
            self.updateContextFromData(data)
        except ImmutableVisibilityError as error:
            self.request.response.addErrorNotification(str(error))
            # Abort must be called or changes to fields before the one causing
            # the error will be committed.  If we have a database validation
            # error we want to abort the transaction.
            # XXX: BradCrittenden 2009-04-13 bug=360540: Remove the call to
            # abort if it is moved up to updateContextFromData.
            self._abort()

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url


class TeamAdministerView(PersonAdministerView):
    """A view to administer teams on behalf of users."""
    label = "Review team"
    default_field_names = ['name', 'displayname']


def generateTokenAndValidationEmail(email, team):
    """Send a validation message to the given email."""
    login = getUtility(ILaunchBag).login
    token = getUtility(ILoginTokenSet).new(
        team, login, email, LoginTokenType.VALIDATETEAMEMAIL)

    user = getUtility(ILaunchBag).user
    token.sendTeamEmailAddressValidationEmail(user)


class MailingListTeamBaseView(LaunchpadFormView):
    """A base view for manipulating a team's mailing list.

    This class contains common functionality for retrieving and
    checking the state of mailing lists.
    """

    def _getList(self):
        """Try to find a mailing list for this team.

        :return: The mailing list object, or None if this team has no
        mailing list.
        """
        return getUtility(IMailingListSet).get(self.context.name)

    def getListInState(self, *statuses):
        """Return this team's mailing list if it's in one of the given states.

        :param statuses: The states that the mailing list must be in for it to
            be returned.
        :return: This team's IMailingList or None if the team doesn't have
            a mailing list, or if it isn't in one of the given states.
        """
        mailing_list = self._getList()
        if mailing_list is not None and mailing_list.status in statuses:
            return mailing_list
        return None

    @property
    def list_is_usable(self):
        """Checks whether or not the list is usable; ie. accepting messages.

        The list must exist and must be in a state acceptable to
        MailingList.is_usable.
        """
        mailing_list = self._getList()
        return mailing_list is not None and mailing_list.is_usable

    @property
    def mailinglist_address(self):
        """The address for this team's mailing list."""
        mailing_list = self._getList()
        assert mailing_list is not None, (
                'Attempt to find address of nonexistent mailing list.')
        return mailing_list.address


class TeamContactAddressView(MailingListTeamBaseView):
    """A view for manipulating the team's contact address."""

    schema = ITeamContactAddressForm

    custom_widget(
        'contact_method', LaunchpadRadioWidget, orientation='vertical')

    @property
    def label(self):
        return "%s contact address" % self.context.displayname

    page_title = label

    def setUpFields(self):
        """See `LaunchpadFormView`.
        """
        super(TeamContactAddressView, self).setUpFields()

        # Replace the default contact_method field by a custom one.
        self.form_fields = (
            FormFields(self.getContactMethodField())
            + self.form_fields.omit('contact_method'))

    def getContactMethodField(self):
        """Create the form.Fields to use for the contact_method field.

        If the team has a mailing list that can be the team contact
        method, the full range of TeamContactMethod terms shows up
        in the contact_method vocabulary. Otherwise, the HOSTED_LIST
        term does not show up in the vocabulary.
        """
        terms = [term for term in TeamContactMethod]
        for i, term in enumerate(TeamContactMethod):
            if term.value == TeamContactMethod.HOSTED_LIST:
                hosted_list_term_index = i
                break
        if self.list_is_usable:
            # The team's mailing list can be used as the contact
            # address. However we need to change the title of the
            # corresponding term to include the list's email address.
            title = structured(
                'The Launchpad mailing list for this team - '
                '<strong>%s</strong>', self.mailinglist_address)
            hosted_list_term = SimpleTerm(
                TeamContactMethod.HOSTED_LIST,
                TeamContactMethod.HOSTED_LIST.name, title)
            terms[hosted_list_term_index] = hosted_list_term
        else:
            # The team's mailing list does not exist or can't be
            # used as the contact address. Remove the term from the
            # field.
            del terms[hosted_list_term_index]

        return FormField(
            Choice(__name__='contact_method',
                   title=_("How do people contact this team's members?"),
                   required=True, vocabulary=SimpleVocabulary(terms)))

    def validate(self, data):
        """Validate the team contact email address.

        Validation only occurs if the user wants to use an external address,
        and the given email address is not already in use by this team.
        This also ensures the mailing list is active if the HOSTED_LIST option
        has been chosen.
        """
        if data['contact_method'] == TeamContactMethod.EXTERNAL_ADDRESS:
            email = data['contact_address']
            if not email:
                self.setFieldError(
                   'contact_address',
                   'Enter the contact address you want to use for this team.')
                return
            email = getUtility(IEmailAddressSet).getByEmail(
                data['contact_address'])
            if email is None or email.person != self.context:
                try:
                    validate_new_team_email(data['contact_address'])
                except LaunchpadValidationError as error:
                    # We need to wrap this in structured, so that the
                    # markup is preserved.  Note that this puts the
                    # responsibility for security on the exception thrower.
                    self.setFieldError('contact_address',
                                       structured(str(error)))
        elif data['contact_method'] == TeamContactMethod.HOSTED_LIST:
            mailing_list = getUtility(IMailingListSet).get(self.context.name)
            if mailing_list is None or not mailing_list.is_usable:
                self.addError(
                    "This team's mailing list is not active and may not be "
                    "used as its contact address yet")
        else:
            # Nothing to validate!
            pass

    @property
    def initial_values(self):
        """Infer the contact method from this team's preferredemail.

        Return a dictionary representing the contact_address and
        contact_method so inferred.
        """
        context = self.context
        if context.preferredemail is None:
            return dict(contact_method=TeamContactMethod.NONE)
        mailing_list = getUtility(IMailingListSet).get(context.name)
        if (mailing_list is not None
            and mailing_list.address == context.preferredemail.email):
            return dict(contact_method=TeamContactMethod.HOSTED_LIST)
        return dict(contact_address=context.preferredemail.email,
                    contact_method=TeamContactMethod.EXTERNAL_ADDRESS)

    @action('Change', name='change')
    def change_action(self, action, data):
        """Changes the contact address for this mailing list."""
        context = self.context
        email_set = getUtility(IEmailAddressSet)
        list_set = getUtility(IMailingListSet)
        contact_method = data['contact_method']
        if contact_method == TeamContactMethod.NONE:
            context.setContactAddress(None)
        elif contact_method == TeamContactMethod.HOSTED_LIST:
            mailing_list = list_set.get(context.name)
            assert mailing_list is not None and mailing_list.is_usable, (
                "A team can only use a usable mailing list as its contact "
                "address.")
            email = email_set.getByEmail(mailing_list.address)
            assert email is not None, (
                "Cannot find mailing list's posting address")
            context.setContactAddress(email)
        elif contact_method == TeamContactMethod.EXTERNAL_ADDRESS:
            contact_address = data['contact_address']
            email = email_set.getByEmail(contact_address)
            if email is None:
                generateTokenAndValidationEmail(contact_address, context)
                self.request.response.addInfoNotification(
                    "A confirmation message has been sent to '%s'. Follow "
                    "the instructions in that message to confirm the new "
                    "contact address for this team. (If the message "
                    "doesn't arrive in a few minutes, your mail provider "
                    "might use 'greylisting', which could delay the "
                    "message for up to an hour or two.)" % contact_address)
            else:
                context.setContactAddress(email)
        else:
            raise UnexpectedFormData(
                "Unknown contact_method: %s" % contact_method)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url


class TeamMailingListConfigurationView(MailingListTeamBaseView):
    """A view for creating and configuring a team's mailing list.

    Allows creating a request for a list, cancelling the request,
    setting the welcome message, deactivating, and reactivating the
    list.
    """

    schema = IMailingList
    field_names = ['welcome_message']
    label = "Mailing list configuration"
    custom_widget('welcome_message', TextAreaWidget, width=72, height=10)
    page_title = label

    def __init__(self, context, request):
        """Set feedback messages for users who want to edit the mailing list.

        There are a number of reasons why your changes to the mailing
        list might not take effect immediately. First, the mailing
        list may not actually be set as the team contact
        address. Second, the mailing list may be in a transitional
        state: from MODIFIED to UPDATING to ACTIVE can take a while.
        """
        super(TeamMailingListConfigurationView, self).__init__(
            context, request)
        list_set = getUtility(IMailingListSet)
        self.mailing_list = list_set.get(self.context.name)

    @action('Save', name='save')
    def save_action(self, action, data):
        """Sets the welcome message for a mailing list."""
        welcome_message = data.get('welcome_message')
        assert (self.mailing_list is not None
                and self.mailing_list.is_usable), (
            "Only a usable mailing list can be configured.")

        if (welcome_message is not None
            and welcome_message != self.mailing_list.welcome_message):
            self.mailing_list.welcome_message = welcome_message

        self.next_url = canonical_url(self.context)

    def cancel_list_creation_validator(self, action, data):
        """Validator for the `cancel_list_creation` action.

        Adds an error if someone tries to cancel a request that's
        already been approved or declined. This can only happen
        through bypassing the UI.
        """
        getUtility(IMailingListSet).get(self.context.name)
        if self.getListInState(MailingListStatus.REGISTERED) is None:
            self.addError("This application can't be cancelled.")

    @action('Cancel Application', name='cancel_list_creation',
            validator=cancel_list_creation_validator)
    def cancel_list_creation(self, action, data):
        """Cancels a pending mailing list registration."""
        mailing_list_set = getUtility(IMailingListSet)
        mailing_list_set.get(self.context.name).cancelRegistration()
        self.request.response.addInfoNotification(
            "Mailing list application cancelled.")
        self.next_url = canonical_url(self.context)

    def create_list_creation_validator(self, action, data):
        """Validator for the `create_list_creation` action.

        Adds an error if someone tries to create a mailing list for a
        team that already has one. This can only happen through
        bypassing the UI.
        """
        if not self.list_can_be_created:
            self.addError(
                "You cannot create a new mailing list for this team.")

    @action('Create new Mailing List', name='create_list_creation',
            validator=create_list_creation_validator)
    def create_list_creation(self, action, data):
        """Creates a new mailing list."""
        getUtility(IMailingListSet).new(self.context)
        self.request.response.addInfoNotification(
            "The mailing list is being created and will be available for "
            "use in a few minutes.")
        self.next_url = canonical_url(self.context)

    def deactivate_list_validator(self, action, data):
        """Adds an error if someone tries to deactivate a non-active list.

        This can only happen through bypassing the UI.
        """
        if not self.list_can_be_deactivated:
            self.addError("This list can't be deactivated.")

    @action('Deactivate this Mailing List', name='deactivate_list',
            validator=deactivate_list_validator)
    def deactivate_list(self, action, data):
        """Deactivates a mailing list."""
        getUtility(IMailingListSet).get(self.context.name).deactivate()
        self.request.response.addInfoNotification(
            "The mailing list will be deactivated within a few minutes.")
        self.next_url = canonical_url(self.context)

    def reactivate_list_validator(self, action, data):
        """Adds an error if a non-deactivated list is reactivated.

        This can only happen through bypassing the UI.
        """
        if not self.list_can_be_reactivated:
            self.addError("Only a deactivated list can be reactivated.")

    @action('Reactivate this Mailing List', name='reactivate_list',
            validator=reactivate_list_validator)
    def reactivate_list(self, action, data):
        getUtility(IMailingListSet).get(self.context.name).reactivate()
        self.request.response.addInfoNotification(
            "The mailing list will be reactivated within a few minutes.")
        self.next_url = canonical_url(self.context)

    def purge_list_validator(self, action, data):
        """Adds an error if the list is not safe to purge.

        This can only happen through bypassing the UI.
        """
        if not self.list_can_be_purged:
            self.addError('This list cannot be purged.')

    @action('Purge this Mailing List', name='purge_list',
            validator=purge_list_validator)
    def purge_list(self, action, data):
        getUtility(IMailingListSet).get(self.context.name).purge()
        self.request.response.addInfoNotification(
            'The mailing list has been purged.')
        self.next_url = canonical_url(self.context)

    @property
    def list_is_usable_but_not_contact_method(self):
        """The list could be the contact method for its team, but isn't.

        The list exists and is usable, but isn't set as the contact
        method.
        """

        return (self.list_is_usable and
                (self.context.preferredemail is None or
                 self.mailing_list.address !=
                 self.context.preferredemail.email))

    @property
    def mailing_list_status_message(self):
        """A status message describing the state of the mailing list.

        This status message helps a user be aware of behind-the-scenes
        processes that would otherwise manifest only as mysterious
        failures and inconsistencies.
        """
        contact_admin = (
            'Please '
            '<a href="https://answers.launchpad.net/launchpad/+faq/197">'
            'contact a Launchpad administrator</a> for further assistance.')

        if (self.mailing_list is None or
            self.mailing_list.status == MailingListStatus.PURGED):
            # Purged lists act as if they don't exist.
            return None
        elif self.mailing_list.status == MailingListStatus.REGISTERED:
            return None
        elif self.mailing_list.status in [MailingListStatus.APPROVED,
                                          MailingListStatus.CONSTRUCTING]:
            return _("This team's mailing list will be available within "
                     "a few minutes.")
        elif self.mailing_list.status == MailingListStatus.DECLINED:
            return _("The application for this team's mailing list has been "
                     'declined. ' + contact_admin)
        elif self.mailing_list.status == MailingListStatus.ACTIVE:
            return None
        elif self.mailing_list.status == MailingListStatus.DEACTIVATING:
            return _("This team's mailing list is being deactivated.")
        elif self.mailing_list.status == MailingListStatus.INACTIVE:
            return _("This team's mailing list has been deactivated.")
        elif self.mailing_list.status == MailingListStatus.FAILED:
            return _("This team's mailing list could not be created. " +
                     contact_admin)
        elif self.mailing_list.status == MailingListStatus.MODIFIED:
            return _("An update to this team's mailing list is pending "
                     "and has not yet taken effect.")
        elif self.mailing_list.status == MailingListStatus.UPDATING:
            return _("A change to this team's mailing list is currently "
                     "being applied.")
        elif self.mailing_list.status == MailingListStatus.MOD_FAILED:
            return _("This team's mailing list is in an inconsistent state "
                     'because a change to its configuration was not '
                     'applied. ' + contact_admin)
        else:
            raise AssertionError(
                "Unknown mailing list status: %s" % self.mailing_list.status)

    @property
    def initial_values(self):
        """The initial value of welcome_message comes from the database.

        :return: A dictionary containing the current welcome message.
        """
        if self.mailing_list is not None:
            return dict(welcome_message=self.mailing_list.welcome_message)
        else:
            return {}

    @property
    def list_application_can_be_cancelled(self):
        """Can this team's mailing list request be cancelled?

        It can only be cancelled if its state is REGISTERED.
        """
        return self.getListInState(MailingListStatus.REGISTERED) is not None

    @property
    def list_can_be_created(self):
        """Can a mailing list be created for this team?

        It can only be requested if there's no mailing list associated with
        this team, or the mailing list has been purged.
        """
        mailing_list = getUtility(IMailingListSet).get(self.context.name)
        return (mailing_list is None or
                mailing_list.status == MailingListStatus.PURGED)

    @property
    def list_can_be_deactivated(self):
        """Is this team's list in a state where it can be deactivated?

        The list must exist and be in the ACTIVE state.
        """
        return self.getListInState(MailingListStatus.ACTIVE) is not None

    @property
    def list_can_be_reactivated(self):
        """Is this team's list in a state where it can be reactivated?

        The list must exist and be in the INACTIVE state.
        """
        return self.getListInState(MailingListStatus.INACTIVE) is not None

    @property
    def list_can_be_purged(self):
        """Is this team's list in a state where it can be purged?

        The list must exist and be in one of the REGISTERED, DECLINED, FAILED,
        or INACTIVE states.  Further, the user doing the purging, must be
        an owner, Launchpad administrator or mailing list expert.
        """
        is_moderator = check_permission('launchpad.Moderate', self.context)
        is_mailing_list_manager = check_permission(
            'launchpad.Moderate', self.context)
        if is_moderator or is_mailing_list_manager:
            return self.getListInState(*PURGE_STATES) is not None
        else:
            return False


class TeamMailingListSubscribersView(LaunchpadView):
    """The list of people subscribed to a team's mailing list."""

    max_columns = 4

    @property
    def label(self):
        return ('Mailing list subscribers for the %s team' %
                self.context.displayname)

    @cachedproperty
    def subscribers(self):
        return BatchNavigator(
            self.context.mailing_list.getSubscribers(), self.request)

    def renderTable(self):
        html = ['<table style="max-width: 80em">']
        items = list(self.subscribers.currentBatch())
        assert len(items) > 0, (
            "Don't call this method if there are no subscribers to show.")
        # When there are more than 10 items, we use multiple columns, but
        # never more columns than self.max_columns.
        columns = int(math.ceil(len(items) / 10.0))
        columns = min(columns, self.max_columns)
        rows = int(math.ceil(len(items) / float(columns)))
        for i in range(0, rows):
            html.append('<tr>')
            for j in range(0, columns):
                index = i + (j * rows)
                if index >= len(items):
                    break
                subscriber_link = PersonFormatterAPI(items[index]).link(None)
                html.append(
                    '<td style="width: 20em">%s</td>' % subscriber_link)
            html.append('</tr>')
        html.append('</table>')
        return '\n'.join(html)


class TeamMailingListModerationView(MailingListTeamBaseView):
    """A view for moderating the held messages of a mailing list."""

    schema = Interface
    label = 'Mailing list moderation'

    def __init__(self, context, request):
        """Allow for review and moderation of held mailing list posts."""
        super(TeamMailingListModerationView, self).__init__(context, request)
        list_set = getUtility(IMailingListSet)
        self.mailing_list = list_set.get(self.context.name)
        if self.mailing_list is None:
            self.request.response.addInfoNotification(
                '%s does not have a mailing list.' % self.context.displayname)
            return self.request.response.redirect(canonical_url(self.context))

    @cachedproperty
    def hold_count(self):
        """The number of message being held for moderator approval.

        :return: Number of message being held for moderator approval.
        """
        ## return self.mailing_list.getReviewableMessages().count()
        # This looks like it would be more efficient, but it raises
        # LocationError.
        return self.held_messages.currentBatch().listlength

    @cachedproperty
    def held_messages(self):
        """All the messages being held for moderator approval.

        :return: Sequence of held messages.
        """
        results = self.mailing_list.getReviewableMessages()
        navigator = BatchNavigator(results, self.request)
        navigator.setHeadings('message', 'messages')
        return navigator

    @action('Moderate', name='moderate')
    def moderate_action(self, action, data):
        """Commits the moderation actions."""
        # We're somewhat abusing LaunchpadFormView, so the interesting bits
        # won't be in data.  Instead, get it out of the request.
        reviewable = self.hold_count
        disposed_count = 0
        actions = {}
        form = self.request.form_ng
        for field_name in form:
            if (field_name.startswith('field.') and
                field_name.endswith('')):
                # A moderated message.
                quoted_id = field_name[len('field.'):]
                message_id = unquote(quoted_id)
                actions[message_id] = form.getOne(field_name)
        messages = self.mailing_list.getReviewableMessages(
            message_id_filter=actions)
        for message in messages:
            action_name = actions[message.message_id]
            # This essentially acts like a switch statement or if/elifs.  It
            # looks the action up in a map of allowed actions, watching out
            # for bogus input.
            try:
                action, status = dict(
                    approve=(message.approve, PostedMessageStatus.APPROVED),
                    reject=(message.reject, PostedMessageStatus.REJECTED),
                    discard=(message.discard, PostedMessageStatus.DISCARDED),
                    # hold is a no-op.  Using None here avoids the bogus input
                    # trigger.
                    hold=(None, None),
                    )[action_name]
            except KeyError:
                raise UnexpectedFormData(
                    'Invalid moderation action for held message %s: %s' %
                    (message.message_id, action_name))
            if action is not None:
                disposed_count += 1
                action(self.user)
                self.request.response.addInfoNotification(
                    'Held message %s; Message-ID: %s' % (
                        status.title.lower(), message.message_id))
        still_held = reviewable - disposed_count
        if still_held > 0:
            self.request.response.addInfoNotification(
                'Messages still held for review: %d of %d' %
                (still_held, reviewable))
        self.next_url = canonical_url(self.context)


class TeamMailingListArchiveView(LaunchpadView):

    label = "Mailing list archive"

    def __init__(self, context, request):
        super(TeamMailingListArchiveView, self).__init__(context, request)
        self.messages = self._get_messages()
        cache = IJSONRequestCache(request).objects
        cache['mail'] = self.messages

    def _get_messages(self):
        # XXX: jcsackett 18-1-2012: This needs to be updated to use the
        # grackle client, once that is available, instead of returning
        # an empty list as it does now.
        return simplejson.loads('[]')


class TeamAddView(TeamFormMixin, HasRenewalPolicyMixin, LaunchpadFormView):
    """View for adding a new team."""

    schema = ITeam
    page_title = 'Register a new team in Launchpad'
    label = page_title

    custom_widget('teamowner', HiddenUserWidget)
    custom_widget(
        'renewal_policy', LaunchpadRadioWidget, orientation='vertical')
    custom_widget(
        'membership_policy', LaunchpadRadioWidgetWithDescription,
        orientation='vertical')
    custom_widget('defaultrenewalperiod', IntWidget,
        widget_class='field subordinate')

    def setUpFields(self):
        """See `LaunchpadViewForm`.

        Only Launchpad Admins get to see the visibility field.
        """
        super(TeamAddView, self).setUpFields()
        self.setUpVisibilityField()

    @action('Create Team', name='create',
        failure=LaunchpadFormView.ajax_failure_handler)
    def create_action(self, action, data):
        name = data.get('name')
        displayname = data.get('displayname')
        defaultmembershipperiod = data.get('defaultmembershipperiod')
        defaultrenewalperiod = data.get('defaultrenewalperiod')
        membership_policy = data.get('membership_policy')
        teamowner = data.get('teamowner')
        team = getUtility(IPersonSet).newTeam(
            teamowner, name, displayname, None, membership_policy,
            defaultmembershipperiod, defaultrenewalperiod)
        visibility = data.get('visibility')
        if visibility:
            team.transitionVisibility(visibility, self.user)
            del data['visibility']

        if self.request.is_ajax:
            return ''
        self.next_url = canonical_url(team)

    def _validateVisibilityConsistency(self, value):
        """See `TeamFormMixin`."""
        return None

    @property
    def _visibility(self):
        """Return the visibility for the object.

        For a new team it is PUBLIC unless otherwise set in the form data.
        """
        return PersonVisibility.PUBLIC

    @property
    def _name(self):
        return None


class SimpleTeamAddView(TeamAddView):
    """View for adding a new team using a Javascript form.

    This view is used to render a form used to create a new team. The form is
    displayed in a popup overlay and submission is done using an XHR call.
    """

    for_input = True
    schema = ITeam
    next_url = None

    field_names = [
        "name", "displayname", "visibility", "membership_policy",
        "teamowner"]

    # Use a dropdown - Javascript will be used to change this to a choice
    # popup widget.
    custom_widget(
        'membership_policy', LaunchpadDropdownWidget,
        orientation='vertical')


class ProposedTeamMembersEditView(LaunchpadFormView):
    schema = Interface
    label = 'Proposed team members'

    @action('Save changes', name='save')
    def action_save(self, action, data):
        expires = self.context.defaultexpirationdate
        statuses = dict(
            approve=TeamMembershipStatus.APPROVED,
            decline=TeamMembershipStatus.DECLINED,
            )
        target_team = self.context
        failed_joins = []
        for person in target_team.proposedmembers:
            action = self.request.form.get('action_%d' % person.id)
            status = statuses.get(action)
            if status is None:
                # The action is "hold" or no action was specified for this
                # person, which could happen if the set of proposed members
                # changed while the form was being processed.
                continue
            try:
                target_team.setMembershipData(
                    person, status, reviewer=self.user, expires=expires,
                    comment=self.request.form.get('comment'))
            except CyclicalTeamMembershipError:
                failed_joins.append(person)

        if len(failed_joins) > 0:
            failed_names = [person.displayname for person in failed_joins]
            failed_list = ", ".join(failed_names)

            mapping = dict(this_team=target_team.displayname,
                failed_list=failed_list)

            if len(failed_joins) == 1:
                self.request.response.addInfoNotification(
                    _('${this_team} is a member of the following team, so it '
                      'could not be accepted:  '
                      '${failed_list}.  You need to "Decline" that team.',
                      mapping=mapping))
            else:
                self.request.response.addInfoNotification(
                    _('${this_team} is a member of the following teams, so '
                      'they could not be accepted:  '
                      '${failed_list}.  You need to "Decline" those teams.',
                      mapping=mapping))
            self.next_url = ''
        else:
            self.next_url = self._next_url

    @property
    def page_title(self):
        return 'Proposed members of %s' % self.context.displayname

    @property
    def _next_url(self):
        return '%s/+members' % canonical_url(self.context)

    cancel_url = _next_url


class TeamBrandingView(BrandingChangeView):

    schema = ITeam
    field_names = ['icon', 'logo', 'mugshot']


class ITeamMember(Interface):
    """The interface used in the form to add a new member to a team."""

    newmember = PersonChoice(
        title=_('New member'), required=True,
        vocabulary='ValidTeamMember',
        description=_("The user or team which is going to be "
                        "added as the new member of this team."))


class TeamMemberAddView(LaunchpadFormView):

    schema = ITeamMember
    label = "Select the new member"
    # XXX: jcsackett 5.7.2011 bug=799847 The assignment of 'false' to the vars
    # below should be changed to the more appropriate False bool when we're
    # making use of the JSON cache to setup pickers, rather than assembling
    # javascript in a view macro.
    custom_widget(
        'newmember', PersonPickerWidget,
        show_assign_me_button='false', show_remove_button='false')

    @property
    def page_title(self):
        return 'Add members to %s' % self.context.displayname

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def validate(self, data):
        """Verify new member.

        This checks that the new member has some active members and is not
        already an active team member.
        """
        newmember = data.get('newmember')
        error = None
        if newmember is not None:
            if newmember.is_team and not newmember.activemembers:
                error = _("You can't add a team that doesn't have any active"
                          " members.")
            elif newmember in self.context.activemembers:
                error = _("%s (%s) is already a member of %s." % (
                    newmember.displayname, newmember.name,
                    self.context.displayname))

        if error:
            self.setFieldError("newmember", error)

    @action(u"Add Member", name="add")
    def add_action(self, action, data):
        """Add the new member to the team."""
        newmember = data['newmember']
        # If we get to this point with the member being the team itself,
        # it means the ValidTeamMemberVocabulary is broken.
        assert newmember != self.context, (
            "Can't add team to itself: %s" % newmember)

        changed, new_status = self.context.addMember(
            newmember, reviewer=self.user,
            status=TeamMembershipStatus.APPROVED)

        if new_status == TeamMembershipStatus.INVITED:
            msg = "%s has been invited to join this team." % (
                  newmember.unique_displayname)
        else:
            msg = "%s has been added as a member of this team." % (
                  newmember.unique_displayname)
        self.request.response.addInfoNotification(msg)
        # Clear the newmember widget so that the user can add another member.
        self.widgets['newmember'].setRenderedValue(None)


class TeamNavigation(PersonNavigation):

    usedfor = ITeam

    @stepthrough('+poll')
    def traverse_poll(self, name):
        return getUtility(IPollSet).getByTeamAndName(self.context, name)

    @stepthrough('+invitation')
    def traverse_invitation(self, name):
        # Return the found membership regardless of its status as we know
        # TeamInvitationView can handle memberships in statuses other than
        # INVITED.
        membership = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.context, getUtility(IPersonSet).getByName(name))
        if membership is None:
            return None
        return TeamInvitationView(membership, self.request)

    @stepthrough('+member')
    def traverse_member(self, name):
        person = getUtility(IPersonSet).getByName(name)
        if person is None:
            return None
        return getUtility(ITeamMembershipSet).getByPersonAndTeam(
            person, self.context)


class TeamBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `ITeam`."""

    @property
    def text(self):
        return smartquote('"%s" team') % self.context.displayname


class TeamMembershipSelfRenewalView(LaunchpadFormView):

    implements(IBrowserPublisher)

    # This is needed for our breadcrumbs, as there's no <browser:page>
    # declaration for this view.
    __name__ = '+self-renewal'
    schema = ITeamMembership
    field_names = []
    template = ViewPageTemplateFile(
        '../templates/teammembership-self-renewal.pt')

    @property
    def label(self):
        return "Renew membership of %s in %s" % (
            self.context.person.displayname, self.context.team.displayname)

    page_title = label

    def __init__(self, context, request):
        # Only the member himself or admins of the member (in case it's a
        # team) can see the page in which they renew memberships that are
        # about to expire.
        if not check_permission('launchpad.Edit', context.person):
            raise Unauthorized(
                "You may not renew the membership for %s." %
                context.person.displayname)
        LaunchpadFormView.__init__(self, context, request)

    def browserDefault(self, request):
        return self, ()

    @property
    def reason_for_denied_renewal(self):
        """Return text describing why the membership can't be renewed."""
        context = self.context
        ondemand = TeamMembershipRenewalPolicy.ONDEMAND
        admin = TeamMembershipStatus.ADMIN
        approved = TeamMembershipStatus.APPROVED
        date_limit = datetime.now(pytz.UTC) - timedelta(
            days=DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT)
        if context.status not in (admin, approved):
            text = "it is not active."
        elif context.team.renewal_policy != ondemand:
            text = ('<a href="%s">%s</a> is not a team that allows its '
                    'members to renew their own memberships.'
                    % (canonical_url(context.team),
                       context.team.unique_displayname))
        elif context.dateexpires is None or context.dateexpires > date_limit:
            if context.person.is_team:
                link_text = "Somebody else has already renewed it."
            else:
                link_text = (
                    "You or one of the team administrators has already "
                    "renewed it.")
            text = ('it is not set to expire in %d days or less. '
                    '<a href="%s/+members">%s</a>'
                    % (DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT,
                       canonical_url(context.team), link_text))
        else:
            raise AssertionError('This membership can be renewed!')
        return text

    @property
    def time_before_expiration(self):
        return self.context.dateexpires - datetime.now(pytz.timezone('UTC'))

    @property
    def next_url(self):
        return canonical_url(self.context.person)

    cancel_url = next_url

    @action(_("Renew"), name="renew")
    def renew_action(self, action, data):
        member = self.context.person
        # This if-statement prevents an exception if the user
        # double clicks on the submit button.
        if self.context.canBeRenewedByMember():
            member.renewTeamMembership(self.context.team)
        self.request.response.addInfoNotification(
            _("Membership renewed until ${date}.", mapping=dict(
                    date=self.context.dateexpires.strftime('%Y-%m-%d'))))


class ITeamMembershipInvitationAcknowledgementForm(Interface):
    """Schema for the form in which team admins acknowledge invitations.

    We could use ITeamMembership for that, but the acknowledger_comment is
    marked readonly there and that means LaunchpadFormView won't include the
    value of that in the data given to our action handler.
    """

    acknowledger_comment = Text(
        title=_("Comment"), required=False, readonly=False)


class TeamInvitationView(LaunchpadFormView):
    """Where team admins can accept/decline membership invitations."""

    implements(IBrowserPublisher)

    # This is needed for our breadcrumbs, as there's no <browser:page>
    # declaration for this view.
    __name__ = '+invitation'
    schema = ITeamMembershipInvitationAcknowledgementForm
    field_names = ['acknowledger_comment']
    custom_widget('acknowledger_comment', TextAreaWidget, height=5, width=60)
    template = ViewPageTemplateFile(
        '../templates/teammembership-invitation.pt')

    def __init__(self, context, request):
        # Only admins of the invited team can see the page in which they
        # approve/decline invitations.
        if not check_permission('launchpad.Edit', context.person):
            raise Unauthorized(
                "Only team administrators can approve/decline invitations "
                "sent to this team.")
        LaunchpadFormView.__init__(self, context, request)

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return "Make %s a member of %s" % (
            self.context.person.displayname, self.context.team.displayname)

    @property
    def page_title(self):
        return smartquote(
            '"%s" team invitation') % self.context.team.displayname

    def browserDefault(self, request):
        return self, ()

    @property
    def next_url(self):
        return canonical_url(self.context.person)

    @action(_("Accept"), name="accept")
    def accept_action(self, action, data):
        if self.context.status != TeamMembershipStatus.INVITED:
            self.request.response.addInfoNotification(
                _("This invitation has already been processed."))
            return
        member = self.context.person
        try:
            member.acceptInvitationToBeMemberOf(
                self.context.team, data['acknowledger_comment'])
        except CyclicalTeamMembershipError:
            self.request.response.addInfoNotification(
                _("This team may not be added to ${that_team} because it is "
                  "a member of ${this_team}.",
                  mapping=dict(
                      that_team=self.context.team.displayname,
                      this_team=member.displayname)))
        else:
            self.request.response.addInfoNotification(
                _("This team is now a member of ${team}.", mapping=dict(
                    team=self.context.team.displayname)))

    @action(_("Decline"), name="decline")
    def decline_action(self, action, data):
        if self.context.status != TeamMembershipStatus.INVITED:
            self.request.response.addInfoNotification(
                _("This invitation has already been processed."))
            return
        member = self.context.person
        member.declineInvitationToBeMemberOf(
            self.context.team, data['acknowledger_comment'])
        self.request.response.addInfoNotification(
            _("Declined the invitation to join ${team}", mapping=dict(
                  team=self.context.team.displayname)))

    @action(_("Cancel"), name="cancel")
    def cancel_action(self, action, data):
        # Simply redirect back.
        pass


class TeamMenuMixin(PPANavigationMenuMixIn, CommonMenuLinks):
    """Base class of team menus.

    You will need to override the team attribute if your menu subclass
    has the view as its context object.
    """

    def profile(self):
        target = ''
        text = 'Overview'
        return Link(target, text)

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        target = '+edit'
        text = 'Change details'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def branding(self):
        target = '+branding'
        text = 'Change branding'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Owner')
    def reassign(self):
        target = '+reassign'
        text = 'Change owner'
        summary = 'Change the owner of the team'
        return Link(target, text, summary, icon='edit')

    def administer(self):
        target = '+review'
        text = 'Administer'
        # Team owners and admins have launchpad.Moderate on ITeam, but we
        # do not want them to see this link because it is for Lp admins
        # and registry experts.
        checker = ModerateByRegistryExpertsOrAdmins(self)
        if self.user is None:
            enabled = False
        else:
            enabled = checker.checkAuthenticated(IPersonRoles(self.user))
        summary = 'Administer this team on behalf of a user'
        return Link(target, text, summary, icon='edit', enabled=enabled)

    @enabled_with_permission('launchpad.Moderate')
    def delete(self):
        target = '+delete'
        text = 'Delete'
        summary = 'Delete this team'
        return Link(target, text, summary, icon='trash-icon')

    @enabled_with_permission('launchpad.View')
    def members(self):
        target = '+members'
        text = 'Show all members'
        return Link(target, text, icon='team')

    @enabled_with_permission('launchpad.Edit')
    def received_invitations(self):
        target = '+invitations'
        text = 'Show received invitations'
        return Link(target, text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def add_member(self):
        target = '+addmember'
        text = 'Add member'
        return Link(target, text, icon='add')

    @enabled_with_permission('launchpad.Edit')
    def proposed_members(self):
        target = '+editproposedmembers'
        text = 'Approve or decline members'
        return Link(target, text, icon='add')

    def add_my_teams(self):
        target = '+add-my-teams'
        text = 'Add one of my teams'
        enabled = True
        restricted = TeamMembershipPolicy.RESTRICTED
        if self.person.membership_policy == restricted:
            # This is a restricted team; users can't join.
            enabled = False
        return Link(target, text, icon='add', enabled=enabled)

    def memberships(self):
        target = '+participation'
        text = 'Show team participation'
        return Link(target, text, icon='info')

    @enabled_with_permission('launchpad.View')
    def mugshots(self):
        target = '+mugshots'
        text = 'Show member photos'
        return Link(target, text, icon='team')

    def polls(self):
        target = '+polls'
        text = 'Show polls'
        return Link(target, text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def add_poll(self):
        target = '+newpoll'
        text = 'Create a poll'
        return Link(target, text, icon='add')

    @enabled_with_permission('launchpad.Edit')
    def editemail(self):
        target = '+contactaddress'
        text = 'Set contact address'
        summary = (
            'The address Launchpad uses to contact %s' %
            self.person.displayname)
        return Link(target, text, summary, icon='edit')

    @enabled_with_permission('launchpad.Moderate')
    def configure_mailing_list(self):
        target = '+mailinglist'
        mailing_list = self.person.mailing_list
        if mailing_list is not None:
            text = 'Configure mailing list'
            icon = 'edit'
        else:
            text = 'Create a mailing list'
            icon = 'add'
        summary = (
            'The mailing list associated with %s' % self.context.displayname)
        return Link(target, text, summary, icon=icon)

    @enabled_with_active_mailing_list
    @enabled_with_permission('launchpad.Edit')
    def moderate_mailing_list(self):
        target = '+mailinglist-moderate'
        text = 'Moderate mailing list'
        summary = (
            'The mailing list associated with %s' % self.context.displayname)
        return Link(target, text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def editlanguages(self):
        target = '+editlanguages'
        text = 'Set preferred languages'
        return Link(target, text, icon='edit')

    def leave(self):
        enabled = True
        if not userIsActiveTeamMember(self.person):
            enabled = False
        if self.person.teamowner == self.user:
            # The owner cannot leave his team.
            enabled = False
        target = '+leave'
        text = 'Leave the Team'
        icon = 'remove'
        return Link(target, text, icon=icon, enabled=enabled)

    def join(self):
        enabled = True
        person = self.person
        if userIsActiveTeamMember(person):
            enabled = False
        elif (self.person.membership_policy ==
              TeamMembershipPolicy.RESTRICTED):
            # This is a restricted team; users can't join.
            enabled = False
        target = '+join'
        text = 'Join the team'
        icon = 'add'
        return Link(target, text, icon=icon, enabled=enabled)

    def upcomingwork(self):
        target = '+upcomingwork'
        text = 'Upcoming work for this team'
        enabled = False
        if getFeatureFlag('registry.upcoming_work_view.enabled'):
            enabled = True
        return Link(target, text, icon='team', enabled=enabled)


class TeamOverviewMenu(ApplicationMenu, TeamMenuMixin, HasRecipesMenuMixin):

    usedfor = ITeam
    facet = 'overview'
    links = [
        'edit',
        'branding',
        'members',
        'mugshots',
        'add_member',
        'proposed_members',
        'memberships',
        'received_invitations',
        'editemail',
        'configure_mailing_list',
        'moderate_mailing_list',
        'editlanguages',
        'polls',
        'add_poll',
        'join',
        'leave',
        'add_my_teams',
        'reassign',
        'projects',
        'activate_ppa',
        'maintained',
        'ppa',
        'related_software_summary',
        'view_recipes',
        'subscriptions',
        'structural_subscriptions',
        'upcomingwork',
        ]


class TeamOverviewNavigationMenu(NavigationMenu, TeamMenuMixin):
    """A top-level menu for navigation within a Team."""

    usedfor = ITeam
    facet = 'overview'
    links = ['profile', 'polls', 'members', 'ppas']


class TeamMembershipView(LaunchpadView):
    """The view behind ITeam/+members."""

    page_title = 'Members'

    @cachedproperty
    def label(self):
        return smartquote('Members of "%s"' % self.context.displayname)

    @cachedproperty
    def active_memberships(self):
        """Current members of the team."""
        return ActiveBatchNavigator(
            self.context.member_memberships, self.request)

    @cachedproperty
    def inactive_memberships(self):
        """Former members of the team."""
        return InactiveBatchNavigator(
            self.context.getInactiveMemberships(), self.request)

    @cachedproperty
    def invited_memberships(self):
        """Other teams invited to become members of this team."""
        return list(self.context.getInvitedMemberships())

    @cachedproperty
    def proposed_memberships(self):
        """Users who have requested to join this team."""
        return list(self.context.getProposedMemberships())

    @property
    def have_pending_members(self):
        return self.proposed_memberships or self.invited_memberships


class TeamIndexView(PersonIndexView, TeamJoinMixin):
    """The view class for the +index page.

    This class is needed, so an action menu that only applies to
    teams can be displayed without showing up on the person index page.
    """

    @property
    def super_teams(self):
        """Return only the super teams that the viewer is able to see."""
        return [
            team for team in self.context.super_teams
            if check_permission('launchpad.View', team)]

    @property
    def can_show_subteam_portlet(self):
        """Only show the subteam portlet if there is info to display.

        Either the team is a member of another team, or there are
        invitations to join a team, and the owner needs to see the
        link so that the invitation can be accepted.
        """
        try:
            return (len(self.super_teams) > 0
                    or (self.context.open_membership_invitations
                        and check_permission('launchpad.Edit', self.context)))
        except AttributeError as e:
            raise AssertionError(e)

    @property
    def visibility_info(self):
        if self.context.visibility == PersonVisibility.PRIVATE:
            return 'Private team'
        else:
            return 'Public team'

    @property
    def visibility_portlet_class(self):
        """The portlet class for team visibility."""
        if self.context.visibility == PersonVisibility.PUBLIC:
            return 'portlet'
        return 'portlet private'

    @property
    def add_member_step_title(self):
        """A string for setup_add_member_handler with escaped quotes."""
        vocabulary_registry = getVocabularyRegistry()
        vocabulary = vocabulary_registry.get(self.context, 'ValidTeamMember')
        return vocabulary.step_title.replace("'", "\\'").replace('"', '\\"')


class TeamJoinForm(Interface):
    """Schema for team join."""
    mailinglist_subscribe = Bool(
        title=_("Subscribe me to this team's mailing list"),
        required=True, default=True)


class TeamJoinView(LaunchpadFormView, TeamJoinMixin):
    """A view class for joining a team."""

    schema = TeamJoinForm

    @property
    def label(self):
        return 'Join ' + self.context.displayname

    page_title = label

    def setUpWidgets(self):
        super(TeamJoinView, self).setUpWidgets()
        if 'mailinglist_subscribe' in self.field_names:
            widget = self.widgets['mailinglist_subscribe']
            widget.setRenderedValue(self.user_wants_list_subscriptions)

    @property
    def field_names(self):
        """See `LaunchpadFormView`.

        If the user can subscribe to the mailing list then include the
        mailinglist subscription checkbox otherwise remove it.
        """
        if self.user_can_subscribe_to_list:
            return ['mailinglist_subscribe']
        else:
            return []

    @property
    def join_allowed(self):
        """Is the logged in user allowed to join this team?

        The answer is yes if this team's membership policy is not RESTRICTED
        and this team's visibility is either None or PUBLIC.
        """
        # Joining a moderated team will put you on the proposed_members
        # list. If it is a private team, you are not allowed to view the
        # proposed_members attribute until you are an active member;
        # therefore, it would look like the join button is broken. Either
        # private teams should always have a restricted membership policy,
        # or we need a more complicated permission model.
        if not (self.context.visibility is None
                or self.context.visibility == PersonVisibility.PUBLIC):
            return False

        restricted = TeamMembershipPolicy.RESTRICTED
        return self.context.membership_policy != restricted

    @property
    def user_can_request_to_join(self):
        """Can the logged in user request to join this team?

        The user can request if he's allowed to join this team and if he's
        not yet an active member of this team.
        """
        if not self.join_allowed:
            return False
        return not (self.user_is_active_member or
                    self.user_is_proposed_member)

    @property
    def user_wants_list_subscriptions(self):
        """Is the user interested in subscribing to mailing lists?"""
        return (self.user.mailing_list_auto_subscribe_policy !=
                MailingListAutoSubscribePolicy.NEVER)

    @property
    def team_is_moderated(self):
        """Is this team a moderated team?

        Return True if the team's membership policy is MODERATED.
        """
        policy = self.context.membership_policy
        return policy == TeamMembershipPolicy.MODERATED

    @property
    def next_url(self):
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @action(_("Join"), name="join")
    def action_save(self, action, data):
        response = self.request.response

        if self.user_can_request_to_join:
            # Shut off mailing list auto-subscription - we want direct
            # control over it.
            self.user.join(self.context, may_subscribe_to_list=False)

            if self.team_is_moderated:
                response.addInfoNotification(
                    _('Your request to join ${team} is awaiting '
                      'approval.',
                      mapping={'team': self.context.displayname}))
            else:
                response.addInfoNotification(
                    _('You have successfully joined ${team}.',
                      mapping={'team': self.context.displayname}))
            if data.get('mailinglist_subscribe', False):
                self._subscribeToList(response)

        else:
            response.addErrorNotification(
                _('You cannot join ${team}.',
                  mapping={'team': self.context.displayname}))

    def _subscribeToList(self, response):
        """Subscribe the user to the team's mailing list."""

        if self.user_can_subscribe_to_list:
            # 'user_can_subscribe_to_list' should have dealt with
            # all of the error cases.
            self.context.mailing_list.subscribe(self.user)

            if self.team_is_moderated:
                response.addInfoNotification(
                    _('Your mailing list subscription is '
                      'awaiting approval.'))
            else:
                response.addInfoNotification(
                    structured(
                        _("You have been subscribed to this "
                          "team&#x2019;s mailing list.")))
        else:
            # A catch-all case, perhaps from stale or mangled
            # form data.
            response.addErrorNotification(
                _('Mailing list subscription failed.'))


class TeamAddMyTeamsView(LaunchpadFormView):
    """Propose/add to this team any team that you're an administrator of."""

    page_title = 'Propose/add one of your teams to another one'
    custom_widget('teams', LabeledMultiCheckBoxWidget)

    def initialize(self):
        context = self.context
        if context.membership_policy == TeamMembershipPolicy.MODERATED:
            self.label = 'Propose these teams as members'
        else:
            self.label = 'Add these teams to %s' % context.displayname
        self.next_url = canonical_url(context)
        super(TeamAddMyTeamsView, self).initialize()

    def setUpFields(self):
        terms = []
        for team in self.candidate_teams:
            text = structured(
                '<a href="%s">%s</a>', canonical_url(team), team.displayname)
            terms.append(SimpleTerm(team, team.name, text))
        self.form_fields = FormFields(
            List(__name__='teams',
                 title=_(''),
                 value_type=Choice(vocabulary=SimpleVocabulary(terms)),
                 required=False),
            render_context=self.render_context)

    def setUpWidgets(self, context=None):
        super(TeamAddMyTeamsView, self).setUpWidgets(context)
        self.widgets['teams'].display_label = False

    @cachedproperty
    def candidate_teams(self):
        """Return the set of teams that can be added/proposed for the context.

        We return only teams that the user can administer, that aren't already
        a member in the context or that the context isn't a member of. (Of
        course, the context is also omitted.)
        """
        candidates = []
        for team in self.user.getAdministratedTeams():
            if team == self.context:
                continue
            elif team in self.context.activemembers:
                # The team is already a member of the context object.
                continue
            elif self.context.hasParticipationEntryFor(team):
                # The context object is a member/submember of the team.
                continue
            candidates.append(team)
        return candidates

    @property
    def cancel_url(self):
        """The return URL."""
        return canonical_url(self.context)

    def validate(self, data):
        if len(data.get('teams', [])) == 0:
            self.setFieldError('teams',
                               'Please select the team(s) you want to be '
                               'member(s) of this team.')

    def hasCandidates(self, action):
        """Return whether the user has teams to propose."""
        return len(self.candidate_teams) > 0

    @action(_("Continue"), name="continue", condition=hasCandidates)
    def continue_action(self, action, data):
        """Make the selected teams join this team."""
        context = self.context
        is_admin = check_permission('launchpad.Admin', context)
        membership_set = getUtility(ITeamMembershipSet)
        proposed_team_names = []
        added_team_names = []
        accepted_invite_team_names = []
        membership_set = getUtility(ITeamMembershipSet)
        for team in data['teams']:
            membership = membership_set.getByPersonAndTeam(team, context)
            if (membership is not None
                and membership.status == TeamMembershipStatus.INVITED):
                team.acceptInvitationToBeMemberOf(
                    context,
                    'Accepted an already pending invitation while trying to '
                    'propose the team for membership.')
                accepted_invite_team_names.append(team.displayname)
            elif is_admin:
                context.addMember(team, reviewer=self.user)
                added_team_names.append(team.displayname)
            else:
                team.join(context, requester=self.user)
                membership = membership_set.getByPersonAndTeam(team, context)
                if membership.status == TeamMembershipStatus.PROPOSED:
                    proposed_team_names.append(team.displayname)
                elif membership.status == TeamMembershipStatus.APPROVED:
                    added_team_names.append(team.displayname)
                else:
                    raise AssertionError(
                        'Unexpected membership status (%s) for %s.'
                        % (membership.status.name, team.name))
        full_message = ''
        for team_names, message in (
            (proposed_team_names, 'proposed to this team.'),
            (added_team_names, 'added to this team.'),
            (accepted_invite_team_names,
             'added to this team because of an existing invite.'),
            ):
            if len(team_names) == 0:
                continue
            elif len(team_names) == 1:
                verb = 'has been'
                team_string = team_names[0]
            elif len(team_names) > 1:
                verb = 'have been'
                team_string = (
                    ', '.join(team_names[:-1]) + ' and ' + team_names[-1])
            full_message += '%s %s %s' % (team_string, verb, message)
        self.request.response.addInfoNotification(full_message)


class TeamLeaveView(LaunchpadFormView, TeamJoinMixin):
    schema = Interface

    @property
    def is_private_team(self):
        return self.context.visibility == PersonVisibility.PRIVATE

    @property
    def label(self):
        return 'Leave ' + self.context.displayname

    page_title = label

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def next_url(self):
        if self.is_private_team:
            return canonical_url(self.user)
        else:
            return self.cancel_url

    @action(_("Leave"), name="leave")
    def action_save(self, action, data):
        if self.user_can_request_to_leave:
            self.user.leave(self.context)
            if self.is_private_team:
                self.request.response.addNotification(
                    "You are no longer a member of private team %s "
                    "and are not authorised to view the team."
                        % self.context.displayname)


class TeamReassignmentView(ObjectReassignmentView):

    ownerOrMaintainerAttr = 'teamowner'
    schema = ITeamReassignment

    def __init__(self, context, request):
        super(TeamReassignmentView, self).__init__(context, request)
        self.callback = self._afterOwnerChange
        self.teamdisplayname = self.contextName
        self._next_url = canonical_url(self.context)

    def validateOwner(self, new_owner):
        """Display error if the owner is not valid.

        Called by ObjectReassignmentView.validate().
        """
        if self.context.inTeam(new_owner):
            path = self.context.findPathToTeam(new_owner)
            if len(path) == 1:
                relationship = 'a direct member'
                path_string = ''
            else:
                relationship = 'an indirect member'
                full_path = [self.context] + path
                path_string = '(%s)' % '&rArr;'.join(
                    team.displayname for team in full_path)
            error = structured(
                'Circular team memberships are not allowed. '
                '%(new)s cannot be the new team owner, since %(context)s '
                'is %(relationship)s of %(new)s. '
                '<span style="white-space: nowrap">%(path)s</span>'
                % dict(new=new_owner.displayname,
                        context=self.context.displayname,
                        relationship=relationship,
                        path=path_string))
            self.setFieldError(self.ownerOrMaintainerName, error)

    @property
    def contextName(self):
        return self.context.displayname

    @property
    def next_url(self):
        return self._next_url

    def _afterOwnerChange(self, team, oldOwner, newOwner):
        """Add the new and the old owners as administrators of the team.

        When a user creates a new team, he is added as an administrator of
        that team. To be consistent with this, we must make the new owner an
        administrator of the team. This rule is ignored only if the new owner
        is an inactive member of the team, as that means he's not interested
        in being a member. The same applies to the old owner.
        """
        # Both new and old owners won't be added as administrators of the team
        # only if they're inactive members. If they're either active or
        # proposed members they'll be made administrators of the team.
        if newOwner not in team.inactivemembers:
            team.addMember(
                newOwner, reviewer=self.user,
                status=TeamMembershipStatus.ADMIN, force_team_add=True)
        if oldOwner not in team.inactivemembers:
            team.addMember(
                oldOwner, reviewer=self.user,
                status=TeamMembershipStatus.ADMIN, force_team_add=True)

        # If the current logged in user cannot see the team anymore as a
        # result of the ownership change, we don't want them to get a nasty
        # error page. So we redirect to launchpad.net with a notification.
        clear_cache()
        if not check_permission('launchpad.LimitedView', team):
            self.request.response.addNotification(
                "The owner of team %s was successfully changed but you are "
                "now no longer authorised to view the team."
                    % self.teamdisplayname)
            self._next_url = canonical_url(self.user)


class ITeamIndexMenu(Interface):
    """A marker interface for the +index navigation menu."""


class ITeamEditMenu(Interface):
    """A marker interface for the edit navigation menu."""


classImplements(TeamIndexView, ITeamIndexMenu)
classImplements(TeamEditView, ITeamEditMenu)


class TeamNavigationMenuBase(NavigationMenu, TeamMenuMixin):

    @property
    def person(self):
        """Override CommonMenuLinks since the view is the context."""
        return self.context.context


class TeamIndexMenu(TeamNavigationMenuBase):
    """A menu for different aspects of editing a team."""

    usedfor = ITeamIndexMenu
    facet = 'overview'
    title = 'Change team'
    links = ('edit', 'administer', 'delete', 'join', 'add_my_teams', 'leave')


class TeamEditMenu(TeamNavigationMenuBase):
    """A menu for different aspects of editing a team."""

    usedfor = ITeamEditMenu
    facet = 'overview'
    title = 'Change team'
    links = ('branding', 'editlanguages', 'reassign', 'editemail')


class TeamMugshotView(LaunchpadView):
    """A view for the team mugshot (team photo) page"""

    label = "Member photos"
    batch_size = config.launchpad.mugshot_batch_size

    def initialize(self):
        """Cache images to avoid dying from a million cuts."""
        getUtility(IPersonSet).cacheBrandingForPeople(
            self.members.currentBatch())

    @cachedproperty
    def members(self):
        """Get a batch of all members in the team."""
        batch_nav = BatchNavigator(
            self.context.allmembers, self.request, size=self.batch_size)
        return batch_nav
