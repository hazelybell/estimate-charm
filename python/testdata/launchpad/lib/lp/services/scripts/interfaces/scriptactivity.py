# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for Script activity records"""

__metaclass__ = type

__all__ = [
    'IScriptActivity',
    'IScriptActivitySet',
    ]

from zope.interface import Interface
from zope.schema import (
    Datetime,
    TextLine,
    )

from lp import _


class IScriptActivity(Interface):
    """A record of an invocation of a script."""

    name = TextLine(
        title=_('Script name'), required=True,
        description=_('The name of the script that was run'))
    hostname = TextLine(
        title=_('Host name'), required=True,
        description=_('The host on which the script was run'))
    date_started = Datetime(
        title=_('Date started'), required=True,
        description=_('The date at which the script started'))
    date_completed = Datetime(
        title=_('Date completed'), required=True,
        description=_('The date at which the script completed'))


class IScriptActivitySet(Interface):

    def recordSuccess(name, date_started, date_completed, hostname=None):
        """Record a successful script run.

        :param name: The name of the script that ran successfully.
        :param date_started: The `datetime` when the script started.
        :param date_completed: The `datetime` when the script finished.
        :param hostname: The name of the host the script ran on. If None, then
            use the hostname from `socket.gethostname`.
        """

    def getLastActivity(name):
        """Get the last activity record for the given script name."""
