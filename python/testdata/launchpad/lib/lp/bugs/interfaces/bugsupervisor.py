# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for objects which have a bug Supervisor."""

__metaclass__ = type

__all__ = [
    'IHasBugSupervisor',
    ]

from lazr.restful.declarations import exported
from zope.interface import Interface

from lp import _
from lp.services.fields import PersonChoice


class IHasBugSupervisor(Interface):

    bug_supervisor = exported(PersonChoice(
        title=_("Bug Supervisor"),
        description=_(
            "The Launchpad id of the person or team (preferred) responsible "
            "for bug management."),
        required=False, vocabulary='ValidPersonOrTeam', readonly=False))
