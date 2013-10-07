# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mailing list interfaces related to list subscriptions."""

__metaclass__ = type

__all__ = ['MailingListAutoSubscribePolicy']


from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )


class MailingListAutoSubscribePolicy(DBEnumeratedType):
    """A person's auto-subscribe policy.

    When a person joins a team, or is joined to a team, their
    auto-subscribe policy describes how and whether they will be
    automatically subscribed to any team mailing list that the team may have.

    This does not describe what happens when a team that already has members
    gets a new team mailing list.  In that case, its members are never
    automatically subscribed to the mailing list.
    """

    NEVER = DBItem(0, """
        Never subscribe to mailing lists

        Do not subscribe to mailing lists.
        """)

    ON_REGISTRATION = DBItem(1, """
        Ask me when I join a team

        Launchpad will only ask about mailing subscriptions when you
        request to join a team.
        """)

    ALWAYS = DBItem(2, """
        Always subscribe me to mailing lists

        Launchpad will automatically subscribe you to a team's
        mailing list, even when someone else adds you to the team.
        """)
