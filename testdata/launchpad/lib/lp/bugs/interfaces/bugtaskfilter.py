# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Fiter bugtasks based on context."""

__metaclass__ = type
__all__ = [
    'filter_bugtasks_by_context',
    'OrderedBugTask',
    'simple_weight_calculator',
    ]


from collections import (
    defaultdict,
    namedtuple,
    )
from operator import attrgetter

from lp.bugs.interfaces.bugtarget import IHasBugs


OrderedBugTask = namedtuple('OrderedBugTask', 'rank id task')


def simple_weight_calculator(bugtask):
    """All tasks have the same weighting."""
    return OrderedBugTask(1, bugtask.id, bugtask)


def filter_bugtasks_by_context(context, bugtasks):
    """Return the bugtasks filtered so there is only one bug task per bug.

    The context is used to return the most relevent bugtask for that context.

    An initial constraint is to not require any database queries from this
    method.

    Current contexts that impact selection:
      IProduct
      IProductSeries
      IDistribution
      IDistroSeries
      ISourcePackage
    Others:
      get the first bugtask for any particular bug

    If the context is a Product, then return the product bug task if there is
    one.  If the context is a ProductSeries, then return the productseries
    task if there is one, and if there isn't, look for the product task.  A
    similar approach is taked for Distribution and distroseries.

    For source packages, we look for the source package task, followed by the
    distro source package, then the distroseries task, and lastly the distro
    task.

    If there is no specific matching task, we return the first task (the one
    with the smallest database id).
    """
    has_bugs = IHasBugs(context, None)
    if has_bugs is None:
        weight_calculator = simple_weight_calculator
    else:
        weight_calculator = has_bugs.getBugTaskWeightFunction()

    bug_mapping = defaultdict(list)
    for task in bugtasks:
        bug_mapping[task.bugID].append(weight_calculator(task))

    filtered = [sorted(tasks)[0].task for tasks in bug_mapping.itervalues()]
    return sorted(filtered, key=attrgetter('bugID'))
