# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Errors used in the lp/code modules."""

__metaclass__ = type
__all__ = [
    'AlreadyLatestFormat',
    'BadBranchMergeProposalSearchContext',
    'BadStateTransition',
    'BranchCreationException',
    'BranchCreationForbidden',
    'BranchCreatorNotMemberOfOwnerTeam',
    'BranchCreatorNotOwner',
    'BranchExists',
    'BranchHasPendingWrites',
    'BranchTargetError',
    'BranchTypeError',
    'BuildAlreadyPending',
    'BuildNotAllowedForDistro',
    'BranchMergeProposalExists',
    'CannotDeleteBranch',
    'CannotUpgradeBranch',
    'CannotUpgradeNonHosted',
    'CannotHaveLinkedBranch',
    'CodeImportAlreadyRequested',
    'CodeImportAlreadyRunning',
    'CodeImportNotInReviewedState',
    'ClaimReviewFailed',
    'InvalidBranchMergeProposal',
    'InvalidMergeQueueConfig',
    'InvalidNamespace',
    'NoLinkedBranch',
    'NoSuchBranch',
    'PrivateBranchRecipe',
    'ReviewNotPending',
    'StaleLastMirrored',
    'TooManyBuilds',
    'TooNewRecipeFormat',
    'UnknownBranchTypeError',
    'UpdatePreviewDiffNotReady',
    'UpgradePending',
    'UserHasExistingReview',
    'UserNotBranchReviewer',
    'WrongBranchMergeProposal',
]

import httplib

from bzrlib.plugins.builder.recipe import RecipeParseError
from lazr.restful.declarations import error_status

from lp.app.errors import NameLookupFailed

# Annotate the RecipeParseError's with a 400 webservice status.
error_status(httplib.BAD_REQUEST)(RecipeParseError)


class BadBranchMergeProposalSearchContext(Exception):
    """The context is not valid for a branch merge proposal search."""


@error_status(httplib.BAD_REQUEST)
class BadStateTransition(Exception):
    """The user requested a state transition that is not possible."""


class BranchCreationException(Exception):
    """Base class for branch creation exceptions."""


@error_status(httplib.CONFLICT)
class BranchExists(BranchCreationException):
    """Raised when creating a branch that already exists."""

    def __init__(self, existing_branch):
        # XXX: TimPenhey 2009-07-12 bug=405214: This error
        # message logic is incorrect, but the exact text is being tested
        # in branch-xmlrpc.txt.
        params = {'name': existing_branch.name}
        if existing_branch.product is None:
            params['maybe_junk'] = 'junk '
            params['context'] = existing_branch.owner.name
        else:
            params['maybe_junk'] = ''
            params['context'] = '%s in %s' % (
                existing_branch.owner.name, existing_branch.product.name)
        message = (
            'A %(maybe_junk)sbranch with the name "%(name)s" already exists '
            'for %(context)s.' % params)
        self.existing_branch = existing_branch
        BranchCreationException.__init__(self, message)


class BranchHasPendingWrites(Exception):
    """Raised if the branch can't be processed because a write is pending.

    In this case the operation can usually be retried in a while.

    See bug 612171.
    """


class BranchTargetError(Exception):
    """Raised when there is an error determining a branch target."""


@error_status(httplib.BAD_REQUEST)
class CannotDeleteBranch(Exception):
    """The branch cannot be deleted at this time."""


class BranchCreationForbidden(BranchCreationException):
    """A Branch visibility policy forbids branch creation.

    The exception is raised if the policy for the product does not allow
    the creator of the branch to create a branch for that product.
    """


@error_status(httplib.BAD_REQUEST)
class BranchCreatorNotMemberOfOwnerTeam(BranchCreationException):
    """Branch creator is not a member of the owner team.

    Raised when a user is attempting to create a branch and set the owner of
    the branch to a team that they are not a member of.
    """


@error_status(httplib.BAD_REQUEST)
class BranchCreatorNotOwner(BranchCreationException):
    """A user cannot create a branch belonging to another user.

    Raised when a user is attempting to create a branch and set the owner of
    the branch to another user.
    """


class BranchTypeError(Exception):
    """An operation cannot be performed for a particular branch type.

    Some branch operations are only valid for certain types of branches.  The
    BranchTypeError exception is raised if one of these operations is called
    with a branch of the wrong type.
    """


class InvalidBranchException(Exception):
    """Base exception for an error resolving a branch for a component.

    Subclasses should set _msg_template to match their required display
    message.
    """

    _msg_template = "Invalid branch for: %s"

    def __init__(self, component):
        self.component = component
        # It's expected that components have a name attribute,
        # so let's assume they will and deal with any error if it occurs.
        try:
            component_name = component.name
        except AttributeError:
            component_name = str(component)
        # The display_message contains something readable for the user.
        self.display_message = self._msg_template % component_name
        Exception.__init__(self, self._msg_template % (repr(component),))


class CannotHaveLinkedBranch(InvalidBranchException):
    """Raised when we try to get the linked branch for a thing that can't."""

    _msg_template = "%s cannot have linked branches."


class CannotUpgradeBranch(Exception):
    """"Made for subclassing."""

    def __init__(self, branch):
        super(CannotUpgradeBranch, self).__init__(
            self._msg_template % branch.bzr_identity)
        self.branch = branch


class AlreadyLatestFormat(CannotUpgradeBranch):
    """Raised on attempt to upgrade a branch already in the latest format."""

    _msg_template = (
        'Branch %s is in the latest format, so it cannot be upgraded.')


class CannotUpgradeNonHosted(CannotUpgradeBranch):

    """Raised on attempt to upgrade a non-Hosted branch."""

    _msg_template = 'Cannot upgrade non-hosted branch %s'


class UpgradePending(CannotUpgradeBranch):

    """Raised on attempt to upgrade a branch already in the latest format."""

    _msg_template = 'An upgrade is already in progress for branch %s.'


class ClaimReviewFailed(Exception):
    """The user cannot claim the pending review."""


@error_status(httplib.BAD_REQUEST)
class InvalidBranchMergeProposal(Exception):
    """Raised during the creation of a new branch merge proposal.

    The text of the exception is the rule violation.
    """


@error_status(httplib.BAD_REQUEST)
class BranchMergeProposalExists(InvalidBranchMergeProposal):
    """Raised if there is already a matching BranchMergeProposal."""

    def __init__(self, existing_proposal):
        super(BranchMergeProposalExists, self).__init__(
                'There is already a branch merge proposal registered for '
                'branch %s to land on %s that is still active.' %
                (existing_proposal.source_branch.displayname,
                 existing_proposal.target_branch.displayname))
        self.existing_proposal = existing_proposal


class InvalidNamespace(Exception):
    """Raised when someone tries to lookup a namespace with a bad name.

    By 'bad', we mean that the name is unparsable. It might be too short, too
    long or malformed in some other way.
    """

    def __init__(self, name):
        self.name = name
        Exception.__init__(
            self, "Cannot understand namespace name: '%s'" % (name,))


class NoLinkedBranch(InvalidBranchException):
    """Raised when there's no linked branch for a thing."""

    _msg_template = "%s has no linked branch."


class NoSuchBranch(NameLookupFailed):
    """Raised when we try to load a branch that does not exist."""

    _message_prefix = "No such branch"


class StaleLastMirrored(Exception):
    """Raised when last_mirrored_id is out of date with on-disk value."""

    def __init__(self, db_branch, info):
        """Constructor.

        :param db_branch: The database branch.
        :param info: A dict of information about the branch, as produced by
            lp.codehosting.bzrutils.get_branch_info
        """
        self.db_branch = db_branch
        self.info = info
        Exception.__init__(
            self,
            'Database last_mirrored_id %s does not match on-disk value %s' %
            (db_branch.last_mirrored_id, self.info['last_revision_id']))


@error_status(httplib.BAD_REQUEST)
class PrivateBranchRecipe(Exception):

    def __init__(self, branch):
        message = (
            'Recipe may not refer to private branch: %s' %
            branch.bzr_identity)
        self.branch = branch
        Exception.__init__(self, message)


class ReviewNotPending(Exception):
    """The requested review is not in a pending state."""


class UpdatePreviewDiffNotReady(Exception):
    """Raised if the preview diff is not ready to run."""


class UserHasExistingReview(Exception):
    """The user has an existing review."""


class UserNotBranchReviewer(Exception):
    """The user who attempted to review the merge proposal isn't a reviewer.

    A specific reviewer may be set on a branch.  If a specific reviewer
    isn't set then any user in the team of the owner of the branch is
    considered a reviewer.
    """


class WrongBranchMergeProposal(Exception):
    """The comment requested is not associated with this merge proposal."""


class UnknownBranchTypeError(Exception):
    """Raised when the user specifies an unrecognized branch type."""


@error_status(httplib.BAD_REQUEST)
class CodeImportNotInReviewedState(Exception):
    """Raised when the user requests an import of a non-automatic import."""


class CodeImportAlreadyRequested(Exception):
    """Raised when the user requests an import that is already requested."""

    def __init__(self, msg, requesting_user):
        super(CodeImportAlreadyRequested, self).__init__(msg)
        self.requesting_user = requesting_user


@error_status(httplib.BAD_REQUEST)
class CodeImportAlreadyRunning(Exception):
    """Raised when the user requests an import that is already running."""


@error_status(httplib.BAD_REQUEST)
class TooNewRecipeFormat(Exception):
    """The format of the recipe supplied was too new."""

    def __init__(self, supplied_format, newest_supported):
        super(TooNewRecipeFormat, self).__init__()
        self.supplied_format = supplied_format
        self.newest_supported = newest_supported


@error_status(httplib.BAD_REQUEST)
class RecipeBuildException(Exception):

    def __init__(self, recipe, distroseries, template):
        self.recipe = recipe
        self.distroseries = distroseries
        msg = template % {'recipe': recipe, 'distroseries': distroseries}
        Exception.__init__(self, msg)


class TooManyBuilds(RecipeBuildException):
    """A build was requested that exceeded the quota."""

    def __init__(self, recipe, distroseries):
        RecipeBuildException.__init__(
            self, recipe, distroseries,
            'You have exceeded your quota for recipe %(recipe)s for'
            ' distroseries %(distroseries)s')


class BuildAlreadyPending(RecipeBuildException):
    """A build was requested when an identical build was already pending."""

    def __init__(self, recipe, distroseries):
        RecipeBuildException.__init__(
            self, recipe, distroseries,
            'An identical build of this recipe is already pending.')


class BuildNotAllowedForDistro(RecipeBuildException):
    """A build was requested against an unsupported distroseries."""

    def __init__(self, recipe, distroseries):
        RecipeBuildException.__init__(
            self, recipe, distroseries,
            'A build against this distro is not allowed.')


@error_status(httplib.BAD_REQUEST)
class InvalidMergeQueueConfig(Exception):
    """The config specified is not a valid JSON string."""

    def __init__(self):
        message = ('The configuration specified is not a valid JSON string.')
        Exception.__init__(self, message)
