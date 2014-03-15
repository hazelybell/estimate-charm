# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""__init__ module for the externalbugtracker package."""

__metaclass__ = type
__all__ = [
    'BATCH_SIZE_UNLIMITED',
    'BugNotFound',
    'BugTrackerConnectError',
    'BugWatchUpdateError',
    'BugWatchUpdateWarning',
    'Bugzilla',
    'DebBugs',
    'DebBugsDatabaseNotFound',
    'ExternalBugTracker',
    'InvalidBugId',
    'LookupTree',
    'Mantis',
    'MantisLoginHandler',
    'PrivateRemoteBug',
    'RequestTracker',
    'Roundup',
    'SourceForge',
    'Trac',
    'UnknownBugTrackerTypeError',
    'UnknownRemoteStatusError',
    'UnparsableBugData',
    'UnparsableBugTrackerVersion',
    'UnsupportedBugTrackerVersion',
    'get_external_bugtracker',
    ]

from lp.bugs.externalbugtracker.base import *
from lp.bugs.externalbugtracker.bugzilla import *
from lp.bugs.externalbugtracker.debbugs import *
from lp.bugs.externalbugtracker.mantis import *
from lp.bugs.externalbugtracker.roundup import *
from lp.bugs.externalbugtracker.rt import *
from lp.bugs.externalbugtracker.sourceforge import *
from lp.bugs.externalbugtracker.trac import *
from lp.bugs.interfaces.bugtracker import BugTrackerType


BUG_TRACKER_CLASSES = {
    BugTrackerType.BUGZILLA: Bugzilla,
    BugTrackerType.DEBBUGS: DebBugs,
    BugTrackerType.MANTIS: Mantis,
    BugTrackerType.TRAC: Trac,
    BugTrackerType.ROUNDUP: Roundup,
    BugTrackerType.RT: RequestTracker,
    BugTrackerType.SOURCEFORGE: SourceForge,
    }


def get_external_bugtracker(bugtracker):
    """Return an `ExternalBugTracker` for bugtracker."""
    bugtrackertype = bugtracker.bugtrackertype
    bugtracker_class = BUG_TRACKER_CLASSES.get(bugtracker.bugtrackertype)
    if bugtracker_class is not None:
        return bugtracker_class(bugtracker.baseurl)
    else:
        raise UnknownBugTrackerTypeError(bugtrackertype.name,
            bugtracker.name)
