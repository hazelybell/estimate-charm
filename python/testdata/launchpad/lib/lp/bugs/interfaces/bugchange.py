# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for bug changes."""

__metaclass__ = type
__all__ = [
    'IBugChange',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class IBugChange(Interface):
    """Represents a change to an `IBug`."""

    when = Attribute("The timestamp for the BugChange.")
    person = Attribute("The Person who made the change.")
    change_level = Attribute(
        "Type of the change to a bug expressed as `BugNotificationLevel`.")

    def getBugActivity():
        """Return the `BugActivity` data for this change as a dict."""

    def getBugNotification():
        """Return any `BugNotification`s for this event."""
