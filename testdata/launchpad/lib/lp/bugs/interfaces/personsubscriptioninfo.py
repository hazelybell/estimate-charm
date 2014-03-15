# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person's bug subscription information interfaces."""

__all__ = [
    'IAbstractSubscriptionInfoCollection',
    'IPersonSubscriptions',
    'IRealSubscriptionInfo',
    'IRealSubscriptionInfoCollection',
    'IVirtualSubscriptionInfo',
    'IVirtualSubscriptionInfoCollection'
    ]


from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import Bool

from lp import _
from lp.services.fields import (
    BugField,
    PersonChoice,
    )


class IAbstractSubscriptionInfo(Interface):

    bug = BugField(
        title=_("Bug"), readonly=True, required=True,
        description=_("A bug that this subscription is on. "
                      "If subscription is on a duplicate "
                      "bug, references that bug."))

    principal = PersonChoice(
        title=_("Subscriber"), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam',
        description=_(
            "The person or team for which this information is gathered."))


class IRealSubscriptionInfo(IAbstractSubscriptionInfo):

    subscription = Attribute(
        "The bug subscription.  Important attributes for our uses are the "
        "target and the bug_notification_level.")

    principal_is_reporter = Bool(
       title=_("Principal is Reporter?"),
       description=_("Is the principal the bug reporter."),
       default=False, readonly=True)

    bug_supervisor_tasks = Attribute(
        """A collection of targets of the info's bug for which the
        principal is a bug supervisor (which causes direct subscriptions for
        private bugs at this time).""")


class IVirtualSubscriptionInfo(IAbstractSubscriptionInfo):

    pillar = Attribute(
        """The pillar for the bugtask.  Useful for owner and
        bug_supervisor""")

    tasks = Attribute("""The bugtasks pertinent to this subscription.""")


class IAbstractSubscriptionInfoCollection(Interface):

    count = Attribute(
        'The total number of contained subscriptions.')

    personal = Attribute(
        "List of information objects about the personal duplicate "
        "subscriptions.")

    as_team_member = Attribute(
        "List of information objects about the subscriptions "
        "through a team, exluding teams of which the person is an admin")

    as_team_admin = Attribute(
        "List of information objects about the subscriptions "
        "through teams of which the person is an admin.")


class IRealSubscriptionInfoCollection(IAbstractSubscriptionInfoCollection):
    """Contains information about real subscriptions.

    All objects in collections provide IRealSubscriptionInfo."""


class IVirtualSubscriptionInfoCollection(IAbstractSubscriptionInfoCollection):
    """Contains information about virtual subscriptions.

    Includes those through team membership.

    All objects in collections provide IVirtualSubscriptionInfo."""


class IPersonSubscriptions(Interface):
    """Subscription information for a given person and bug."""

    count = Attribute(
        'The total number of subscriptions, real and virtual')

    muted = Bool(
       title=_("Bug is muted?"),
       description=_("Is the bug muted?"),
       default=False, readonly=True)

    bug = BugField(
        title=_("Bug"), readonly=True, required=True,
        description=_("A bug that this subscription is on. "
                      "If subscription is on a duplicate "
                      "bug, references that bug."))

    person = PersonChoice(
        title=_("Subscriber"), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam',
        description=_("The person for which this information is gathered."))

    direct = Attribute(
        "An IRealSubscriptionInfoCollection.  Contains information about all "
        "direct subscriptions. Includes those through membership in teams "
        "directly subscribed to a bug.")

    from_duplicate = Attribute(
        "An IRealSubscriptionInfoCollection.  Contains information about all "
        "subscriptions through duplicate bugs. Includes those through team "
        "membership.")

    as_owner = Attribute(
        "An IVirtualSubscriptionInfoCollection containing information about "
        "all virtual subscriptions as target owner when no bug supervisor "
        "is defined for the target, including those through team "
        "memberships.")

    as_assignee = Attribute(
        "An IVirtualSubscriptionInfoCollection containing information about "
        "all virtual subscriptions as an assignee, including those through "
        "team memberships.")

    def reload():
        """Reload subscriptions for a person/bug."""

    def getDataForClient():
        """Get data for use in client-side code.

        Returns two dicts, subscription info and references.  references is
        expected to be used as
        IJSONRequestCache(request).objects.extend(references).
        subscription info also is expected to be placed in .objects for
        lazr.restful to marshall for the client.  For objects in the data
        structure, values are strings that are keys into the "references"
        map.  With expected usage, then, on the client side LP.cache[name]
        would return the desired value.

        subscription info roughly mirrors the structure of the
        IPersonSubscriptions that sends it.
        """
