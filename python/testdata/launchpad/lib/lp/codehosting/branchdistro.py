# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Opening a new DistroSeries for branch based development.

Intended to be run just after a new distro series has been completed, this
script will create an official package branch in the new series for every one
in the old.  The old branch will become stacked on the new, to avoid a using
too much disk space whilst retaining best performance for the new branch.
"""

__metaclass__ = type
__all__ = [
    'DistroBrancher',
    'switch_branches',
    ]

import os

from bzrlib.branch import Branch
from bzrlib.bzrdir import BzrDir
from bzrlib.errors import (
    NotBranchError,
    NotStacked,
    )
from bzrlib.revision import NULL_REVISION
import transaction
from zope.component import getUtility

from lp.code.enums import (
    BranchLifecycleStatus,
    BranchType,
    )
from lp.code.errors import BranchExists
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.branchnamespace import IBranchNamespaceSet
from lp.code.interfaces.seriessourcepackagebranch import (
    IFindOfficialBranchLinks,
    )
from lp.code.model.branchrevision import BranchRevision
from lp.codehosting.vfs import branch_id_to_path
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.config import config
from lp.services.database.interfaces import IMasterStore


def switch_branches(prefix, scheme, old_db_branch, new_db_branch):
    """Move bzr data from an old to a new branch, leaving old stacked on new.

    This function is intended to be used just after Ubuntu is released to
    create (at the bzr level) a new trunk branch for a source package for the
    next release of the distribution.  We move the bzr data to the location
    for the new branch and replace the trunk branch for the just released
    version with a stacked branch pointing at the new branch.

    The procedure is to complicated to be carried out atomically, so if this
    function is interrupted things may be a little inconsistent (e.g. there
    might be a branch in the old location, but not stacked on the new location
    yet).  There should be no data loss though.

    :param prefix: The non-branch id dependent part of the physical path to
        the branches on disk.
    :param scheme: The branches should be open-able at a URL of the form
        ``scheme + :/// + unique_name``.
    :param old_db_branch: The branch that currently has the trunk bzr data.
    :param old_db_branch: The new trunk branch.  This should not have any
        presence on disk yet.
    """
    # Move .bzr directory from old to new location, crashing through the
    # abstraction we usually hide our branch locations behind.
    old_underlying_path = os.path.join(
        prefix, branch_id_to_path(old_db_branch.id))
    new_underlying_path = os.path.join(
        prefix, branch_id_to_path(new_db_branch.id))
    os.makedirs(new_underlying_path)
    os.rename(
        os.path.join(old_underlying_path, '.bzr'),
        os.path.join(new_underlying_path, '.bzr'))

    # Create branch at old location -- we use the "clone('null:')" trick to
    # preserve the format.  We have to open at the logical, unique_name-based,
    # location so that it works to set the stacked on url to '/' + a
    # unique_name.
    new_location_bzrdir = BzrDir.open(
        scheme + ':///' + new_db_branch.unique_name)
    old_location_bzrdir = new_location_bzrdir.clone(
        scheme + ':///' + old_db_branch.unique_name, revision_id='null:')

    # Set the stacked on url for old location.
    old_location_branch = old_location_bzrdir.open_branch()
    old_location_branch.set_stacked_on_url('/' + new_db_branch.unique_name)

    # Pull from new location to old -- this won't actually transfer any
    # revisions, just update the last revision pointer.
    old_location_branch.pull(new_location_bzrdir.open_branch())


class DistroBrancher:
    """Open a new distroseries for branch based development.

    `makeNewBranches` will create an official package branch in the new series
    for every one in the old.  `checkNewBranches` will check that a previous
    run of this script completed successfully -- this is only likely to be
    really useful if a script run died halfway through or had to be killed.
    """

    def __init__(self, logger, old_distroseries, new_distroseries):
        """Construct a `DistroBrancher`.

        The old and new distroseries must be from the same distribution, but
        not the same distroseries.

        :param logger: A Logger.  Problems will be logged to this object at
            the WARNING level or higher; progress reports will be logged at
            the DEBUG level.
        :param old_distroseries: The distroseries that will be examined to
            find existing source package branches.
        :param new_distroseries: The distroseries that will have new official
            source branches made for it.
        """
        self.logger = logger
        if old_distroseries.distribution != new_distroseries.distribution:
            raise AssertionError(
                "%s and %s are from different distributions!" %
                (old_distroseries, new_distroseries))
        if old_distroseries == new_distroseries:
            raise AssertionError(
                "New and old distributions must be different!")
        self.old_distroseries = old_distroseries
        self.new_distroseries = new_distroseries

    @classmethod
    def fromNames(cls, logger, distribution_name, old_distroseries_name,
                  new_distroseries_name):
        """Make a `DistroBrancher` from the names of a distro and two series.
        """
        distribution = getUtility(IDistributionSet).getByName(
            distribution_name)
        new_distroseries = distribution.getSeries(new_distroseries_name)
        old_distroseries = distribution.getSeries(old_distroseries_name)
        return cls(logger, old_distroseries, new_distroseries)

    def _existingOfficialBranches(self):
        """Return the collection of official branches in the old distroseries.
        """
        branches = getUtility(IAllBranches)
        distroseries_branches = branches.inDistroSeries(self.old_distroseries)
        return distroseries_branches.officialBranches().getBranches(
            eager_load=False)

    def checkConsistentOfficialPackageBranch(self, db_branch):
        """Check that `db_branch` is a consistent official package branch.

        'Consistent official package branch' means:

         * It's a package branch (rather than a personal or junk branch).
         * It's official for its SourcePackage and no other.

        This function simply returns True or False -- any problems will be
        logged to ``self.logger``.

        :param db_branch: The `IBranch` to check.
        :return: ``True`` if the branch is a consistent official package
            branch, ``False`` otherwise.
        """
        if db_branch.product:
            self.logger.warning(
                "Encountered unexpected product branch %r",
                db_branch.unique_name)
            return False
        if not db_branch.distroseries:
            self.logger.warning(
                "Encountered unexpected personal branch %s",
                db_branch.unique_name)
            return False
        find_branch_links = getUtility(IFindOfficialBranchLinks)
        links = list(find_branch_links.findForBranch(db_branch))
        if len(links) == 0:
            self.logger.warning(
                "%s is not an official branch", db_branch.unique_name)
            return False
        elif len(links) > 1:
            series_text = ', '.join([
                link.sourcepackage.path for link in links])
            self.logger.warning(
                "%s is official for multiple series: %s",
                db_branch.unique_name, series_text)
            return False
        elif links[0].sourcepackage != db_branch.sourcepackage:
            self.logger.warning(
                "%s is the official branch for %s but not its "
                "sourcepackage", db_branch.unique_name,
                links[0].sourcepackage.path)
            return False
        return True

    def makeNewBranches(self):
        """Make official branches in the new distroseries."""
        for db_branch in self._existingOfficialBranches():
            self.logger.debug("Processing %s" % db_branch.unique_name)
            try:
                self.makeOneNewBranch(db_branch)
            except BranchExists:
                pass

    def checkNewBranches(self):
        """Check the branches in the new distroseries are present and correct.

        This function checks that every official package branch in the old
        distroseries has a matching branch in the new distroseries and that
        stacking is set up as we expect on disk.

        Every branch will be checked, even if some fail.

        This function simply returns True or False -- any problems will be
        logged to ``self.logger``.

        :return: ``True`` if every branch passes the check, ``False``
            otherwise.
        """
        ok = True
        for db_branch in self._existingOfficialBranches():
            self.logger.debug("Checking %s" % db_branch.unique_name)
            try:
                if not self.checkOneBranch(db_branch):
                    ok = False
            except:
                ok = False
                self.logger.exception(
                    "Unexpected error checking %s!", db_branch)
        return ok

    def checkOneBranch(self, old_db_branch):
        """Check a branch in the old distroseries has been copied to the new.

        This function checks that `old_db_branch` has a matching branch in the
        new distroseries and that stacking is set up as we expect on disk.

        This function simply returns True or False -- any problems will be
        logged to ``self.logger``.

        :param old_db_branch: The branch to check.
        :return: ``True`` if the branch passes the check, ``False`` otherwise.
        """
        ok = self.checkConsistentOfficialPackageBranch(old_db_branch)
        if not ok:
            return ok
        new_sourcepackage = self.new_distroseries.getSourcePackage(
            old_db_branch.sourcepackagename)
        new_db_branch = new_sourcepackage.getBranch(
            PackagePublishingPocket.RELEASE)
        if new_db_branch is None:
            self.logger.warning(
                "No official branch found for %s",
                new_sourcepackage.path)
            return False
        ok = self.checkConsistentOfficialPackageBranch(new_db_branch)
        if not ok:
            return ok
        # the branch in the new distroseries is unstacked
        new_location = 'lp-internal:///' + new_db_branch.unique_name
        try:
            new_bzr_branch = Branch.open(new_location)
        except NotBranchError:
            self.logger.warning(
                "No bzr branch at new location %s", new_location)
            ok = False
        else:
            try:
                new_stacked_on_url = new_bzr_branch.get_stacked_on_url()
                ok = False
                self.logger.warning(
                    "New branch at %s is stacked on %s, should be "
                    "unstacked.", new_location, new_stacked_on_url)
            except NotStacked:
                pass
        # The branch in the old distroseries is stacked on that in the
        # new.
        old_location = 'lp-internal:///' + old_db_branch.unique_name
        try:
            old_bzr_branch = Branch.open(old_location)
        except NotBranchError:
            self.logger.warning(
                "No bzr branch at old location %s", old_location)
            ok = False
        else:
            try:
                old_stacked_on_url = old_bzr_branch.get_stacked_on_url()
                if old_stacked_on_url != '/' + new_db_branch.unique_name:
                    self.logger.warning(
                        "Old branch at %s is stacked on %s, should be "
                        "stacked on %s", old_location, old_stacked_on_url,
                        '/' + new_db_branch.unique_name)
                    ok = False
            except NotStacked:
                self.logger.warning(
                    "Old branch at %s is not stacked, should be stacked "
                    "on %s", old_location,
                    '/' + new_db_branch.unique_name)
                ok = False
            # The branch in the old distroseries has no revisions in its
            # repository.  We open the repository independently of the
            # branch because the branch's repository has had its fallback
            # location activated. Note that this check might fail if new
            # revisions get pushed to the branch in the old distroseries,
            # which shouldn't happen but isn't totally impossible.
            old_repo = BzrDir.open(old_location).open_repository()
            if len(old_repo.all_revision_ids()) > 0:
                self.logger.warning(
                    "Repository at %s has %s revisions.",
                    old_location, len(old_repo.all_revision_ids()))
                ok = False
            # The branch in the old distroseries has at least some
            # history.  (We can't check that the tips are the same because
            # the branch in the new distroseries might have new revisons).
            if old_bzr_branch.last_revision() == 'null:':
                self.logger.warning(
                    "Old branch at %s has null tip revision.",
                    old_location)
                ok = False
        return ok

    def makeOneNewBranch(self, old_db_branch):
        """Copy a branch to the new distroseries.

        This function makes a new database branch for the same source package
        as old_db_branch but in the new distroseries and then uses
        `switch_branches` to move the underlying bzr branch to the new series
        and replace the old branch with a branch stacked on the new series'
        branch.

        :param old_db_branch: The branch to copy into the new distroseries.
        :raises BranchExists: This will be raised if old_db_branch has already
            been copied to the new distroseries (in the database, at least).
        """
        if not self.checkConsistentOfficialPackageBranch(old_db_branch):
            self.logger.warning("Skipping branch")
            return
        new_namespace = getUtility(IBranchNamespaceSet).get(
            person=old_db_branch.owner, product=None,
            distroseries=self.new_distroseries,
            sourcepackagename=old_db_branch.sourcepackagename)
        new_db_branch = new_namespace.createBranch(
            BranchType.HOSTED, self.new_distroseries.name,
            old_db_branch.registrant)
        new_db_branch.sourcepackage.setBranch(
            PackagePublishingPocket.RELEASE, new_db_branch,
            new_db_branch.owner)
        old_db_branch.lifecycle_status = BranchLifecycleStatus.MATURE
        # switch_branches *moves* the data to locations dependent on the
        # new_branch's id, so if the transaction was rolled back we wouldn't
        # know the branch id and thus wouldn't be able to find the branch data
        # again.  So commit before doing that.
        transaction.commit()
        switch_branches(
            config.codehosting.mirrored_branches_root,
            'lp-internal', old_db_branch, new_db_branch)
        # Directly copy the branch revisions from the old branch to the new
        # branch.
        store = IMasterStore(BranchRevision)
        store.execute(
            """
            INSERT INTO BranchRevision (branch, revision, sequence)
            SELECT %s, BranchRevision.revision, BranchRevision.sequence
            FROM BranchRevision
            WHERE branch = %s
            """ % (new_db_branch.id, old_db_branch.id))

        # Update the scanned details first, that way when hooking into
        # branchChanged, it won't try to create a new scan job.
        tip_revision = old_db_branch.getTipRevision()
        new_db_branch.updateScannedDetails(
            tip_revision, old_db_branch.revision_count)
        tip_revision_id = (
            tip_revision.revision_id if tip_revision is not None else
            NULL_REVISION)
        new_db_branch.branchChanged(
            '', tip_revision_id,
            old_db_branch.control_format,
            old_db_branch.branch_format,
            old_db_branch.repository_format)
        old_db_branch.stacked_on = new_db_branch
        transaction.commit()
        return new_db_branch
