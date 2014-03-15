# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper class and functions for the import-debian-bugs.py script."""

__metaclass__ = type

import transaction
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.externalbugtracker import get_external_bugtracker
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.scripts.checkwatches import CheckwatchesMaster
from lp.services.scripts.logger import log


def import_debian_bugs(bugs_to_import, logger=None):
    """Import the specified Debian bugs into Launchpad."""
    if logger is None:
        logger = log
    debbugs = getUtility(ILaunchpadCelebrities).debbugs
    external_debbugs = get_external_bugtracker(debbugs)
    bug_watch_updater = CheckwatchesMaster(transaction, logger)
    debian = getUtility(ILaunchpadCelebrities).debian
    for debian_bug in bugs_to_import:
        existing_bug_ids = [
            str(bug.id) for bug in debbugs.getBugsWatching(debian_bug)]
        if len(existing_bug_ids) > 0:
            logger.warning(
                "Not importing debbugs #%s, since it's already linked"
                " from LP bug(s) #%s." % (
                    debian_bug, ', '.join(existing_bug_ids)))
            continue
        bug = bug_watch_updater.importBug(
            external_debbugs, debbugs, debian, debian_bug)

        [debian_task] = bug.bugtasks
        bug_watch_updater.updateBugWatches(
            external_debbugs, [debian_task.bugwatch])
        target = getUtility(ILaunchpadCelebrities).ubuntu
        if debian_task.sourcepackagename:
            target = target.getSourcePackage(debian_task.sourcepackagename)
        getUtility(IBugTaskSet).createTask(
            bug, getUtility(ILaunchpadCelebrities).bug_watch_updater, target)
        logger.info(
            "Imported debbugs #%s as Launchpad bug #%s." % (
                debian_bug, bug.id))
