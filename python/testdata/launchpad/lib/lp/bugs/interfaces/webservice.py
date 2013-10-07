# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.bugs.interfaces.webservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__all__ = [
    'BugNominationStatusError',
    'IBug',
    'IBugActivity',
    'IBugAttachment',
    'IBugBranch',
    'IBugLinkTarget',
    'IBugNomination',
    'IBugSubscription',
    'IBugTarget',
    'IBugTask',
    'IBugTracker',
    'IBugTrackerComponent',
    'IBugTrackerComponentGroup',
    'IBugTrackerSet',
    'IBugWatch',
    'ICve',
    'ICveSet',
    'IHasBugs',
    'IMaloneApplication',
    'IStructuralSubscription',
    'IStructuralSubscriptionTarget',
    'IllegalRelatedBugTasksParams',
    'IllegalTarget',
    'NominationError',
    'NominationSeriesObsoleteError',
    'UserCannotEditBugTaskAssignee',
    'UserCannotEditBugTaskImportance',
    'UserCannotEditBugTaskMilestone',
    'UserCannotEditBugTaskStatus',
    ]

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
from lp.bugs.interfaces.bug import IBug
from lp.bugs.interfaces.bugactivity import IBugActivity
from lp.bugs.interfaces.bugattachment import IBugAttachment
from lp.bugs.interfaces.bugbranch import IBugBranch
from lp.bugs.interfaces.buglink import IBugLinkTarget
from lp.bugs.interfaces.bugnomination import (
    BugNominationStatusError,
    IBugNomination,
    NominationError,
    NominationSeriesObsoleteError,
    )
from lp.bugs.interfaces.bugsubscription import IBugSubscription
from lp.bugs.interfaces.bugsubscriptionfilter import IBugSubscriptionFilter
from lp.bugs.interfaces.bugtarget import (
    IBugTarget,
    IHasBugs,
    )
from lp.bugs.interfaces.bugtask import (
    IBugTask,
    IllegalTarget,
    UserCannotEditBugTaskAssignee,
    UserCannotEditBugTaskImportance,
    UserCannotEditBugTaskMilestone,
    UserCannotEditBugTaskStatus,
    )
from lp.bugs.interfaces.bugtasksearch import IllegalRelatedBugTasksParams
from lp.bugs.interfaces.bugtracker import (
    IBugTracker,
    IBugTrackerComponent,
    IBugTrackerComponentGroup,
    IBugTrackerSet,
    )
from lp.bugs.interfaces.bugwatch import IBugWatch
from lp.bugs.interfaces.cve import (
    ICve,
    ICveSet,
    )
from lp.bugs.interfaces.malone import IMaloneApplication
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscription,
    IStructuralSubscriptionTarget,
    )


_schema_circular_imports
