# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""People Merge related wiew classes."""

__metaclass__ = type

__all__ = [
    'AdminPeopleMergeView',
    'AdminTeamMergeView',
    'DeleteTeamView',
    'FinishedPeopleMergeRequestView',
    'RequestPeopleMergeMultipleEmailsView',
    'RequestPeopleMergeView',
    ]


from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.code.interfaces.branchcollection import IAllBranches
from lp.registry.interfaces.mailinglist import (
    MailingListStatus,
    PURGE_STATES,
    )
from lp.registry.interfaces.person import (
    IAdminPeopleMergeSchema,
    IAdminTeamMergeSchema,
    IPersonSet,
    IRequestPeopleMerge,
    )
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.propertycache import cachedproperty
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import ILoginTokenSet
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.soyuz.enums import ArchiveStatus
from lp.soyuz.interfaces.archive import IArchiveSet


class ValidatingMergeView(LaunchpadFormView):

    def validate(self, data):
        """Check that user is not attempting to merge a person into itself."""
        dupe_person = data.get('dupe_person')
        target_person = data.get('target_person') or self.user
        if dupe_person is None:
            self.setFieldError(
                'dupe_person', 'The duplicate is not a valid person or team.')
        else:
            if dupe_person == target_person:
                self.addError(_("You can't merge ${name} into itself.",
                      mapping=dict(name=dupe_person.name)))
            dupe_person_ppas = getUtility(IArchiveSet).getPPAOwnedByPerson(
                dupe_person, statuses=[ArchiveStatus.ACTIVE,
                                       ArchiveStatus.DELETING])
            if dupe_person_ppas is not None:
                self.addError(_(
                    "${name} has a PPA that must be deleted before it "
                    "can be merged. It may take ten minutes to remove the "
                    "deleted PPA's files.",
                    mapping=dict(name=dupe_person.name)))
            all_branches = getUtility(IAllBranches)
            if not all_branches.ownedBy(dupe_person).isPrivate().is_empty():
                self.addError(
                    _("${name} owns private branches that must be "
                      "deleted or transferred to another owner first.",
                    mapping=dict(name=dupe_person.name)))
            if dupe_person.isMergePending():
                self.addError(_("${name} is already queued for merging.",
                      mapping=dict(name=dupe_person.name)))
        if target_person is not None and target_person.isMergePending():
            self.addError(_("${name} is already queued for merging.",
                  mapping=dict(name=target_person.name)))


class AdminMergeBaseView(ValidatingMergeView):
    """Base view for the pages where admins can merge people/teams."""

    page_title = 'Merge Launchpad accounts'
    # Both subclasses share the same template so we need to define these
    # variables (which are used in the template) here rather than on
    # subclasses.
    should_confirm_email_reassignment = False
    should_confirm_member_deactivation = False
    merge_message = _(
        'A merge is queued and is expected to complete in a few minutes.')

    dupe_person_emails = ()
    dupe_person = None
    target_person = None
    delete = False

    @property
    def cancel_url(self):
        return canonical_url(getUtility(IPersonSet))

    @property
    def success_url(self):
        return canonical_url(self.target_person)

    def render(self):
        # Subclasses may define other actions that they will render manually
        # only in certain circunstances, so don't include them in the list of
        # actions to be rendered.
        self.actions = [self.merge_action]
        return super(AdminMergeBaseView, self).render()

    def setUpPeople(self, data):
        """Store the people to be merged in instance variables.

        Also store all emails associated with the dupe account in an
        instance variable.
        """
        emailset = getUtility(IEmailAddressSet)
        self.dupe_person = data['dupe_person']
        self.target_person = data.get('target_person', None)
        self.dupe_person_emails = emailset.getByPerson(self.dupe_person)

    def doMerge(self, data):
        """Merge the two person/team entries specified in the form.

        Before merging this moves each email address of the duplicate person
        to the target person, and resets them to `NEW`.
        """
        if not self.dupe_person.is_team:
            # Transfer user email addresses. Team addresses will be deleted.
            for email in self.dupe_person_emails:
                # EmailAddress.person is a readonly field, so we need to
                # remove the security proxy here.
                naked_email = removeSecurityProxy(email)
                naked_email.personID = self.target_person.id
                naked_email.status = EmailAddressStatus.NEW
        getUtility(IPersonSet).mergeAsync(
            self.dupe_person, self.target_person, reviewer=self.user,
            delete=self.delete, requester=self.user)
        self.request.response.addInfoNotification(self.merge_message)
        self.next_url = self.success_url


class AdminPeopleMergeView(AdminMergeBaseView):
    """A view for merging two Persons.

    If the duplicate person has any email addresses associated with we'll
    ask the user to confirm that it's okay to reassign these emails to the
    other account.  We do it because the fact that the dupe person still has
    email addresses is a possible indication that the admin may be merging
    the wrong person.
    """

    label = "Merge Launchpad people"
    schema = IAdminPeopleMergeSchema

    @action('Merge', name='merge')
    def merge_action(self, action, data):
        """Merge the two person entries specified in the form.

        If we're merging a person which has email addresses associated with
        we'll ask for confirmation before actually performing the merge.
        """
        self.setUpPeople(data)
        if not self.dupe_person_emails.is_empty():
            # We're merging a person which has one or more email addresses,
            # so we better warn the admin doing the operation and have him
            # check the emails that will be reassigned to ensure he's not
            # doing anything stupid.
            self.should_confirm_email_reassignment = True
            return
        self.doMerge(data)

    @action('Reassign E-mails and Merge', name='reassign_emails_and_merge')
    def reassign_emails_and_merge_action(self, action, data):
        """Reassign emails of the person to be merged and merge them."""
        self.setUpPeople(data)
        self.doMerge(data)


class AdminTeamMergeView(AdminMergeBaseView):
    """A view for merging two Teams.

    The duplicate team cannot be associated with a mailing list and if it
    has any active members we'll ask for confirmation from the user as we'll
    need to deactivate all members before we can do the merge.
    """

    label = "Merge Launchpad teams"
    schema = IAdminTeamMergeSchema

    def hasMailingList(self, team):
        unused_states = [state for state in PURGE_STATES]
        unused_states.append(MailingListStatus.PURGED)
        return (
            team.mailing_list is not None
            and team.mailing_list.status not in unused_states)

    @cachedproperty
    def registry_experts(self):
        return getUtility(ILaunchpadCelebrities).registry_experts

    def validate(self, data):
        """Check there are no mailing lists associated with the dupe team."""
        # If errors have already been discovered there is no need to continue,
        # especially since some of our expected data may be missing in the
        # case of user-entered invalid data.
        if len(self.errors) > 0:
            return

        super(AdminTeamMergeView, self).validate(data)
        dupe_team = data['dupe_person']
        # We cannot merge the teams if there is a mailing list on the
        # duplicate person, unless that mailing list is purged.
        if self.hasMailingList(dupe_team):
            self.addError(_(
                "${name} is associated with a Launchpad mailing list; we "
                "can't merge it.", mapping=dict(name=dupe_team.name)))

    @action('Merge', name='merge')
    def merge_action(self, action, data):
        """Merge the two team entries specified in the form.

        A confirmation will be asked if the team we're merging from still
        has active members, as in that case we'll have to deactivate all
        members first.
        """
        self.setUpPeople(data)
        if not self.dupe_person.activemembers.is_empty():
            # Merging teams with active members is not possible, so we'll
            # ask the admin if he wants to deactivate all members and then
            # merge.
            self.should_confirm_member_deactivation = True
            return
        super(AdminTeamMergeView, self).doMerge(data)

    @action('Deactivate Members and Merge',
            name='deactivate_members_and_merge')
    def deactivate_members_and_merge_action(self, action, data):
        """Deactivate all members of the team to be merged and merge them."""
        self.setUpPeople(data)
        super(AdminTeamMergeView, self).doMerge(data)


class DeleteTeamView(AdminTeamMergeView):
    """A view that deletes a team by merging it with Registry experts."""

    page_title = 'Delete'
    field_names = ['dupe_person']
    merge_message = _('The team is queued to be deleted.')

    @property
    def label(self):
        return 'Delete %s' % self.context.displayname

    def __init__(self, context, request):
        super(DeleteTeamView, self).__init__(context, request)
        if ('field.dupe_person' in self.request.form):
            # These fields have fixed values and are managed by this method.
            # The user has crafted a request to gain ownership of the dupe
            # team's assets.
            self.addError('Unable to process submitted data.')
        elif 'field.actions.delete' in self.request.form:
            # In the case of deleting a team, the form values are always
            # the context team, and the registry experts team. These values
            # are injected during __init__ because the base classes assume the
            # values are submitted. The validations performed by the base
            # classes are still required to ensure the team can be deleted.
            self.request.form.update(self.default_values)
        else:
            # Show the page explaining the action.
            pass

    @property
    def default_values(self):
        return {
            'field.dupe_person': self.context.name,
            'field.delete': True,
            }

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def success_url(self):
        return canonical_url(getUtility(IPersonSet))

    @property
    def has_mailing_list(self):
        return self.hasMailingList(self.context)

    def canDelete(self, data):
        return not self.has_mailing_list

    @action('Delete', name='delete', condition=canDelete)
    def merge_action(self, action, data):
        base = super(DeleteTeamView, self)
        self.delete = True
        base.deactivate_members_and_merge_action.success(data)


class FinishedPeopleMergeRequestView(LaunchpadView):
    """A simple view for a page where we only tell the user that we sent the
    email with further instructions to complete the merge.

    This view is used only when the dupe account has a single email address.
    """

    page_title = 'Merge request sent'

    def initialize(self):
        user = getUtility(ILaunchBag).user
        try:
            dupe_id = int(self.request.get('dupe'))
        except (ValueError, TypeError):
            self.request.response.redirect(canonical_url(user))
            return

        dupe_account = getUtility(IPersonSet).get(dupe_id)
        results = getUtility(IEmailAddressSet).getByPerson(dupe_account)

        result_count = results.count()
        if not result_count:
            # The user came back to visit this page with nothing to
            # merge, so we redirect him away to somewhere useful.
            self.request.response.redirect(canonical_url(user))
            return
        assert result_count == 1
        # Need to remove the security proxy because the dupe account may have
        # hidden email addresses.
        self.dupe_email = removeSecurityProxy(results[0]).email

    def render(self):
        if self.dupe_email:
            return LaunchpadView.render(self)
        else:
            return ''


class RequestPeopleMergeMultipleEmailsView(LaunchpadView):
    """Merge request view when dupe account has multiple email addresses."""

    label = 'Merge Launchpad accounts'
    page_title = label

    def __init__(self, context, request):
        super(RequestPeopleMergeMultipleEmailsView, self).__init__(
            context, request)
        self.form_processed = False
        self.dupe = None
        self.notified_addresses = []

    def processForm(self):
        dupe = self.request.form.get('dupe')
        if dupe is None:
            # We just got redirected to this page and we don't have the dupe
            # hidden field in request.form.
            dupe = self.request.get('dupe')
            if dupe is None:
                return

        self.dupe = getUtility(IPersonSet).get(int(dupe))
        emailaddrset = getUtility(IEmailAddressSet)
        self.dupeemails = emailaddrset.getByPerson(self.dupe)

        if self.request.method != "POST":
            return

        login = getUtility(ILaunchBag).login
        logintokenset = getUtility(ILoginTokenSet)

        email_addresses = []
        if self.email_hidden:
            # If the email addresses are hidden we must send a merge request
            # to each of them.  But first we've got to remove the security
            # proxy so we can get to them.
            email_addresses = [removeSecurityProxy(email).email
                               for email in self.dupeemails]
        else:
            # Otherwise we send a merge request only to the ones the user
            # selected.
            emails = self.request.form.get("selected")
            if emails is not None:
                # We can have multiple email addresses selected, and in this
                # case emails will be a list. Otherwise it will be a string
                # and we need to make a list with that value to use in the for
                # loop.
                if not isinstance(emails, list):
                    emails = [emails]

                for emailaddress in emails:
                    email = emailaddrset.getByEmail(emailaddress)
                    if email is None or email not in self.dupeemails:
                        # The dupe person has changes his email addresses.
                        # See bug 239838.
                        self.request.response.addNotification(
                            "An address was removed from the duplicate "
                            "account while you were making this merge "
                            "request. Select again.")
                        return
                    email_addresses.append(emailaddress)

        for emailaddress in email_addresses:
            token = logintokenset.new(
                self.user, login, emailaddress, LoginTokenType.ACCOUNTMERGE)
            token.sendMergeRequestEmail()
            self.notified_addresses.append(emailaddress)
        self.form_processed = True

    @property
    def cancel_url(self):
        """Cancel URL."""
        return canonical_url(self.user)

    @property
    def email_hidden(self):
        """Does the duplicate account hide email addresses?"""
        return self.dupe.hide_email_addresses


class RequestPeopleMergeView(ValidatingMergeView):
    """The view for the page where the user asks a merge of two accounts.

    If the dupe account have only one email address we send a message to that
    address and then redirect the user to other page saying that everything
    went fine. Otherwise we redirect the user to another page where we list
    all email addresses owned by the dupe account and the user selects which
    of those (s)he wants to claim.
    """

    label = 'Merge Launchpad accounts'
    page_title = label
    schema = IRequestPeopleMerge

    @property
    def cancel_url(self):
        return canonical_url(getUtility(IPersonSet))

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        dupeaccount = data['dupe_person']
        if dupeaccount == self.user:
            # Please, don't try to merge you into yourself.
            return

        emails = getUtility(IEmailAddressSet).getByPerson(dupeaccount)
        emails_count = emails.count()
        if emails_count > 1:
            # The dupe account have more than one email address. Must redirect
            # the user to another page to ask which of those emails (s)he
            # wants to claim.
            self.next_url = '+requestmerge-multiple?dupe=%d' % dupeaccount.id
            return

        assert emails_count == 1
        email = emails[0]
        login = getUtility(ILaunchBag).login
        logintokenset = getUtility(ILoginTokenSet)
        # Need to remove the security proxy because the dupe account may have
        # hidden email addresses.
        token = logintokenset.new(
            self.user, login, removeSecurityProxy(email).email,
            LoginTokenType.ACCOUNTMERGE)
        token.sendMergeRequestEmail()
        self.next_url = './+mergerequest-sent?dupe=%d' % dupeaccount.id
