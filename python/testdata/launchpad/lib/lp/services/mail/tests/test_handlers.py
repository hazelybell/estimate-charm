# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.mail.handlers import MailHandlers
from lp.testing import TestCase


class TestMailHandlers(TestCase):
    """Tests for the `MailHandlers` class."""

    def test_get(self):
        # MailHandlers.get() should return the registered handler for the
        # given domain.
        handlers = MailHandlers()
        self.assertIsNot(None, handlers.get("bugs.launchpad.net"))
        self.assertIs(None, handlers.get("no.such.domain"))

    def test_get_is_case_insensitive(self):
        # The domain passed to get() is treated case-insentitively.
        handlers = MailHandlers()
        handler = object()
        handlers.add("some.domain", handler)
        self.assertIs(handler, handlers.get("some.domain"))
        self.assertIs(handler, handlers.get("SOME.DOMAIN"))
        self.assertIs(handler, handlers.get("Some.Domain"))

    def test_add_for_new_domain(self):
        # MailHandlers.add() registers a handler for the given domain.
        handlers = MailHandlers()
        self.assertIs(None, handlers.get("some.domain"))
        handler = object()
        handlers.add("some.domain", handler)
        self.assertIs(handler, handlers.get("some.domain"))

    def test_add_for_existing_domain(self):
        # When adding a new handler for an already congfigured domain, the
        # existing handler is overwritten.
        handlers = MailHandlers()
        handler1 = object()
        handlers.add("some.domain", handler1)
        handler2 = object()
        handlers.add("some.domain", handler2)
        self.assertIs(handler2, handlers.get("some.domain"))
