# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'TeamMembershipBreadcrumb',
    'TeamInvitationsView',
    'TeamMembershipEditView',
    ]


from datetime import datetime

import pytz
from zope.formlib import form
from zope.formlib.interfaces import InputErrors
from zope.formlib.widget import CustomWidgetFactory
from zope.schema import Date

from lp import _
from lp.app.errors import UnexpectedFormData
from lp.app.widgets.date import DateWidget
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.breadcrumb import Breadcrumb


class TeamMembershipBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `ITeamMembership`."""

    @property
    def text(self):
        return "%s's membership" % self.context.person.displayname


class TeamMembershipEditView(LaunchpadView):

    def __init__(self, context, request):
        super(TeamMembershipEditView, self).__init__(context, request)
        self.errormessage = ""
        self.prefix = 'membership'
        self.max_year = 2050
        fields = form.Fields(Date(
            __name__='expirationdate', title=_('Expiration date')))
        expiration_field = fields['expirationdate']
        expiration_field.custom_widget = CustomWidgetFactory(DateWidget)
        expires = self.context.dateexpires
        UTC = pytz.timezone('UTC')
        if self.isExpired():
            # For expired members, we will present the team's default
            # renewal date.
            expires = self.context.team.defaultrenewedexpirationdate
        if self.isDeactivated():
            # For members who were deactivated, we present by default
            # their original expiration date, or, if that has passed, or
            # never set, the team's default renewal date.
            if expires is None or expires < datetime.now(UTC):
                expires = self.context.team.defaultrenewedexpirationdate
        if expires is not None:
            # We get a datetime from the database, but we want to use a
            # datepicker so we must feed it a plain date without time.
            expires = expires.date()
        data = {'expirationdate': expires}
        self.widgets = form.setUpWidgets(
            fields, self.prefix, context, request, ignore_request=False,
            data=data)
        self.expiration_widget = self.widgets['expirationdate']
        # Set the acceptable date range for expiration.
        self.expiration_widget.from_date = datetime.now(UTC).date()
        # Disable the date widget if there is no current or required
        # expiration
        if not expires:
            self.expiration_widget.disabled = True

    @property
    def label(self):
        # This reproduces the logic of the old H1's in the pre-3.0 UI view.
        if self.isActive():
            prefix = 'Active'
        elif self.isInactive():
            prefix = 'Inactive'
        elif self.isProposed():
            prefix = 'Proposed'
        elif self.isDeclined():
            prefix = 'Declined'
        elif self.isInvited() or self.isInvitationDeclined():
            prefix = 'Invited'
        else:
            raise AssertionError('status unknown')
        return '%s member %s' % (prefix, self.context.person.displayname)

    # Boolean helpers
    def isActive(self):
        return self.context.status in [TeamMembershipStatus.APPROVED,
                                       TeamMembershipStatus.ADMIN]

    def isInactive(self):
        return self.context.status in [TeamMembershipStatus.EXPIRED,
                                       TeamMembershipStatus.DEACTIVATED]

    def isAdmin(self):
        return self.context.status == TeamMembershipStatus.ADMIN

    def isProposed(self):
        return self.context.status == TeamMembershipStatus.PROPOSED

    def isDeclined(self):
        return self.context.status == TeamMembershipStatus.DECLINED

    def isExpired(self):
        return self.context.status == TeamMembershipStatus.EXPIRED

    def isDeactivated(self):
        return self.context.status == TeamMembershipStatus.DEACTIVATED

    def isInvited(self):
        return self.context.status == TeamMembershipStatus.INVITED

    def isInvitationDeclined(self):
        return self.context.status == TeamMembershipStatus.INVITATION_DECLINED

    def adminIsSelected(self):
        """Whether the admin radiobutton should be selected."""
        request_admin = self.request.get('admin')
        if request_admin == 'yes':
            return 'checked'
        if self.isAdmin():
            return 'checked'
        return None

    def adminIsNotSelected(self):
        """Whether the not-admin radiobutton should be selected."""
        if self.adminIsSelected() != 'checked':
            return 'checked'
        return None

    def expiresIsSelected(self):
        """Whether the expiration date radiobutton should be selected."""
        request_expires = self.request.get('expires')
        if request_expires == 'date':
            return 'checked'
        if self.isExpired():
            # Never checked when expired, because there's another
            # radiobutton in that situation.
            return None
        if self.membershipExpires():
            return 'checked'
        return None

    def neverExpiresIsSelected(self):
        """Whether the never-expires radiobutton should be selected."""
        request_expires = self.request.get('expires')
        if request_expires == 'never':
            return 'checked'
        if self.isExpired():
            # Never checked when expired, because there's another
            # radiobutton in that situation.
            return None
        if not self.membershipExpires():
            return 'checked'
        return None

    def canChangeExpirationDate(self):
        """Return True if the logged in user can change the expiration date of
        this membership.

        Team administrators can't change the expiration date of their own
        membership.
        """
        return self.context.canChangeExpirationDate(self.user)

    def membershipExpires(self):
        """Return True if this membership is scheduled to expire one day."""
        if self.context.dateexpires is None:
            return False
        else:
            return True

    #
    # Form post handlers and helpers
    #

    def processForm(self):
        if self.request.method != 'POST':
            return

        if self.request.form.get('editactive'):
            self.processActiveMember()
        elif self.request.form.get('editproposed'):
            self.processProposedMember()
        elif self.request.form.get('editinactive'):
            self.processInactiveMember()

    def processActiveMember(self):
        # This method checks the current status to ensure that we don't
        # crash because of users reposting a form.
        form = self.request.form
        context = self.context
        if form.get('deactivate'):
            if self.context.status == TeamMembershipStatus.DEACTIVATED:
                # This branch and redirect is necessary because
                # TeamMembership.setStatus() does not allow us to set an
                # already-deactivated account to deactivated, causing
                # double form posts to crash there. We instead manually
                # ensure that the double-post is harmless.
                self.request.response.redirect(
                    '%s/+members' % canonical_url(context.team))
                return
            new_status = TeamMembershipStatus.DEACTIVATED
        elif form.get('change'):
            if (form.get('admin') == "no" and
                context.status == TeamMembershipStatus.ADMIN):
                new_status = TeamMembershipStatus.APPROVED
            elif (form.get('admin') == "yes" and
                  context.status == TeamMembershipStatus.APPROVED):
                new_status = TeamMembershipStatus.ADMIN
            else:
                # No status change will happen
                new_status = self.context.status
        else:
            raise UnexpectedFormData(
                "None of the expected actions were found.")

        if self._setMembershipData(new_status):
            self.request.response.redirect(
                '%s/+members' % canonical_url(context.team))

    def processProposedMember(self):
        if self.context.status != TeamMembershipStatus.PROPOSED:
            # Catch a double-form-post.
            self.errormessage = _(
                'The membership request for %s has already been processed.' %
                    self.context.person.displayname)
            return

        assert self.context.status == TeamMembershipStatus.PROPOSED

        if self.request.form.get('decline'):
            status = TeamMembershipStatus.DECLINED
        elif self.request.form.get('approve'):
            status = TeamMembershipStatus.APPROVED
        else:
            raise UnexpectedFormData(
                "None of the expected actions were found.")
        if self._setMembershipData(status):
            self.request.response.redirect(
                '%s/+members' % canonical_url(self.context.team))

    def processInactiveMember(self):
        if self.context.status not in (TeamMembershipStatus.EXPIRED,
                                       TeamMembershipStatus.DEACTIVATED):
            # Catch a double-form-post.
            self.errormessage = _(
                'The membership request for %s has already been processed.' %
                    self.context.person.displayname)
            return

        if self._setMembershipData(TeamMembershipStatus.APPROVED):
            self.request.response.redirect(
                '%s/+members' % canonical_url(self.context.team))

    def _setMembershipData(self, status):
        """Set all data specified on the form, for this TeamMembership.

        Get all data from the form, together with the given status and set
        them for this TeamMembership object.

        Returns True if we successfully set the data, False otherwise.
        Callsites should not commit the transaction if we return False.
        """
        if self.canChangeExpirationDate():
            if self.request.form.get('expires') == 'never':
                expires = None
            else:
                try:
                    expires = self._getExpirationDate()
                except ValueError as err:
                    self.errormessage = (
                        'Invalid expiration: %s' % err)
                    return False
        else:
            expires = self.context.dateexpires

        silent = self.request.form.get('silent', False)

        self.context.setExpirationDate(expires, self.user)
        self.context.setStatus(
            status, self.user, self.request.form_ng.getOne('comment'),
            silent)
        return True

    def _getExpirationDate(self):
        """Return a datetime with the expiration date selected on the form.

        Raises ValueError if the date selected is invalid. The use of
        that exception is unusual but allows us to present a consistent
        API to the caller, who needs to check only for that specific
        exception.
        """
        expires = None
        try:
            expires = self.expiration_widget.getInputValue()
        except InputErrors as value:
            # Handle conversion errors. We have to do this explicitly here
            # because we are not using the full form machinery which would
            # put the relevant error message into the field error. We are
            # mixing the zope3 widget stuff with a hand-crafted form
            # processor, so we need to trap this manually.
            raise ValueError(value.doc())
        if expires is None:
            return None

        # We used a date picker, so we have a date. What we want is a
        # datetime in UTC
        UTC = pytz.timezone('UTC')
        expires = datetime(expires.year, expires.month, expires.day,
                           tzinfo=UTC)
        return expires


class TeamInvitationsView(LaunchpadView):
    """View for ~team/+invitations."""

    @property
    def label(self):
        return 'Invitations for ' + self.context.displayname
