# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper class for checking the event notifications."""

__metaclass__ = type

from zope.app.testing import ztapi


class TestEventListener:
    """Listen for a specific object event in tests.

    When an event of the specified type is fired off for an object with
    the specifed type, the given callback is called.

    The callback function should take an object and an event.

    At the end of the test you have to unregister the event listener
    using event_listener.unregister().
    """

    def __init__(self, object_type, event_type, callback):
        self.object_type = object_type
        self.event_type = event_type
        self.callback = callback
        self._active = True
        ztapi.subscribe((object_type, event_type), None, self)

    def __call__(self, object, event):
        if not self._active:
            return
        self.callback(object, event)

    def unregister(self):
        """Stop the event listener from listening to events."""
        # XXX: Bjorn Tillenius 2006-02-14 bug=2338: There is currently no way
        #      of unsubscribing an event handler, so we simply set
        #      self._active to False in order to make the handler return
        #      without doing anything.
        self._active = False

