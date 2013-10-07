# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions for code testing live here."""

__metaclass__ = type
__all__ = [
    'add_revision_to_branch',
    'get_non_existant_source_package_branch_unique_name',
    'make_erics_fooix_project',
    'make_linked_package_branch',
    'make_merge_proposal_without_reviewers',
    'make_official_package_branch',
    'make_project_branch_with_revisions',
    'make_project_cloud_data',
    'remove_all_sample_data_branches',
    ]


from contextlib import contextmanager
from datetime import timedelta
from difflib import unified_diff
from itertools import count

from bzrlib.plugins.builder.recipe import RecipeParser
import transaction
from zope.component import getUtility
from zope.security.proxy import (
    isinstance as zisinstance,
    removeSecurityProxy,
    )

from lp.app.enums import InformationType
from lp.code.interfaces.branchmergeproposal import (
    IBranchMergeProposalJobSource,
    )
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.code.interfaces.revision import IRevisionSet
from lp.code.model.seriessourcepackagebranch import (
    SeriesSourcePackageBranchSet,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.sqlbase import cursor
from lp.testing import (
    run_with_login,
    time_counter,
    )


def mark_all_merge_proposal_jobs_done():
    """Sometimes in tests we want to clear out all pending jobs.

    This function iterates through all the pending jobs and marks the done.
    """
    while True:
        jobs = list(getUtility(IBranchMergeProposalJobSource).iterReady())
        if len(jobs) == 0:
            break
        for job in jobs:
            job.start()
            job.complete()


def add_revision_to_branch(factory, branch, revision_date, date_created=None,
                           mainline=True, commit_msg=None):
    """Add a new revision to the branch with the specified revision date.

    If date_created is None, it gets set to the revision_date.
    """
    if date_created is None:
        date_created = revision_date
    parent = branch.revision_history.last()
    if parent is None:
        parent_ids = []
    else:
        parent_ids = [parent.revision.revision_id]
    revision = factory.makeRevision(
        revision_date=revision_date, date_created=date_created,
        log_body=commit_msg, parent_ids=parent_ids)
    if mainline:
        sequence = branch.revision_count + 1
        branch_revision = branch.createBranchRevision(sequence, revision)
        branch.updateScannedDetails(revision, sequence)
    else:
        branch_revision = branch.createBranchRevision(None, revision)
    return branch_revision


def make_erics_fooix_project(factory):
    """Make Eric, the Fooix project, and some branches.

    :return: a dict of objects to put into local scope.
    """
    eric = factory.makePerson(
        name='eric', displayname='Eric the Viking', email='eric@example.com')
    fooix = factory.makeProduct(
        name='fooix', displayname='Fooix', owner=eric)
    trunk = factory.makeProductBranch(
        owner=eric, product=fooix, name='trunk')
    removeSecurityProxy(fooix.development_focus).branch = trunk
    # Development is done by Fred.
    fred = factory.makePerson(
        name='fred', displayname='Fred Flintstone', email='fred@example.com')
    feature = factory.makeProductBranch(
        owner=fred, product=fooix, name='feature')
    proposed = factory.makeProductBranch(
        owner=fred, product=fooix, name='proposed')
    bmp = proposed.addLandingTarget(
        registrant=fred, target_branch=trunk, needs_review=True,
        review_requests=[(eric, 'code')])
    # And fake a diff.
    naked_bmp = removeSecurityProxy(bmp)
    preview = removeSecurityProxy(naked_bmp.updatePreviewDiff(
        ''.join(unified_diff('', 'random content')), u'rev-a', u'rev-b'))
    naked_bmp.source_branch.last_scanned_id = preview.source_revision_id
    naked_bmp.target_branch.last_scanned_id = preview.target_revision_id
    preview.diff_lines_count = 47
    preview.added_lines_count = 7
    preview.remvoed_lines_count = 13
    preview.diffstat = {'file1': (3, 8), 'file2': (4, 5)}
    return {
        'eric': eric, 'fooix': fooix, 'trunk': trunk, 'feature': feature,
        'proposed': proposed, 'fred': fred}


def make_linked_package_branch(factory, distribution=None,
                               sourcepackagename=None):
    """Make a new package branch and make it official."""
    distro_series = factory.makeDistroSeries(distribution)
    source_package = factory.makeSourcePackage(
        sourcepackagename=sourcepackagename, distroseries=distro_series)
    branch = factory.makePackageBranch(sourcepackage=source_package)
    pocket = PackagePublishingPocket.RELEASE
    # It is possible for the param to be None, so reset to the factory
    # generated one.
    sourcepackagename = source_package.sourcepackagename
    SeriesSourcePackageBranchSet.new(
        distro_series, pocket, sourcepackagename, branch, branch.owner)
    return branch


def consistent_branch_names():
    """Provide a generator for getting consistent branch names.

    This generator does not finish!
    """
    for name in ['trunk', 'testing', 'feature-x', 'feature-y', 'feature-z']:
        yield name
    index = count(1)
    while True:
        yield "branch-%s" % index.next()


def make_package_branches(factory, series, sourcepackagename, branch_count,
                          official_count=0, owner=None, registrant=None):
    """Make some package branches.

    Make `branch_count` branches, and make `official_count` of those
    official branches.
    """
    if zisinstance(sourcepackagename, basestring):
        sourcepackagename = factory.getOrMakeSourcePackageName(
            sourcepackagename)
    # Make the branches created in the past in order.
    time_gen = time_counter(delta=timedelta(days=-1))
    branch_names = consistent_branch_names()
    branches = [
        factory.makePackageBranch(
            distroseries=series,
            sourcepackagename=sourcepackagename,
            date_created=time_gen.next(),
            name=branch_names.next(), owner=owner, registrant=registrant)
        for i in range(branch_count)]

    official = []
    # Sort the pocket items so RELEASE is last, and thus first popped.
    pockets = sorted(PackagePublishingPocket.items, reverse=True)
    # Since there can be only one link per pocket, max out the number of
    # official branches at the pocket count.
    for i in range(min(official_count, len(pockets))):
        branch = branches.pop()
        pocket = pockets.pop()
        SeriesSourcePackageBranchSet.new(
            series, pocket, sourcepackagename, branch, branch.owner)
        official.append(branch)

    return series, branches, official


def make_mint_distro_with_branches(factory):
    """This method makes a distro called mint with many branches.

    The mint distro has the following series and status:
        wild - experimental
        dev - development
        stable - current
        old - supported
        very-old - supported
        ancient - supported
        mouldy - supported
        dead - obsolete

    The mint distro has a team: mint-team, which has Albert, Bob, and Charlie
    as members.

    There are four different source packages:
        twisted, zope, bzr, python
    """
    albert, bob, charlie = [
        factory.makePerson(name=name, email=("%s@mint.example.com" % name))
        for name in ('albert', 'bob', 'charlie')]
    mint_team = factory.makeTeam(owner=albert, name="mint-team")
    mint_team.addMember(bob, albert)
    mint_team.addMember(charlie, albert)
    mint = factory.makeDistribution(
        name='mint', displayname='Mint', owner=albert, members=mint_team)
    series = [
        ("wild", "5.5", SeriesStatus.EXPERIMENTAL),
        ("dev", "4.0", SeriesStatus.DEVELOPMENT),
        ("stable", "3.0", SeriesStatus.CURRENT),
        ("old", "2.0", SeriesStatus.SUPPORTED),
        ("very-old", "1.5", SeriesStatus.SUPPORTED),
        ("ancient", "1.0", SeriesStatus.SUPPORTED),
        ("mouldy", "0.6", SeriesStatus.SUPPORTED),
        ("dead", "0.1", SeriesStatus.OBSOLETE),
        ]
    for name, version, status in series:
        factory.makeDistroSeries(
            distribution=mint, version=version, status=status, name=name)

    for pkg_index, name in enumerate(['twisted', 'zope', 'bzr', 'python']):
        for series_index, series in enumerate(mint.series):
            # Over the series and source packages, we want to have different
            # combinations of official and branch counts.
            # Make the more recent series have most official branches.
            official_count = 6 - series_index
            branch_count = official_count + pkg_index
            make_package_branches(
                factory, series, name, branch_count, official_count,
                owner=mint_team, registrant=albert)


def make_official_package_branch(factory, owner=None):
    """Make a branch linked to the pocket of a source package."""
    branch = factory.makePackageBranch(owner=owner)
    # Make sure the (distroseries, pocket) combination used allows us to
    # upload to it.
    stable_states = (
        SeriesStatus.SUPPORTED, SeriesStatus.CURRENT)
    if branch.distroseries.status in stable_states:
        pocket = PackagePublishingPocket.BACKPORTS
    else:
        pocket = PackagePublishingPocket.RELEASE
    sourcepackage = branch.sourcepackage
    suite_sourcepackage = sourcepackage.getSuiteSourcePackage(pocket)
    registrant = factory.makePerson()
    run_with_login(
        suite_sourcepackage.distribution.owner,
        ICanHasLinkedBranch(suite_sourcepackage).setBranch,
        branch, registrant)
    return branch


def make_project_branch_with_revisions(factory, date_generator, product=None,
                                       private=None, revision_count=None):
    """Make a new branch with revisions."""
    if revision_count is None:
        revision_count = 5
    if private:
        information_type = InformationType.USERDATA
    else:
        information_type = InformationType.PUBLIC
    branch = factory.makeProductBranch(
        product=product, information_type=information_type)
    naked_branch = removeSecurityProxy(branch)
    factory.makeRevisionsForBranch(
        naked_branch, count=revision_count, date_generator=date_generator)
    # The code that updates the revision cache doesn't need to care about
    # the privacy of the branch.
    getUtility(IRevisionSet).updateRevisionCacheForBranch(naked_branch)
    return branch


def make_project_cloud_data(factory, details):
    """Make test data to populate the project cloud.

    Details is a list of tuples containing:
      (project-name, num_commits, num_authors, last_commit)
    """
    delta = timedelta(seconds=1)
    for project_name, num_commits, num_authors, last_commit in details:
        project = factory.makeProduct(name=project_name)
        start_date = last_commit - delta * (num_commits - 1)
        gen = time_counter(start_date, delta)
        commits_each = num_commits / num_authors
        for committer in range(num_authors - 1):
            make_project_branch_with_revisions(
                factory, gen, project, commits_each)
            num_commits -= commits_each
        make_project_branch_with_revisions(
            factory, gen, project, revision_count=num_commits)
    transaction.commit()


@contextmanager
def recipe_parser_newest_version(version):
    old_version = RecipeParser.NEWEST_VERSION
    RecipeParser.NEWEST_VERSION = version
    try:
        yield
    finally:
        RecipeParser.NEWEST_VERSION = old_version


def make_merge_proposal_without_reviewers(factory, **kwargs):
    """Make a merge proposal and strip of any review votes."""
    proposal = factory.makeBranchMergeProposal(**kwargs)
    for vote in proposal.votes:
        removeSecurityProxy(vote).destroySelf()
    return proposal


def get_non_existant_source_package_branch_unique_name(owner, factory):
    """Return the unique name for a non-existanct source package branch.

    Neither the branch nor the source package name will exist.
    """
    distroseries = factory.makeDistroSeries()
    source_package = factory.getUniqueString('source-package')
    branch = factory.getUniqueString('branch')
    return '~%s/%s/%s/%s/%s' % (
        owner, distroseries.distribution.name, distroseries.name,
        source_package, branch)


def remove_all_sample_data_branches():
    c = cursor()
    c.execute('delete from bugbranch')
    c.execute('delete from specificationbranch')
    c.execute('update productseries set branch=NULL')
    c.execute('delete from branchrevision')
    c.execute('delete from branchsubscription')
    c.execute('delete from codeimportjob')
    c.execute('delete from codeimport')
    c.execute('delete from branch')
