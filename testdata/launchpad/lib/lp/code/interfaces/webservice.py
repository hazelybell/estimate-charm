# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.code.interfaces.webservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__all__ = [
    'BranchCreatorNotMemberOfOwnerTeam',
    'BranchCreatorNotOwner',
    'BranchExists',
    'BranchMergeProposalExists',
    'BuildAlreadyPending',
    'CodeImportAlreadyRunning',
    'CodeImportNotInReviewedState',
    'IBranch',
    'IBranchMergeProposal',
    'IBranchSet',
    'IBranchSubscription',
    'ICodeImport',
    'ICodeReviewComment',
    'ICodeReviewVoteReference',
    'IDiff',
    'IPreviewDiff',
    'ISourcePackageRecipe',
    'ISourcePackageRecipeBuild',
    'TooManyBuilds',
    ]

# The exceptions are imported so that they can produce the special
# status code defined by error_status when they are raised.
from lp.code.errors import (
    BranchCreatorNotMemberOfOwnerTeam,
    BranchCreatorNotOwner,
    BranchExists,
    BranchMergeProposalExists,
    BuildAlreadyPending,
    CodeImportAlreadyRunning,
    CodeImportNotInReviewedState,
    TooManyBuilds,
    )
from lp.code.interfaces.branch import (
    IBranch,
    IBranchSet,
    )
from lp.code.interfaces.branchmergeproposal import IBranchMergeProposal
from lp.code.interfaces.branchmergequeue import IBranchMergeQueue
from lp.code.interfaces.branchsubscription import IBranchSubscription
from lp.code.interfaces.codeimport import ICodeImport
from lp.code.interfaces.codereviewcomment import ICodeReviewComment
from lp.code.interfaces.codereviewvote import ICodeReviewVoteReference
from lp.code.interfaces.diff import (
    IDiff,
    IPreviewDiff,
    )
from lp.code.interfaces.sourcepackagerecipe import ISourcePackageRecipe
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuild,
    )


IBranchMergeQueue['branches'].value_type.schema = IBranch

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
_schema_circular_imports
