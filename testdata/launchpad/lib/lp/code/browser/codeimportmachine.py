# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for CodeImportMachines."""

__metaclass__ = type

__all__ = [
    'CodeImportMachineBreadcrumb',
    'CodeImportMachineSetBreadcrumb',
    'CodeImportMachineSetNavigation',
    'CodeImportMachineSetView',
    'CodeImportMachineView',
    ]


from lazr.delegates import delegates
from zope.component import getUtility
from zope.interface import Interface
from zope.schema import TextLine

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.code.enums import (
    CodeImportMachineOfflineReason,
    CodeImportMachineState,
    )
from lp.code.interfaces.codeimportevent import ICodeImportEvent
from lp.code.interfaces.codeimportmachine import ICodeImportMachineSet
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    Navigation,
    )
from lp.services.webapp.breadcrumb import Breadcrumb


class CodeImportMachineBreadcrumb(Breadcrumb):
    """An `IBreadcrumb` that uses the machines hostname."""

    @property
    def text(self):
        return self.context.hostname


class CodeImportMachineSetNavigation(Navigation):
    """Navigation methods for ICodeImportMachineSet."""
    usedfor = ICodeImportMachineSet

    def traverse(self, hostname):
        """See `Navigation`."""
        return self.context.getByHostname(hostname)


class CodeImportMachineSetBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `ICodeImportMachineSet`."""
    text = u'Machines'


class CodeImportMachineSetView(LaunchpadView):
    """The view for the page that shows all the import machines."""

    label = "Import machines for Launchpad"
    page_title = label

    @property
    def machines(self):
        """Get the machines, sorted alphabetically by hostname."""
        return getUtility(ICodeImportMachineSet).getAll()


class UpdateMachineStateForm(Interface):
    """An interface to allow the user to enter a reason for quiescing."""

    reason = TextLine(
        title=_('Reason'), required=False, description=_(
            "Why the machine state is changing."))


class DecoratedEvent:
    """A CodeImportEvent with cached items."""

    delegates(ICodeImportEvent, 'event')

    def __init__(self, event):
        self.event = event

    @cachedproperty
    def items(self):
        """Avoid hitting the database multiple times by caching the result."""
        return self.event.items()


class CodeImportMachineView(LaunchpadFormView):
    """The view for looking at an individual code import machine."""

    schema = UpdateMachineStateForm

    # The default reason is always the empty string.
    initial_values = {'reason': ''}

    @property
    def page_title(self):
        return 'Code Import machine "%s"' % self.context.hostname

    @property
    def latest_events(self):
        """The ten most recent events for the machine."""
        return [DecoratedEvent(event) for event in self.context.events[:10]]

    @property
    def adapters(self):
        """See `LaunchpadFormView`"""
        return {UpdateMachineStateForm: self.context}

    @property
    def next_url(self):
        """See `LaunchpadFormView`"""
        return canonical_url(self.context)

    def _canChangeToState(self, action):
        """Is it valid for the machine to move to the next_state.

        The next_state is stored in the data dict of the action.
        """
        next_state = action.data['next_state']
        if next_state == CodeImportMachineState.QUIESCING:
            return self.context.state == CodeImportMachineState.ONLINE
        else:
            return self.context.state != next_state

    @action('Set Online', name='set_online',
            data={'next_state': CodeImportMachineState.ONLINE},
            condition=_canChangeToState)
    def set_online_action(self, action, data):
        self.context.setOnline(self.user, data['reason'])

    @action('Set Offline', name='set_offline',
            data={'next_state': CodeImportMachineState.OFFLINE},
            condition=_canChangeToState)
    def set_offline_action(self, action, data):
        self.context.setOffline(
            CodeImportMachineOfflineReason.STOPPED, self.user, data['reason'])

    @action('Set Quiescing', name='set_quiescing',
            data={'next_state': CodeImportMachineState.QUIESCING},
            condition=_canChangeToState)
    def set_quiescing_action(self, action, data):
        self.context.setQuiescing(self.user, data['reason'])
