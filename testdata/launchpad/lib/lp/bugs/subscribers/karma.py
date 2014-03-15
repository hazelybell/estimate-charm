# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Assign karma for bugs domain activity."""

from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.subscribers.bug import get_bug_delta
from lp.registry.interfaces.person import IPerson
from lp.services.database.sqlbase import block_implicit_flushes


@block_implicit_flushes
def bug_created(bug, event):
    """Assign karma to the user which created <bug>."""
    # All newly created bugs get at least one bugtask associated with
    assert len(bug.bugtasks) >= 1
    _assignKarmaUsingBugContext(IPerson(event.user), bug, 'bugcreated')


def _assign_karma_using_bugtask_context(person, bugtask, actionname):
    """Extract the right context from the bugtask and assign karma."""
    distribution = bugtask.distribution
    if bugtask.distroseries is not None:
        # This is a DistroSeries Task, so distribution is None and we
        # have to get it from the distroseries.
        distribution = bugtask.distroseries.distribution
    product = bugtask.product
    if bugtask.productseries is not None:
        product = bugtask.productseries.product
    person.assignKarma(
        actionname, product=product, distribution=distribution,
        sourcepackagename=bugtask.sourcepackagename)


@block_implicit_flushes
def bugtask_created(bugtask, event):
    """Assign karma to the user which created <bugtask>."""
    _assign_karma_using_bugtask_context(
        IPerson(event.user), bugtask, 'bugtaskcreated')


def _assignKarmaUsingBugContext(person, bug, actionname):
    """For each of the given bug's bugtasks, assign Karma with the given
    actionname to the given person.
    """
    for task in bug.bugtasks:
        if task.status == BugTaskStatus.INVALID:
            continue
        _assign_karma_using_bugtask_context(person, task, actionname)


@block_implicit_flushes
def bug_comment_added(bugmessage, event):
    """Assign karma to the user which added <bugmessage>."""
    _assignKarmaUsingBugContext(
        IPerson(event.user), bugmessage.bug, 'bugcommentadded')


@block_implicit_flushes
def bug_modified(bug, event):
    """Check changes made to <bug> and assign karma to user if needed."""
    user = IPerson(event.user)
    bug_delta = get_bug_delta(
        event.object_before_modification, event.object, user)

    if bug_delta is not None:
        attrs_actionnames = {'title': 'bugtitlechanged',
                             'description': 'bugdescriptionchanged',
                             'duplicateof': 'bugmarkedasduplicate'}

        for attr, actionname in attrs_actionnames.items():
            if getattr(bug_delta, attr) is not None:
                _assignKarmaUsingBugContext(user, bug, actionname)


@block_implicit_flushes
def bugwatch_added(bugwatch, event):
    """Assign karma to the user which added :bugwatch:."""
    _assignKarmaUsingBugContext(
        IPerson(event.user), bugwatch.bug, 'bugwatchadded')


@block_implicit_flushes
def cve_added(cve, event):
    """Assign karma to the user which added :cve:."""
    _assignKarmaUsingBugContext(
        IPerson(event.user), cve.bug, 'bugcverefadded')


@block_implicit_flushes
def bugtask_modified(bugtask, event):
    """Check changes made to <bugtask> and assign karma to user if needed."""
    user = IPerson(event.user)
    task_delta = event.object.getDelta(event.object_before_modification)

    if task_delta is None:
        return

    actionname_status_mapping = {
        BugTaskStatus.FIXRELEASED: 'bugfixed',
        BugTaskStatus.INVALID: 'bugrejected',
        BugTaskStatus.CONFIRMED: 'bugaccepted',
        BugTaskStatus.TRIAGED: 'bugaccepted',
        }

    if task_delta.status:
        new_status = task_delta.status['new']
        actionname = actionname_status_mapping.get(new_status)
        if actionname is not None:
            if actionname == 'bugfixed' and bugtask.assignee is not None:
                _assign_karma_using_bugtask_context(
                    bugtask.assignee, bugtask, actionname)
            else:
                _assign_karma_using_bugtask_context(user, bugtask, actionname)

    if task_delta.importance is not None:
        _assign_karma_using_bugtask_context(
            user, bugtask, 'bugtaskimportancechanged')


@block_implicit_flushes
def bug_branch_created(bug_branch, event):
    """Assign karma to the user who linked the bug to the branch."""
    bug_branch.branch.target.assignKarma(
        bug_branch.registrant, 'bugbranchcreated')
