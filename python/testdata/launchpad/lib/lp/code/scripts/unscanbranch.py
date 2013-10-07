# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'UnscanBranchScript',
    ]


import transaction
from zope.component import getUtility

from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.model.branchjob import BranchScanJob
from lp.code.model.branchrevision import BranchRevision
from lp.services.database.interfaces import IStore
from lp.services.scripts.base import LaunchpadScript


class UnscanBranchScript(LaunchpadScript):
    """Unscan branches.

    Resets the database scan data (eg. BranchRevision records and
    last_scanned_id) for a set of branches, and optionally requests a
    rescan.

    Mostly useful for working around performance bugs in the branch scanner
    that don't affect fresh branches.
    """

    description = __doc__
    usage = "%prog <branch URL>..."

    def add_my_options(self):
        self.parser.add_option(
            "--rescan", dest="rescan", action="store_true", default=False,
            help="Request a rescan of the branches after unscanning them.")

    def main(self):
        if len(self.args) == 0:
            self.parser.error("Wrong number of arguments.")

        for url in self.args:
            branch = getUtility(IBranchLookup).getByUrl(url)
            if branch is None:
                self.logger.error(
                    "Could not find branch at %s" % url)
                continue
            self.unscan(branch)

    def unscan(self, branch):
        self.logger.info(
            "Unscanning %s (last scanned id: %s)", branch.displayname,
            branch.last_scanned_id)
        self.logger.debug("Purging BranchRevisions.")
        IStore(BranchRevision).find(BranchRevision, branch=branch).remove()

        self.logger.debug("Resetting scan data.")
        branch.last_scanned = branch.last_scanned_id = None
        branch.revision_count = 0

        if self.options.rescan:
            self.logger.debug("Requesting rescan.")
            job = BranchScanJob.create(branch)
            job.celeryRunOnCommit()

        transaction.commit()
