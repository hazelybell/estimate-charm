# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Question subscription interface."""

__metaclass__ = type

__all__ = [
    'IQuestionSubscription',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    )

from lp import _
from lp.services.fields import PersonChoice


class IQuestionSubscription(Interface):
    """A subscription for a person to a question."""

    export_as_webservice_entry(publish_web_link=False, as_of='devel')

    id = Int(title=_('ID'), readonly=True, required=True)
    person = exported(PersonChoice(
        title=_('Person'), required=True, vocabulary='ValidPersonOrTeam',
        readonly=True, description=_("The person's Launchpad ID or "
        "e-mail address.")), as_of="devel")
    question = exported(Reference(
        Interface, title=_("Question"), required=True, readonly=True),
        as_of="devel")
    date_created = exported(
        Datetime(title=_('Date subscribed'), required=True, readonly=True),
        as_of="devel")

    def canBeUnsubscribedByUser(user):
        """Can the user unsubscribe the subscriber from the question?"""
