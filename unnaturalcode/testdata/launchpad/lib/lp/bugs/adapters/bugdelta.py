# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Components related to bugs."""

__metaclass__ = type

from zope.interface import implements

from lp.bugs.interfaces.bug import IBugDelta


class BugDelta:
    """See `IBugDelta`."""
    implements(IBugDelta)

    def __init__(self, bug, bugurl, user,
                 title=None, description=None, name=None,
                 private=None, security_related=None, information_type=None,
                 duplicateof=None, external_reference=None, bugwatch=None,
                 cve=None, attachment=None, tags=None,
                 added_bugtasks=None, bugtask_deltas=None,
                 bug_before_modification=None):
        self.bug = bug
        self.bug_before_modification = bug_before_modification
        self.bugurl = bugurl
        self.user = user
        self.title = title
        self.description = description
        self.name = name
        self.private = private
        self.security_related = security_related
        self.information_type = information_type
        self.duplicateof = duplicateof
        self.external_reference = external_reference
        self.bugwatch = bugwatch
        self.cve = cve
        self.attachment = attachment
        self.tags = tags
        self.added_bugtasks = added_bugtasks
        self.bugtask_deltas = bugtask_deltas
