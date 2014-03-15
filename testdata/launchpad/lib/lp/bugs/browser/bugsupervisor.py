# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser view for bug supervisor."""

__metaclass__ = type

__all__ = [
    'BugSupervisorEditView',
    ]

from lazr.restful.interface import copy_field
from zope.interface import Interface

from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    )
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.services.webapp.escaping import structured
from lp.services.webapp.publisher import canonical_url


class BugSupervisorEditSchema(Interface):
    """Defines the fields for the edit form.

    This is necessary to make an editable field for bug supervisor as it is
    defined as read-only in the interface to prevent setting it directly.
    """
    bug_supervisor = copy_field(
        IHasBugSupervisor['bug_supervisor'], readonly=False)


class BugSupervisorEditView(LaunchpadEditFormView):
    """Browser view class for editing the bug supervisor."""

    schema = BugSupervisorEditSchema
    field_names = ['bug_supervisor']

    @property
    def label(self):
        """The form label."""
        return 'Edit bug supervisor for %s' % self.context.displayname

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @property
    def adapters(self):
        """See `LaunchpadFormView`"""
        return {BugSupervisorEditSchema: self.context}

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    cancel_url = next_url

    @action('Change', name='change')
    def change_action(self, action, data):
        """Redirect to the target page with a success message."""
        self.updateContextFromData(data)
        if self.context.bug_supervisor is None:
            message = (
                "Successfully cleared the bug supervisor. "
                "You can set the bug supervisor again at any time.")
        else:
            message = structured('Bug supervisor privilege granted.')
        self.request.response.addNotification(message)
