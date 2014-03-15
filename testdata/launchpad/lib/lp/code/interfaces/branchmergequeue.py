# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Branch merge queue interfaces."""

__metaclass__ = type

__all__ = [
    'IBranchMergeQueue',
    'IBranchMergeQueueSource',
    'user_has_special_merge_queue_access',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    export_write_operation,
    exported,
    mutator_for,
    operation_parameters,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.component import getUtility
from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.fields import (
    PersonChoice,
    PublicPersonChoice,
    )


class IBranchMergeQueue(Interface):
    """An interface for managing branch merges."""

    export_as_webservice_entry()

    id = Int(title=_('ID'), readonly=True, required=True)

    registrant = exported(
        PublicPersonChoice(
            title=_("The user that registered the branch."),
            required=True, readonly=True,
            vocabulary='ValidPersonOrTeam'))

    owner = exported(
        PersonChoice(
            title=_('Owner'),
            required=True, readonly=True,
            vocabulary='UserTeamsParticipationPlusSelf',
            description=_("The owner of the merge queue.")))

    name = exported(
        TextLine(
            title=_('Name'), required=True,
            description=_(
                "Keep very short, unique, and descriptive, because it will "
                "be used in URLs.  "
                "Examples: main, devel, release-1.0, gnome-vfs.")))

    description = exported(
        Text(
            title=_('Description'), required=False,
            description=_(
                'A short description of the purpose of this merge queue.')))

    configuration = exported(
        TextLine(
            title=_('Configuration'), required=False, readonly=True,
            description=_(
                "A JSON string of configuration values.")))

    date_created = exported(
        Datetime(
            title=_('Date Created'),
            required=True,
            readonly=True))

    branches = exported(
        CollectionField(
            title=_('Dependent Branches'),
            description=_(
                'A collection of branches that this queue manages.'),
            readonly=True,
            value_type=Reference(Interface)))

    @mutator_for(configuration)
    @operation_parameters(
        config=TextLine(title=_("A JSON string of configuration values.")))
    @export_write_operation()
    def setMergeQueueConfig(config):
        """Set the JSON string configuration of the merge queue.

        :param config: A JSON string of configuration values.
        """


class IBranchMergeQueueSource(Interface):

    def new(name, owner, registrant, description, configuration, branches):
        """Create a new IBranchMergeQueue object.

        :param name: The name of the branch merge queue.
        :param description: A description of queue.
        :param configuration: A JSON string of configuration values.
        :param owner: The owner of the queue.
        :param registrant: The registrant of the queue.
        :param branches: A list of branches to add to the queue.
        """


def user_has_special_merge_queue_access(user):
    """Admins and bazaar experts have special access.

    :param user: A 'Person' or None.
    """
    if user is None:
        return False
    celebs = getUtility(ILaunchpadCelebrities)
    return user.inTeam(celebs.admin)
