# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions/classes to be used when testing the karma framework."""

__metaclass__ = type
__all__ = [
    'KarmaAssignedEventListener',
    'KarmaRecorder',
    ]

from lp.registry.interfaces.karma import IKarmaAssignedEvent
from lp.registry.interfaces.person import IPerson
from lp.testing.event import TestEventListener


class KarmaRecorder:
    """Helper that records selected karma events.

    Install with `register` (and don't forget to uninstall later with
    `unregister`).

    A list of karma events is accumulated in the `karma_events`
    property.
    """

    def __init__(self, person=None, action_name=None, product=None,
                 distribution=None, sourcepackagename=None):
        """Create a `KarmaRecorder`, but do not activate it yet.

        :param person: If given, record only karma for this `Person`.
        :param action_name: If given, record only karma with this action
            name (e.g. questionasked, sponsoruploadaccepted, bugfixed).
        :param product: If given, record only karma related to this
            `Product`.
        :param distribution: If given, record only karma related to this
            `Distribution`.
        :param sourcepackagename: If given, record only karma related to
            this `SourcePackageName`.
        """
        self.person = person
        self.action_name = action_name
        self.product = product
        self.distribution = distribution
        self.sourcepackagename = sourcepackagename

        self.karma_events = []

    def _filterFor(self, filter_value, event_value):
        """Does an event property value pass our filter for that property?"""
        return filter_value is None or event_value == filter_value

    def filter(self, karma):
        """Does `karma` match our filters?"""
        return (
            self._filterFor(self.person, karma.person) and
            self._filterFor(self.action_name, karma.action.name) and
            self._filterFor(self.product, karma.product) and
            self._filterFor(self.distribution, karma.distribution) and
            self._filterFor(self.sourcepackagename, karma.sourcepackagename))

    def record(self, karma):
        """Overridable: record the assignment of karma.

        The default action to record the karma object in
        `self.karma_events`, but feel free to override this with your
        own handler.
        """
        self.karma_events.append(karma)

    def receive(self, obj, event):
        """Process a karma event.

        Runs `filter` on the event and if it passes, `record`s it.
        """
        if self.filter(event.karma):
            self.record(event.karma)

    def register_listener(self):
        """Register listener.  Must be `unregister`ed later."""
        self.listener = TestEventListener(
            IPerson, IKarmaAssignedEvent, self.receive)

    def unregister_listener(self):
        """Unregister listener after `register`."""
        self.listener.unregister()


class KarmaAssignedEventListener(KarmaRecorder):
    """Test helper class that registers a listener printing information
    whenever Karma is assigned.

    No karma assignments will be printed until the register_listener()
    method is called.

    Each time Karma is assigned to a Person, a line in the following format
    will be printed:

        Karma added: action=<action>, [product|distribution]=<contextname>

    If show_person is set to True, the name of the person to whom karma is
    granted will also be shown like this (on one line):

        Karma added: action=<action>, [product|distribution]=<contextname>,
        person=<name>

    A set of KarmaAction objects assigned since the register_listener()
    method was called is available in the added_listener_actions property.
    """

    def __init__(self, show_person=False):
        super(KarmaAssignedEventListener, self).__init__()
        self.added_karma_actions = set()
        self.show_person = show_person

    def record(self, karma):
        action = karma.action
        self.added_karma_actions.add(action)
        text = "Karma added: action=%s," % action.name
        if karma.product is not None:
            text += " product=%s" % karma.product.name
        elif karma.distribution is not None:
            text += " distribution=%s" % karma.distribution.name
        if self.show_person:
            text += ", person=%s" % karma.person.name
        print text
