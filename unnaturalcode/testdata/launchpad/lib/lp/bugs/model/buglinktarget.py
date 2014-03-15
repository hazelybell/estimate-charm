# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [ 'BugLinkTargetMixin' ]

from lazr.lifecycle.event import (
    ObjectCreatedEvent,
    ObjectDeletedEvent,
    )
from zope.event import notify
from zope.security.interfaces import Unauthorized

from lp.services.webapp.authorization import check_permission


class BugLinkTargetMixin:
    """Mixin class for IBugLinkTarget implementation."""

    @property
    def buglinkClass(self):
        """Subclass should override this property to return the database
        class used for IBugLink."""
        raise NotImplementedError("missing buglinkClass() implementation")

    def createBugLink(self, bug):
        """Subclass should override that method to create a BugLink instance.
        """
        raise NotImplementedError("missing createBugLink() implementation")

    # IBugLinkTarget implementation
    def linkBug(self, bug):
        """See IBugLinkTarget."""
        # XXX gmb 2007-12-11 bug=175545:
        #     We shouldn't be calling check_permission here. The user's
        #     permissions should have been checked before this method
        #     was called. Also, we shouldn't be relying on the logged-in
        #     user in this method; the method should accept a user
        #     parameter.
        if not check_permission('launchpad.View', bug):
            raise Unauthorized(
                "cannot link to a private bug you don't have access to")
        for buglink in self.bug_links:
            if buglink.bug.id == bug.id:
                return buglink
        buglink = self.createBugLink(bug)
        notify(ObjectCreatedEvent(buglink))
        return buglink

    def unlinkBug(self, bug):
        """See IBugLinkTarget."""
        # XXX gmb 2007-12-11 bug=175545:
        #     We shouldn't be calling check_permission here. The user's
        #     permissions should have been checked before this method
        #     was called. Also, we shouldn't be relying on the logged-in
        #     user in this method; the method should accept a user
        #     parameter.
        if not check_permission('launchpad.View', bug):
            raise Unauthorized(
                "cannot unlink a private bug you don't have access to")

        # see if a relevant bug link exists, and if so, delete it
        for buglink in self.bug_links:
            if buglink.bug.id == bug.id:
                notify(ObjectDeletedEvent(buglink))
                self.buglinkClass.delete(buglink.id)
                # XXX: Bjorn Tillenius 2005-11-21: We shouldn't return the
                #      object that we just deleted from the db.
                return buglink
