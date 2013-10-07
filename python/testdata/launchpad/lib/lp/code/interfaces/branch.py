# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Branch interfaces."""

__metaclass__ = type

__all__ = [
    'BRANCH_NAME_VALIDATION_ERROR_MESSAGE',
    'branch_name_validator',
    'BzrIdentityMixin',
    'DEFAULT_BRANCH_STATUS_IN_LISTING',
    'get_blacklisted_hostnames',
    'get_db_branch_info',
    'IBranch',
    'IBranchBatchNavigator',
    'IBranchCloud',
    'IBranchDelta',
    'IBranchListingQueryOptimiser',
    'IBranchNavigationMenu',
    'IBranchSet',
    'user_has_special_branch_access',
    'WrongNumberOfReviewTypeArguments',
    ]

import httplib
import re

from lazr.restful.declarations import (
    call_with,
    collection_default_content,
    error_status,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_destructor_operation,
    export_factory_operation,
    export_operation_as,
    export_read_operation,
    export_write_operation,
    exported,
    mutator_for,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    ReferenceChoice,
    )
from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    List,
    Text,
    TextLine,
    )

from lp import _
from lp.app.enums import InformationType
from lp.app.validators import LaunchpadValidationError
from lp.code.bzr import (
    BranchFormat,
    ControlFormat,
    RepositoryFormat,
    )
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchMergeProposalStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    BranchType,
    CodeReviewNotificationLevel,
    )
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.branchmergequeue import IBranchMergeQueue
from lp.code.interfaces.branchtarget import IHasBranchTarget
from lp.code.interfaces.hasbranches import IHasMergeProposals
from lp.code.interfaces.hasrecipes import IHasRecipes
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.role import (
    IHasOwner,
    IPersonRoles,
    )
from lp.services.config import config
from lp.services.fields import (
    PersonChoice,
    PublicPersonChoice,
    URIField,
    Whiteboard,
    )
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )
from lp.services.webapp.interfaces import ITableBatchNavigator


DEFAULT_BRANCH_STATUS_IN_LISTING = (
    BranchLifecycleStatus.EXPERIMENTAL,
    BranchLifecycleStatus.DEVELOPMENT,
    BranchLifecycleStatus.MATURE)


@error_status(httplib.BAD_REQUEST)
class WrongNumberOfReviewTypeArguments(ValueError):
    """Raised in the webservice API if `reviewers` and `review_types`
    do not have equal length.
    """


def get_blacklisted_hostnames():
    """Return a list of hostnames blacklisted for Branch URLs."""
    hostnames = config.codehosting.blacklisted_hostnames
    # If nothing specified, return an empty list. Special-casing since
    # ''.split(',') == [''].
    if hostnames == '':
        return []
    return hostnames.split(',')


class BranchURIField(URIField):

    #XXX leonardr 2009-02-12 [bug=328588]:
    # This code should be removed once the underlying database restriction
    # is removed.
    trailing_slash = False

    # XXX leonardr 2009-02-12 [bug=328588]:
    # This code should be removed once the underlying database restriction
    # is removed.
    def normalize(self, input):
        """Be extra-strict about trailing slashes."""
        # Can't use super-- this derives from an old-style class
        input = URIField.normalize(self, input)
        if self.trailing_slash == False and input[-1] == '/':
            # ensureNoSlash() doesn't trim the slash if the path
            # is empty (eg. http://example.com/). Due to the database
            # restriction on branch URIs, we need to remove a trailing
            # slash in all circumstances.
            input = input[:-1]
        return input

    def _validate(self, value):
        # import here to avoid circular import
        from lp.services.webapp import canonical_url
        from lazr.uri import URI

        # Can't use super-- this derives from an old-style class
        URIField._validate(self, value)
        uri = URI(self.normalize(value))
        launchpad_domain = config.vhost.mainsite.hostname
        if uri.underDomain(launchpad_domain):
            message = _(
                "For Launchpad to mirror a branch, the original branch "
                "cannot be on <code>${domain}</code>.",
                mapping={'domain': html_escape(launchpad_domain)})
            raise LaunchpadValidationError(structured(message))

        for hostname in get_blacklisted_hostnames():
            if uri.underDomain(hostname):
                message = _(
                    'Launchpad cannot mirror branches from %s.'
                    % html_escape(hostname))
                raise LaunchpadValidationError(structured(message))

        # As well as the check against the config, we also need to check
        # against the actual text used in the database constraint.
        constraint_text = 'http://bazaar.launchpad.net'
        if value.startswith(constraint_text):
            message = _(
                "For Launchpad to mirror a branch, the original branch "
                "cannot be on <code>${domain}</code>.",
                mapping={'domain': html_escape(constraint_text)})
            raise LaunchpadValidationError(structured(message))

        if IBranch.providedBy(self.context) and self.context.url == str(uri):
            return  # url was not changed

        if uri.path == '/':
            message = _(
                "URLs for branches cannot point to the root of a site.")
            raise LaunchpadValidationError(message)

        branch = getUtility(IBranchLookup).getByUrl(str(uri))
        if branch is not None:
            message = _(
                'The bzr branch <a href="${url}">${branch}</a> is '
                'already registered with this URL.',
                mapping={'url': html_escape(canonical_url(branch)),
                         'branch': html_escape(branch.displayname)})
            raise LaunchpadValidationError(structured(message))


BRANCH_NAME_VALIDATION_ERROR_MESSAGE = _(
    "Branch names must start with a number or letter.  The characters +, -, "
    "_, . and @ are also allowed after the first character.")


# This is a copy of the pattern in database/schema/trusted.sql.  Don't
# change this without changing that.
valid_branch_name_pattern = re.compile(r"^(?i)[a-z0-9][a-z0-9+\.\-@_]*\Z")


def valid_branch_name(name):
    """Return True if the name is valid as a branch name, otherwise False.

    The rules for what is a valid branch name are described in
    BRANCH_NAME_VALIDATION_ERROR_MESSAGE.
    """
    if valid_branch_name_pattern.match(name):
        return True
    return False


def branch_name_validator(name):
    """Return True if the name is valid, or raise a LaunchpadValidationError.
    """
    if not valid_branch_name(name):
        raise LaunchpadValidationError(
            _("Invalid branch name '${name}'. ${message}",
              mapping={'name': name,
                       'message': BRANCH_NAME_VALIDATION_ERROR_MESSAGE}))
    return True


class IBranchBatchNavigator(ITableBatchNavigator):
    """A marker interface for registering the appropriate branch listings."""


class IBranchNavigationMenu(Interface):
    """A marker interface to indicate the need to show the branch menu."""


class IBranchPublic(Interface):
    """Public attributes for a branch."""

    date_last_modified = exported(
        Datetime(
            title=_('Date Last Modified'),
            required=True,
            readonly=False))
    # Defines whether *this* branch is private. A branch may have
    # explicitly private set false but still be considered private because it
    # is stacked on a private branch. This attribute is read-only. The value
    # is guarded by setPrivate().
    explicitly_private = exported(
        Bool(
            title=_("Keep branch confidential"), required=False,
            readonly=True, default=False,
            description=_(
                "Make this branch visible only to its subscribers.")))
    information_type = exported(
        Choice(
            title=_('Information Type'), vocabulary=InformationType,
            required=True, readonly=True, default=InformationType.PUBLIC,
            description=_(
                'The type of information contained in this branch.')))


class IBranchAnyone(Interface):
    """Attributes of IBranch that can be changed by launchpad.AnyPerson."""

    whiteboard = exported(
        Whiteboard(
            title=_('Whiteboard'), required=False,
            description=_('Notes on the current status of the branch.')))


class IBranchView(IHasOwner, IHasBranchTarget, IHasMergeProposals,
                  IHasRecipes):
    """IBranch attributes that require launchpad.View permission."""

    id = Int(title=_('ID'), readonly=True, required=True)

    @operation_parameters(
        scheme=TextLine(title=_("URL scheme"), default=u'http'))
    @export_read_operation()
    @operation_for_version('beta')
    def composePublicURL(scheme='http'):
        """Return a public URL for the branch using the given protocol.

        :param scheme: a protocol name accepted by the public
            code-hosting API.  (As a legacy issue, 'sftp' is also
            accepted).
        """

    # People attributes
    registrant = exported(
        PublicPersonChoice(
            title=_("The user that registered the branch."),
            required=True, readonly=True,
            vocabulary='ValidPersonOrTeam'))

    owner = exported(
        PersonChoice(
            title=_('Owner'),
            required=True, readonly=True,
            vocabulary='AllUserTeamsParticipationPlusSelf',
            description=_("Either yourself or an exclusive team you are a "
                          "member of. This controls who can modify the "
                          "branch.")))

    # Distroseries and sourcepackagename are exported together as
    # the sourcepackage.
    distroseries = Choice(
        title=_("Distribution Series"), required=False,
        vocabulary='DistroSeries',
        description=_(
            "The distribution series that this branch belongs to. Branches "
            "do not have to belong to a distribution series, they can also "
            "belong to a project or be junk branches."))

    sourcepackagename = Choice(
        title=_("Source Package Name"), required=True,
        vocabulary='SourcePackageName',
        description=_(
            "The source package that this is a branch of. Source package "
            "branches always belong to a distribution series."))

    distribution = Attribute(
        "The IDistribution that this branch belongs to. None if not a "
        "package branch.")

    # Really an ISourcePackage.
    sourcepackage = exported(
        Reference(
            title=_("The ISourcePackage that this branch belongs to. "
                    "None if not a package branch."),
            schema=Interface, required=False, readonly=True))

    namespace = Attribute(
        "The namespace of this branch, as an `IBranchNamespace`.")

    # Product attributes
    # ReferenceChoice is Interface rather than IProduct as IProduct imports
    # IBranch and we'd get import errors.  IPerson does a similar trick.
    # The schema is set properly to `IProduct` in _schema_circular_imports.
    product = exported(
        ReferenceChoice(
            title=_('Project'),
            required=False, readonly=True,
            vocabulary='Product',
            schema=Interface,
            description=_("The project this branch belongs to.")),
        exported_as='project')

    # Display attributes
    unique_name = exported(
        Text(title=_('Unique name'), readonly=True,
             description=_("Unique name of the branch, including the "
                           "owner and project names.")))

    displayname = exported(
        Text(title=_('Display name'), readonly=True,
             description=_(
                "The branch unique_name.")),
        exported_as='display_name')

    code_reviewer = Attribute(
        "The reviewer if set, otherwise the owner of the branch.")

    @operation_parameters(
        reviewer=Reference(
            title=_("A person for which the reviewer status is in question."),
            schema=IPerson))
    @export_read_operation()
    @operation_for_version('beta')
    def isPersonTrustedReviewer(reviewer):
        """Return true if the `reviewer` is a trusted reviewer.

        The reviewer is trusted if they are either own the branch, or are in
        the team that owns the branch, or they are in the review team for the
        branch.
        """

    last_mirrored = exported(
        Datetime(
            title=_("Last time this branch was successfully mirrored."),
            required=False, readonly=True))
    last_mirrored_id = Text(
        title=_("Last mirrored revision ID"), required=False, readonly=True,
        description=_("The head revision ID of the branch when last "
                      "successfully mirrored."))
    last_mirror_attempt = exported(
        Datetime(
            title=_("Last time a mirror of this branch was attempted."),
            required=False, readonly=True))

    mirror_failures = Attribute(
        "Number of failed mirror attempts since the last successful mirror.")

    next_mirror_time = Datetime(
        title=_("If this value is more recent than the last mirror attempt, "
                "then the branch will be mirrored on the next mirror run."),
        required=False)

    # Scanning attributes
    last_scanned = exported(
        Datetime(
            title=_("Last time this branch was successfully scanned."),
            required=False, readonly=True))
    last_scanned_id = exported(
        TextLine(
            title=_("Last scanned revision ID"),
            required=False, readonly=True,
            description=_("The head revision ID of the branch when last "
                          "successfully scanned.")))

    revision_count = exported(
        Int(
            title=_("Revision count"), readonly=True,
            description=_("The revision number of the tip of the branch.")))

    stacked_on = Attribute('Stacked-on branch')

    # Bug attributes
    bug_branches = CollectionField(
            title=_("The bug-branch link objects that link this branch "
                    "to bugs."),
            readonly=True,
            value_type=Reference(schema=Interface))  # Really IBugBranch

    linked_bugs = exported(
        CollectionField(
            title=_("The bugs linked to this branch."),
        readonly=True,
        value_type=Reference(schema=Interface)))  # Really IBug

    def getLinkedBugTasks(user, status_filter):
        """Return a result set for the tasks that are relevant to this branch.

        When multiple tasks are on a bug, if one of the tasks is for the
        branch.target, then only that task is returned. Otherwise the default
        bug task is returned.

        :param user: The user doing the search.
        :param status_filter: Passed onto the bug search as a constraint.
        """

    @call_with(registrant=REQUEST_USER)
    @operation_parameters(
        bug=Reference(schema=Interface))  # Really IBug
    @export_write_operation()
    @operation_for_version('beta')
    def linkBug(bug, registrant):
        """Link a bug to this branch.

        :param bug: IBug to link.
        :param registrant: IPerson linking the bug.
        """

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        bug=Reference(schema=Interface))  # Really IBug
    @export_write_operation()
    @operation_for_version('beta')
    def unlinkBug(bug, user):
        """Unlink a bug to this branch.

        :param bug: IBug to unlink.
        :param user: IPerson unlinking the bug.
        """

    # Specification attributes
    spec_links = exported(
        CollectionField(
            title=_("Specification linked to this branch."),
            readonly=True,
            value_type=Reference(Interface)),  # Really ISpecificationBranch
        as_of="beta")

    def getSpecificationLinks(user):
        """Fetch the `ISpecificationBranch`'s that the user can view."""

    @call_with(registrant=REQUEST_USER)
    @operation_parameters(
        spec=Reference(schema=Interface))  # Really ISpecification
    @export_write_operation()
    @operation_for_version('beta')
    def linkSpecification(spec, registrant):
        """Link an ISpecification to a branch.

        :param spec: ISpecification to link.
        :param registrant: IPerson unlinking the spec.
        """

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        spec=Reference(schema=Interface))  # Really ISpecification
    @export_write_operation()
    @operation_for_version('beta')
    def unlinkSpecification(spec, user):
        """Unlink an ISpecification to a branch.

        :param spec: ISpecification to unlink.
        :param user: IPerson unlinking the spec.
        """

    # Joins
    revision_history = Attribute(
        """The sequence of revisions for the mainline of this branch.

        They are ordered with the most recent revision first, and the list
        only contains those in the "leftmost tree", or in other words
        the revisions that match the revision history from bzrlib for this
        branch.

        The revisions are listed as tuples of (`BranchRevision`, `Revision`).
        """)
    subscriptions = exported(
        CollectionField(
            title=_("BranchSubscriptions associated to this branch."),
            readonly=True,
            value_type=Reference(Interface)))  # Really IBranchSubscription

    subscribers = exported(
        CollectionField(
            title=_("Persons subscribed to this branch."),
            readonly=True,
            value_type=Reference(IPerson)))

    date_created = exported(
        Datetime(
            title=_('Date Created'),
            required=True,
            readonly=True))

    pending_writes = Attribute(
        "Whether there is new Bazaar data for this branch.")

    def latest_revisions(quantity=10):
        """A specific number of the latest revisions in that branch."""

    # These attributes actually have a value_type of IBranchMergeProposal,
    # but uses Interface to prevent circular imports, and the value_type is
    # set near IBranchMergeProposal.
    landing_targets = exported(
        CollectionField(
            title=_('Landing Targets'),
            description=_(
                'A collection of the merge proposals where this branch is '
                'the source branch.'),
            readonly=True,
            value_type=Reference(Interface)))
    landing_candidates = exported(
        CollectionField(
            title=_('Landing Candidates'),
            description=_(
                'A collection of the merge proposals where this branch is '
                'the target branch.'),
            readonly=True,
            value_type=Reference(Interface)))
    dependent_branches = exported(
        CollectionField(
            title=_('Dependent Branches'),
            description=_(
                'A collection of the merge proposals that are dependent '
                'on this branch.'),
            readonly=True,
            value_type=Reference(Interface)))

    def isBranchMergeable(other_branch):
        """Is the other branch mergeable into this branch (or vice versa)."""

    @export_operation_as('createMergeProposal')
    @operation_parameters(
        target_branch=Reference(schema=Interface),
        prerequisite_branch=Reference(schema=Interface),
        needs_review=Bool(title=_('Needs review'),
            description=_('If True the proposal needs review.'
            'Otherwise, it will be work in progress.')),
        initial_comment=Text(
            title=_('Initial comment'),
            description=_("Registrant's initial description of proposal.")),
        commit_message=Text(
            title=_('Commit message'),
            description=_('Message to use when committing this merge.')),
        reviewers=List(value_type=Reference(schema=IPerson)),
        review_types=List(value_type=TextLine()))
    # target_branch and prerequisite_branch are actually IBranch, patched in
    # _schema_circular_imports.
    @call_with(registrant=REQUEST_USER)
    # IBranchMergeProposal supplied as Interface to avoid circular imports.
    @export_factory_operation(Interface, [])
    @operation_for_version('beta')
    def _createMergeProposal(
        registrant, target_branch, prerequisite_branch=None,
        needs_review=True, initial_comment=None, commit_message=None,
        reviewers=None, review_types=None):
        """Create a new BranchMergeProposal with this branch as the source.

        Both the target_branch and the prerequisite_branch, if it is there,
        must be branches with the same target as the source branch.

        Personal branches (a.k.a. junk branches) cannot specify landing
        targets.
        """

    def addLandingTarget(registrant, target_branch, prerequisite_branch=None,
                         date_created=None, needs_review=False,
                         description=None, review_requests=None,
                         commit_message=None):
        """Create a new BranchMergeProposal with this branch as the source.

        Both the target_branch and the prerequisite_branch, if it is there,
        must be branches with the same target as the source branch.

        Personal branches (a.k.a. junk branches) cannot specify landing
        targets.

        :param registrant: The person who is adding the landing target.
        :param target_branch: Must be another branch, and different to self.
        :param prerequisite_branch: Optional but if it is not None, it must be
            another branch.
        :param date_created: Used to specify the date_created value of the
            merge request.
        :param needs_review: Used to specify the proposal is ready for
            review right now.
        :param description: A description of the bugs fixed, features added,
            or refactorings.
        :param review_requests: An optional list of (`Person`, review_type).
        """

    @operation_parameters(
        status=List(
            title=_("A list of merge proposal statuses to filter by."),
            value_type=Choice(vocabulary=BranchMergeProposalStatus)),
        merged_revnos=List(Int(
            title=_('The target-branch revno of the merge.'))))
    @call_with(visible_by_user=REQUEST_USER)
    # Really IBranchMergeProposal
    @operation_returns_collection_of(Interface)
    @export_read_operation()
    @operation_for_version('beta')
    def getMergeProposals(status=None, visible_by_user=None,
                          merged_revnos=None, eager_load=False):
        """Return matching BranchMergeProposals."""

    def scheduleDiffUpdates():
        """Create UpdatePreviewDiffJobs for this branch's targets."""

    def getStackedBranches():
        """The branches that are stacked on this one."""

    def getStackedOnBranches():
        """The branches on which this one is stacked."""

    def getMainlineBranchRevisions(start_date, end_date=None,
                                   oldest_first=False):
        """Return the matching mainline branch revision objects.

        :param start_date: Return revisions that were committed after the
            start_date.
        :param end_date: Return revisions that were committed before the
            end_date
        :param oldest_first: Defines the ordering of the result set.
        :returns: A resultset of tuples for (BranchRevision, Revision)
        """

    def getRevisionsSince(timestamp):
        """Revisions in the history that are more recent than timestamp."""

    code_is_browseable = Attribute(
        "Is the code in this branch accessable through codebrowse?")

    def codebrowse_url(*extras):
        """Construct a URL for this branch in codebrowse.

        :param extras: Zero or more path segments that will be joined onto the
            end of the URL (with `bzrlib.urlutils.join`).
        """

    browse_source_url = Attribute(
        "The URL of the source browser for this branch.")

    # Really ICodeImport, but that would cause a circular import
    code_import = exported(
        Reference(
            title=_("The associated CodeImport, if any."), schema=Interface))

    bzr_identity = exported(
        Text(
            title=_('Bazaar Identity'),
            readonly=True,
            description=_(
                'The bzr branch path as accessed by Launchpad. If the '
                'branch is associated with a product as the primary '
                'development focus, then the result should be lp:product.  '
                'If the branch is related to a series, then '
                'lp:product/series.  Otherwise the result is '
                'lp:~user/product/branch-name.')))

    def addToLaunchBag(launchbag):
        """Add information about this branch to `launchbag'.

        Use this when traversing to this branch in the web UI.

        In particular, add information about the branch's target to the
        launchbag. If the branch has a product, add that; if it has a source
        package, add lots of information about that.

        :param launchbag: `ILaunchBag`.
        """

    @export_read_operation()
    @operation_for_version('beta')
    def canBeDeleted():
        """Can this branch be deleted in its current state.

        A branch is considered deletable if it has no revisions, is not
        linked to any bugs, specs, productseries, or code imports, and
        has no subscribers.
        """

    def deletionRequirements():
        """Determine what is required to delete this branch.

        :return: a dict of {object: (operation, reason)}, where object is the
            object that must be deleted or altered, operation is either
            "delete" or "alter", and reason is a string explaining why the
            object needs to be touched.
        """

    def associatedProductSeries():
        """Return the product series that this branch is associated with.

        A branch may be associated with a product series is either a
        branch.  Also a branch can be associated with more than one product
        series as a branch.
        """

    def getProductSeriesPushingTranslations():
        """Return sequence of product series pushing translations here.

        These are any `ProductSeries` that have this branch as their
        translations_branch.  It should normally be at most one, but
        there's nothing stopping people from combining translations
        branches.
        """

    def associatedSuiteSourcePackages():
        """Return the suite source packages that this branch is linked to.

        :return: A list of suite source packages ordered by pocket.
        """

    def branchLinks():
        """Return a sorted list of ICanHasLinkedBranch objects.

        There is one result for each related linked object that the branch is
        linked to.  For example in the case where a branch is linked to the
        development series of a project, the link objects for both the project
        and the development series are returned.

        The sorting uses the defined order of the linked objects where the
        more important links are sorted first.
        """

    def branchIdentities():
        """A list of aliases for a branch.

        Returns a list of tuples of bzr identity and context object.  There is
        at least one alias for any branch, and that is the branch itself.  For
        linked branches, the context object is the appropriate linked object.

        Where a branch is linked to a product series or a suite source
        package, the branch is available through a number of different urls.
        These urls are the aliases for the branch.

        For example, a branch linked to the development focus of the 'fooix'
        project is accessible using:
          lp:fooix - the linked object is the product fooix
          lp:fooix/trunk - the linked object is the trunk series of fooix
          lp:~owner/fooix/name - the unique name of the branch where the
              linked object is the branch itself.
        """

    # subscription-related methods
    def userCanBeSubscribed(person):
        """Return if the `IPerson` can be subscribed to the branch."""

    @operation_parameters(
        person=Reference(
            title=_("The person to subscribe."),
            schema=IPerson),
        notification_level=Choice(
            title=_("The level of notification to subscribe to."),
            vocabulary=BranchSubscriptionNotificationLevel),
        max_diff_lines=Choice(
            title=_("The max number of lines for diff email."),
            vocabulary=BranchSubscriptionDiffSize),
        code_review_level=Choice(
            title=_("The level of code review notification emails."),
            vocabulary=CodeReviewNotificationLevel))
    @operation_returns_entry(Interface)  # Really IBranchSubscription
    @call_with(subscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('beta')
    def subscribe(person, notification_level, max_diff_lines,
                  code_review_level, subscribed_by,
                  check_stacked_visibility=True):
        """Subscribe this person to the branch.

        :param person: The `Person` to subscribe.
        :param notification_level: The kinds of branch changes that cause
            notification.
        :param max_diff_lines: The maximum number of lines of diff that may
            appear in a notification.
        :param code_review_level: The kinds of code review activity that cause
            notification.
        :param subscribed_by: The person who is subscribing the subscriber.
            Most often the subscriber themselves.
        :return: new or existing BranchSubscription."""

    @operation_parameters(
        person=Reference(
            title=_("The person to unsubscribe"),
            schema=IPerson))
    @operation_returns_entry(Interface)  # Really IBranchSubscription
    @export_read_operation()
    @operation_for_version('beta')
    def getSubscription(person):
        """Return the BranchSubscription for this person."""

    def hasSubscription(person):
        """Is this person subscribed to the branch?"""

    @operation_parameters(
        person=Reference(
            title=_("The person to unsubscribe"),
            schema=IPerson))
    @call_with(unsubscribed_by=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('beta')
    def unsubscribe(person, unsubscribed_by):
        """Remove the person's subscription to this branch.

        :param person: The person or team to unsubscribe from the branch.
        :param unsubscribed_by: The person doing the unsubscribing.
        """

    def getSubscriptionsByLevel(notification_levels):
        """Return the subscriptions that are at the given notification levels.

        :param notification_levels: An iterable of
            `BranchSubscriptionNotificationLevel`s
        :return: An SQLObject query result.
        """

    def getBranchRevision(sequence=None, revision=None, revision_id=None):
        """Get the associated `BranchRevision`.

        One and only one parameter is to be not None.

        :param sequence: The revno of the revision in the mainline history.
        :param revision: A `Revision` object.
        :param revision_id: A revision id string.
        :return: A `BranchRevision` or None.
        """

    def createBranchRevision(sequence, revision):
        """Create a new `BranchRevision` for this branch."""

    def removeBranchRevisions(revision_ids):
        """Remove the specified revision_ids from this Branch's revisions.

        :param revision_ids: Either a single revision_id or an iterable.
        """

    def createBranchRevisionFromIDs(revision_id_sequence_pairs):
        """Create a batch of BranchRevision objects.

        :param revision_id_sequence_pairs: A sequence of (revision_id,
            sequence) pairs.  The revision_ids are assumed to have been
            inserted already; no checking of this is done.
        """

    def getTipRevision():
        """Return the `Revision` associated with the `last_scanned_id`.

        Will return None if last_scanned_id is None, or if the id
        is not found (as in a ghost revision).
        """

    def updateScannedDetails(db_revision, revision_count):
        """Updates attributes associated with the scanning of the branch.

        A single entry point that is called solely from the branch scanner
        script.

        :param revision: The `Revision` that is the tip, or None if empty.
        :param revision_count: The number of revisions in the history
                               (main line revisions).
        """

    def getNotificationRecipients():
        """Return a complete INotificationRecipientSet instance.

        The INotificationRecipientSet instance contains the subscribers
        and their subscriptions.
        """

    def getScannerData():
        """Retrieve the full ancestry of a branch for the branch scanner.

        The branch scanner script is the only place where we need to retrieve
        all the BranchRevision rows for a branch. Since the ancestry of some
        branches is into the tens of thousands we don't want to materialise
        BranchRevision instances for each of these.

        :return: tuple of three items.
            1. Ancestry set of bzr revision-ids.
            2. History list of bzr revision-ids. Similar to the result of
               bzrlib.Branch.revision_history().
            3. Dictionnary mapping bzr bzr revision-ids to the database ids of
               the corresponding BranchRevision rows for this branch.
        """

    def getInternalBzrUrl():
        """Get the internal URL for this branch.

        It's generally better to use `getBzrBranch` to open the branch
        directly, as that method is safe against the branch unexpectedly being
        a branch reference or stacked on something mischievous.
        """

    def getBzrBranch():
        """Return the BzrBranch for this database Branch.

        You can only call this if a server returned by `get_ro_server` or
        `get_rw_server` is running.

        :raise lp.codehosting.safe_open.BadUrl: If the branch is stacked
            on or a reference to an unacceptable URL.
        """

    def getPullURL():
        """Return the URL used to pull the branch into the mirror area."""

    @export_write_operation()
    @operation_for_version('beta')
    def requestMirror():
        """Request that this branch be mirrored on the next run of the branch
        puller.
        """

    def startMirroring():
        """Signal that this branch is being mirrored."""

    def mirrorFailed(reason):
        """Signal that a mirror attempt failed.

        :param reason: An error message that will be displayed on the branch
            detail page.
        """

    def commitsForDays(since):
        """Get a list of commit counts for days since `since`.

        This method returns all commits for the branch, so this includes
        revisions brought in through merges.

        :return: A list of tuples like (date, count).
        """

    def checkUpgrade():
        """Check whether an upgrade should be performed, and raise if not.

        :raises: a `CannotUpgradeBranch`, or a subclass.
        """

    needs_upgrading = Attribute("Whether the branch needs to be upgraded.")
    upgrade_pending = Attribute(
        "Whether a branch has had an upgrade requested.")

    def visibleByUser(user):
        """Can the specified user see this branch?"""

    def getAllowedInformationTypes(who):
        """Get a list of acceptable `InformationType`s for this branch.

        If the user is a Launchpad admin, any type is acceptable. Otherwise
        the `IBranchNamespace` is consulted.
        """


class IBranchModerateAttributes(Interface):
    """IBranch attributes that can be edited by more than one community."""

    name = exported(
        TextLine(
            title=_('Name'), required=True, constraint=branch_name_validator,
            description=_(
                "Keep very short, unique, and descriptive, because it will "
                "be used in URLs.  "
                "Examples: main, devel, release-1.0, gnome-vfs.")))

    reviewer = exported(
        PublicPersonChoice(
            title=_('Review Team'),
            required=False,
            vocabulary='ValidBranchReviewer',
            description=_("The reviewer of a branch is the person or "
                          "exclusive team that is responsible for reviewing "
                          "proposals and merging into this branch.")))

    description = exported(
        Text(
            title=_('Description'), required=False,
            description=_(
                'A short description of the changes in this branch.')))

    lifecycle_status = exported(
        Choice(
            title=_('Status'), vocabulary=BranchLifecycleStatus,
            default=BranchLifecycleStatus.DEVELOPMENT))


class IBranchModerate(Interface):
    """IBranch methods that can be edited by more than one community."""

    @operation_parameters(
        information_type=copy_field(IBranchPublic['information_type']),
        )
    @call_with(who=REQUEST_USER, verify_policy=True)
    @export_write_operation()
    @operation_for_version("devel")
    def transitionToInformationType(information_type, who,
                                    verify_policy=True):
        """Set the information type for this branch.

        :param information_type: The `InformationType` to transition to.
        :param who: The `IPerson` who is making the change.
        :param verify_policy: Check if the new information type complies
            with the `IBranchNamespacePolicy`.
        """


class IBranchEditableAttributes(Interface):
    """IBranch attributes that can be edited.

    These attributes need launchpad.View to see, and launchpad.Edit to change.
    """

    url = exported(
        BranchURIField(
            title=_('Branch URL'), required=False,
            allowed_schemes=['http', 'https', 'ftp', 'sftp', 'bzr+ssh'],
            allow_userinfo=False,
            allow_query=False,
            allow_fragment=False,
            trailing_slash=False,
            description=_(
                "The external location where the Bazaar "
                "branch is hosted. It is None when the branch is "
                "hosted by Launchpad.")))

    mirror_status_message = exported(
        Text(
            title=_('The last message we got when mirroring this branch.'),
            required=False, readonly=True))

    branch_type = exported(
        Choice(
            title=_("Branch Type"), required=True, readonly=True,
            vocabulary=BranchType))

    branch_format = exported(
        Choice(
            title=_("Branch Format"),
            required=False, readonly=True,
            vocabulary=BranchFormat))

    repository_format = exported(
        Choice(
            title=_("Repository Format"),
            required=False, readonly=True,
            vocabulary=RepositoryFormat))

    control_format = exported(
        Choice(
            title=_("Control Directory"),
            required=False, readonly=True,
            vocabulary=ControlFormat))


class IBranchEdit(Interface):
    """IBranch attributes that require launchpad.Edit permission."""

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        new_owner=Reference(
            title=_("The new owner of the branch."),
            schema=IPerson))
    @export_write_operation()
    @operation_for_version('beta')
    def setOwner(new_owner, user):
        """Set the owner of the branch to be `new_owner`."""

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        project=Reference(
            title=_("The project the branch belongs to."),
            schema=Interface, required=False),  # Really IProduct
        source_package=Reference(
            title=_("The source package the branch belongs to."),
            schema=Interface, required=False))  # Really ISourcePackage
    @export_write_operation()
    @operation_for_version('beta')
    def setTarget(user, project=None, source_package=None):
        """Set the target of the branch to be `project` or `source_package`.

        Only one of `project` or `source_package` can be set, and if neither
        is set, the branch gets moved into the junk namespace of the branch
        owner.

        :raise: `BranchTargetError` if both project and source_package are
          set, or if either the project or source_package fail to be
          adapted to an IBranchTarget.
        """

    def requestUpgrade(requester):
        """Create an IBranchUpgradeJob to upgrade this branch."""

    def branchChanged(stacked_on_url, last_revision_id, control_format,
                      branch_format, repository_format):
        """Record that a branch has been changed.

        This method records the stacked on branch tip revision id and format
        or the branch and creates a scan job if the tip revision id has
        changed.

        :param stacked_on_url: The unique name of the branch this branch is
            stacked on, or '' if this branch is not stacked.
        :param last_revision_id: The tip revision ID of the branch.
        :param control_format: The entry from ControlFormat for the branch.
        :param branch_format: The entry from BranchFormat for the branch.
        :param repository_format: The entry from RepositoryFormat for the
            branch.
        """

    @export_destructor_operation()
    @operation_for_version('beta')
    def destroySelfBreakReferences():
        """Delete the specified branch.

        BranchRevisions associated with this branch will also be deleted as
        well as any items with mandatory references.
        """

    def destroySelf(break_references=False):
        """Delete the specified branch.

        BranchRevisions associated with this branch will also be deleted.

        :param break_references: If supplied, break any references to this
            branch by deleting items with mandatory references and
            NULLing other references.
        :raise: CannotDeleteBranch if the branch cannot be deleted.
        """


class IMergeQueueable(Interface):
    """An interface for branches that can be queued."""

    merge_queue = exported(
        Reference(
            title=_('Branch Merge Queue'),
            schema=IBranchMergeQueue, required=False, readonly=True,
            description=_(
                "The branch merge queue that manages merges for this "
                "branch.")))

    merge_queue_config = exported(
        TextLine(
            title=_('Name'), required=True, readonly=True,
            description=_(
                "A JSON string of configuration values to send to a "
                "branch merge robot.")))

    @mutator_for(merge_queue)
    @operation_parameters(
        queue=Reference(title=_('Branch Merge Queue'),
              schema=IBranchMergeQueue))
    @export_write_operation()
    @operation_for_version('beta')
    def addToQueue(queue):
        """Add this branch to a specified queue.

        A branch's merges can be managed by a queue.

        :param queue: The branch merge queue that will manage the branch.
        """

    @mutator_for(merge_queue_config)
    @operation_parameters(
        config=TextLine(title=_("A JSON string of config values.")))
    @export_write_operation()
    @operation_for_version('beta')
    def setMergeQueueConfig(config):
        """Set the merge_queue_config property.

        A branch can store a JSON string of configuration data for a merge
        robot to retrieve.

        :param config: A JSON string of data.
        """


class IBranch(IBranchPublic, IBranchView, IBranchEdit,
              IBranchEditableAttributes, IBranchModerate,
              IBranchModerateAttributes, IBranchAnyone, IMergeQueueable):
    """A Bazaar branch."""

    # Mark branches as exported entries for the Launchpad API.
    export_as_webservice_entry(plural_name='branches')

    # This is redefined from IPrivacy.private and is read only. This attribute
    # is true if this branch is explicitly private or any of its stacked on
    # branches are private.
    private = exported(
        Bool(
            title=_("Branch is confidential"), required=False,
            readonly=True, default=False,
            description=_(
                "This branch is visible only to its subscribers.")))

    @mutator_for(IBranchPublic['explicitly_private'])
    @call_with(user=REQUEST_USER)
    @operation_parameters(
        private=Bool(title=_("Keep branch confidential")))
    @export_write_operation()
    @operation_for_version('beta')
    def setPrivate(private, user):
        """Set the branch privacy for this branch."""


class IBranchSet(Interface):
    """Interface representing the set of branches."""

    export_as_webservice_collection(IBranch)

    def getRecentlyChangedBranches(
        branch_count=None,
        lifecycle_statuses=DEFAULT_BRANCH_STATUS_IN_LISTING,
        visible_by_user=None):
        """Return a result set of branches that have been recently updated.

        Only HOSTED and MIRRORED branches are returned in the result set.

        If branch_count is specified, the result set will contain at most
        branch_count items.

        If lifecycle_statuses evaluates to False then branches
        of any lifecycle_status are returned, otherwise only branches
        with a lifecycle_status of one of the lifecycle_statuses
        are returned.

        :param visible_by_user: If a person is not supplied, only public
            branches are returned.  If a person is supplied both public
            branches, and the private branches that the person is entitled to
            see are returned.  Private branches are only visible to the owner
            and subscribers of the branch, and to LP admins.
        :type visible_by_user: `IPerson` or None
        """

    def getRecentlyImportedBranches(
        branch_count=None,
        lifecycle_statuses=DEFAULT_BRANCH_STATUS_IN_LISTING,
        visible_by_user=None):
        """Return a result set of branches that have been recently imported.

        The result set only contains IMPORTED branches.

        If branch_count is specified, the result set will contain at most
        branch_count items.

        If lifecycle_statuses evaluates to False then branches
        of any lifecycle_status are returned, otherwise only branches
        with a lifecycle_status of one of the lifecycle_statuses
        are returned.

        :param visible_by_user: If a person is not supplied, only public
            branches are returned.  If a person is supplied both public
            branches, and the private branches that the person is entitled to
            see are returned.  Private branches are only visible to the owner
            and subscribers of the branch, and to LP admins.
        :type visible_by_user: `IPerson` or None
        """

    def getRecentlyRegisteredBranches(
        branch_count=None,
        lifecycle_statuses=DEFAULT_BRANCH_STATUS_IN_LISTING,
        visible_by_user=None):
        """Return a result set of branches that have been recently registered.

        If branch_count is specified, the result set will contain at most
        branch_count items.

        If lifecycle_statuses evaluates to False then branches
        of any lifecycle_status are returned, otherwise only branches
        with a lifecycle_status of one of the lifecycle_statuses
        are returned.

        :param visible_by_user: If a person is not supplied, only public
            branches are returned.  If a person is supplied both public
            branches, and the private branches that the person is entitled to
            see are returned.  Private branches are only visible to the owner
            and subscribers of the branch, and to LP admins.
        :type visible_by_user: `IPerson` or None
        """

    @operation_parameters(
        unique_name=TextLine(title=_('Branch unique name'), required=True))
    @operation_returns_entry(IBranch)
    @export_read_operation()
    @operation_for_version('beta')
    def getByUniqueName(unique_name):
        """Find a branch by its ~owner/product/name unique name.

        Return None if no match was found.
        """

    @operation_parameters(
        url=TextLine(title=_('Branch URL'), required=True))
    @operation_returns_entry(IBranch)
    @export_read_operation()
    @operation_for_version('beta')
    def getByUrl(url):
        """Find a branch by URL.

        Either from the external specified in Branch.url, from the URL on
        http://bazaar.launchpad.net/ or the lp: URL.

        This is a frontend shim to `IBranchLookup.getByUrl` to allow it to be
        exported over the API. If you want to call this from within the
        Launchpad app, use the `IBranchLookup` version instead.

        Return None if no match was found.
        """

    @operation_parameters(
        urls=List(
            title=u'A list of URLs of branches',
            description=(
                u'These can be URLs external to '
                u'Launchpad, lp: URLs, or http://bazaar.launchpad.net/ URLs, '
                u'or any mix of all these different kinds.'),
            value_type=TextLine(),
            required=True))
    @export_read_operation()
    @operation_for_version('beta')
    def getByUrls(urls):
        """Finds branches by URL.

        Either from the external specified in Branch.url, from the URL on
        http://bazaar.launchpad.net/, or from the lp: URL.

        This is a frontend shim to `IBranchLookup.getByUrls` to allow it to be
        exported over the API. If you want to call this from within the
        Launchpad app, use the `IBranchLookup` version instead.

        :param urls: An iterable of URLs expressed as strings.
        :return: A dictionary mapping URLs to branches. If the URL has no
            associated branch, the URL will map to `None`.
        """

    @collection_default_content()
    def getBranches(limit=50, eager_load=True):
        """Return a collection of branches.

        :param eager_load: If True (the default because this is used in the
            web service and it needs the related objects to create links)
            eager load related objects (products, code imports etc).
        """

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        person=Reference(
            title=_("The person whose branch visibility is being "
                    "checked."),
            schema=IPerson),
        branch_names=List(value_type=Text(),
            title=_('List of branch unique names'), required=True),
    )
    @export_read_operation()
    @operation_for_version("devel")
    def getBranchVisibilityInfo(user, person, branch_names):
        """Return the named branches visible to both user and person.

        Anonymous requesters don't get any information.

        :param user: The user requesting the information. If the user is None
            then we return an empty dict.
        :param person: The person whose branch visibility we wish to check.
        :param branch_names: The unique names of the branches to check.

        Return a dict with the following values:
        person_name: the displayname of the person.
        visible_branches: a list of the unique names of the branches which
        the requester and specified person can both see.

        This API call is provided for use by the client Javascript. It is not
        designed to efficiently scale to handle requests for large numbers of
        branches.
        """

    @operation_returns_collection_of(Interface)
    @call_with(visible_by_user=REQUEST_USER)
    @operation_parameters(merged_revision=TextLine())
    @export_read_operation()
    @operation_for_version("devel")
    def getMergeProposals(merged_revision, visible_by_user=None):
        """Return the merge proposals that resulted in this revision.

        :param merged_revision: The revision_id of the revision that resulted
            from this merge proposal.
        :param visible_by_user: The user to whom the proposals must be
            visible.  If None, only public proposals will be returned.
        """


class IBranchListingQueryOptimiser(Interface):
    """Interface for a helper utility to do efficient queries for branches.

    Branch listings show several pieces of information and need to do batch
    queries to the database to avoid many small queries.

    Instead of having branch related queries scattered over other utility
    objects, this interface and utility object brings them together.
    """

    def getProductSeriesForBranches(branch_ids):
        """Return the ProductSeries associated with the branch_ids.

        :param branch_ids: a list of branch ids.
        :return: a list of `ProductSeries` objects.
        """

    def getOfficialSourcePackageLinksForBranches(branch_ids):
        """The SeriesSourcePackageBranches associated with the branch_ids.

        :param branch_ids: a list of branch ids.
        :return: a list of `SeriesSourcePackageBranch` objects.
        """


class IBranchDelta(Interface):
    """The quantitative changes made to a branch that was edited or altered.
    """

    branch = Attribute("The IBranch, after it's been edited.")
    user = Attribute("The IPerson that did the editing.")

    # fields on the branch itself, we provide just the new changed value
    name = Attribute("Old and new names or None.")
    title = Attribute("Old and new branch titles or None.")
    summary = Attribute("The branch summary or None.")
    url = Attribute("Old and new branch URLs or None.")
    whiteboard = Attribute("The branch whiteboard or None.")
    lifecycle_status = Attribute("Old and new lifecycle status, or None.")
    revision_count = Attribute("Old and new revision counts, or None.")
    last_scanned_id = Attribute("The revision id of the tip revision.")


class IBranchCloud(Interface):
    """A utility to generate data for branch clouds.

    A branch cloud is a tag cloud of products, sized and styled based on the
    branches in those products.
    """

    def getProductsWithInfo(num_products=None):
        """Get products with their recent activity information.

        The counts are for the last 30 days.

        :return: a `ResultSet` of (product, num_commits, num_authors,
            last_revision_date).
        """


class BzrIdentityMixin:
    """This mixin class determines the bazaar identities.

    Used by both the model branch class and the browser branch listing item.
    This allows the browser code to cache the associated links which reduces
    query counts.
    """

    @property
    def bzr_identity(self):
        """See `IBranch`."""
        identity, context = self.branchIdentities()[0]
        return identity

    def branchIdentities(self):
        """See `IBranch`."""
        lp_prefix = config.codehosting.bzr_lp_prefix
        if not self.target.supports_short_identites:
            identities = []
        else:
            identities = [
                (lp_prefix + link.bzr_path, link.context)
                for link in self.branchLinks()]
        identities.append((lp_prefix + self.unique_name, self))
        return identities

    def branchLinks(self):
        """See `IBranch`."""
        links = []
        for suite_sp in self.associatedSuiteSourcePackages():
            links.append(ICanHasLinkedBranch(suite_sp))
            if (suite_sp.distribution.currentseries == suite_sp.distroseries
                and suite_sp.pocket == PackagePublishingPocket.RELEASE):
                links.append(ICanHasLinkedBranch(
                        suite_sp.sourcepackage.distribution_sourcepackage))
        for series in self.associatedProductSeries():
            links.append(ICanHasLinkedBranch(series))
            if series.product.development_focus == series:
                links.append(ICanHasLinkedBranch(series.product))
        return sorted(links)


def user_has_special_branch_access(user, branch=None):
    """Admins and vcs-import members have have special access.

    :param user: A 'Person' or None.
    :param branch: A branch or None when checking collection access.
    """
    if user is None:
        return False
    roles = IPersonRoles(user)
    if roles.in_admin:
        return True
    if branch is None:
        return False
    code_import = branch.code_import
    if code_import is None:
        return False
    return (
        roles.in_vcs_imports
        or (IPersonRoles(branch.owner).in_vcs_imports
            and user.inTeam(code_import.registrant)))


def get_db_branch_info(stacked_on_url, last_revision_id, control_string,
                       branch_string, repository_string):
    """Return a dict of branch info suitable for Branch.branchChanged.

    :param stacked_on_url: The URL the branch is stacked on.
    :param last_revision_id: The branch tip revision_id.
    :param control_string: The control format marker as a string.
    :param branch_string: The branch format marker as a string.
    :param repository_string: The repository format marker as a string.
    """
    info = {}
    info['stacked_on_url'] = stacked_on_url
    info['last_revision_id'] = last_revision_id
    info['control_format'] = ControlFormat.get_enum(control_string)
    info['branch_format'] = BranchFormat.get_enum(branch_string)
    info['repository_format'] = RepositoryFormat.get_enum(repository_string)
    return info
