# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation classes for IBranchMergeQueue, etc."""

__metaclass__ = type
__all__ = ['BranchMergeQueue']

import simplejson
from storm.locals import (
    Int,
    Reference,
    Store,
    Storm,
    Unicode,
    )
from zope.interface import (
    classProvides,
    implements,
    )

from lp.code.errors import InvalidMergeQueueConfig
from lp.code.interfaces.branchmergequeue import (
    IBranchMergeQueue,
    IBranchMergeQueueSource,
    )
from lp.code.model.branch import Branch
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.interfaces import IMasterStore


class BranchMergeQueue(Storm):
    """See `IBranchMergeQueue`."""

    __storm_table__ = 'BranchMergeQueue'
    implements(IBranchMergeQueue)
    classProvides(IBranchMergeQueueSource)

    id = Int(primary=True)

    registrant_id = Int(name='registrant', allow_none=True)
    registrant = Reference(registrant_id, 'Person.id')

    owner_id = Int(name='owner', allow_none=True)
    owner = Reference(owner_id, 'Person.id')

    name = Unicode(allow_none=False)
    description = Unicode(allow_none=False)
    configuration = Unicode(allow_none=False)

    date_created = UtcDateTimeCol(notNull=True)

    @property
    def branches(self):
        """See `IBranchMergeQueue`."""
        return Store.of(self).find(
            Branch,
            Branch.merge_queue_id == self.id)

    def setMergeQueueConfig(self, config):
        """See `IBranchMergeQueue`."""
        try:
            simplejson.loads(config)
            self.configuration = config
        except ValueError: # The config string is not valid JSON
            raise InvalidMergeQueueConfig

    @classmethod
    def new(cls, name, owner, registrant, description=None,
            configuration=None, branches=None):
        """See `IBranchMergeQueueSource`."""
        store = IMasterStore(BranchMergeQueue)

        if configuration is None:
            configuration = unicode(simplejson.dumps({}))

        queue = cls()
        queue.name = name
        queue.owner = owner
        queue.registrant = registrant
        queue.description = description
        queue.configuration = configuration
        if branches is not None:
            for branch in branches:
                branch.addToQueue(queue)

        store.add(queue)
        return queue
