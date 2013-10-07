# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    "mail_handlers",
    ]

from lp.answers.mail.handler import AnswerTrackerHandler
from lp.bugs.mail.handler import MaloneHandler
from lp.code.mail.codehandler import CodeHandler
from lp.services.config import config


class MailHandlers:
    """All the registered mail handlers."""

    DEFAULT = (
        (config.launchpad.bugs_domain, MaloneHandler),
        (config.answertracker.email_domain, AnswerTrackerHandler),
        # XXX flacoste 2007-04-23 Backward compatibility for old domain.
        # We probably want to remove it in the future.
        ('support.launchpad.net', AnswerTrackerHandler),
        (config.launchpad.code_domain, CodeHandler),
        )

    def __init__(self):
        self._handlers = {}
        for domain, handler_factory in self.DEFAULT:
            self.add(domain, handler_factory())

    def get(self, domain):
        """Return the handler for the given email domain.

        Return None if no such handler exists.
        """
        return self._handlers.get(domain.lower())

    def add(self, domain, handler):
        """Adds a handler for a domain."""
        self._handlers[domain.lower()] = handler


mail_handlers = MailHandlers()
