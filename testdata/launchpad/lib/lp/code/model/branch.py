# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'Branch',
    'BranchSet',
    'get_branch_privacy_filter',
    ]

from datetime import datetime
import operator

from bzrlib import urlutils
from bzrlib.revision import NULL_REVISION
import pytz
import simplejson
from sqlobject import (
    ForeignKey,
    IntCol,
    SQLMultipleJoin,
    SQLRelatedJoin,
    StringCol,
    )
from storm.expr import (
    And,
    Coalesce,
    Count,
    Desc,
    Insert,
    Join,
    NamedFunc,
    Not,
    Or,
    Select,
    SQL,
    )
from storm.locals import (
    AutoReload,
    Int,
    Reference,
    )
from storm.store import Store
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements
from zope.security.interfaces import Unauthorized
from zope.security.proxy import (
    ProxyFactory,
    removeSecurityProxy,
    )

from lp import _
from lp.app.enums import (
    InformationType,
    PRIVATE_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.app.errors import (
    SubscriptionPrivacyViolation,
    UserCannotUnsubscribePerson,
    )
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.launchpad import (
    ILaunchpadCelebrities,
    IPrivacy,
    )
from lp.app.interfaces.services import IService
from lp.blueprints.model.specification import Specification
from lp.blueprints.model.specificationbranch import SpecificationBranch
from lp.blueprints.model.specificationsearch import (
    get_specification_privacy_filter,
    )
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtaskfilter import filter_bugtasks_by_context
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.buildmaster.model.buildfarmjob import BuildFarmJob
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.code.bzr import (
    BranchFormat,
    ControlFormat,
    CURRENT_BRANCH_FORMATS,
    CURRENT_REPOSITORY_FORMATS,
    RepositoryFormat,
    )
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchMergeProposalStatus,
    BranchType,
    )
from lp.code.errors import (
    AlreadyLatestFormat,
    BranchMergeProposalExists,
    BranchTargetError,
    BranchTypeError,
    CannotDeleteBranch,
    CannotUpgradeBranch,
    CannotUpgradeNonHosted,
    InvalidBranchMergeProposal,
    InvalidMergeQueueConfig,
    UpgradePending,
    )
from lp.code.event.branchmergeproposal import (
    BranchMergeProposalNeedsReviewEvent,
    NewBranchMergeProposalEvent,
    )
from lp.code.interfaces.branch import (
    BzrIdentityMixin,
    DEFAULT_BRANCH_STATUS_IN_LISTING,
    IBranch,
    IBranchNavigationMenu,
    IBranchSet,
    user_has_special_branch_access,
    WrongNumberOfReviewTypeArguments,
    )
from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.branchmergeproposal import (
    BRANCH_MERGE_PROPOSAL_FINAL_STATES,
    )
from lp.code.interfaces.branchnamespace import IBranchNamespacePolicy
from lp.code.interfaces.branchpuller import IBranchPuller
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codehosting import (
    BRANCH_ID_ALIAS_PREFIX,
    compose_public_url,
    )
from lp.code.interfaces.seriessourcepackagebranch import (
    IFindOfficialBranchLinks,
    )
from lp.code.mail.branch import send_branch_modified_notifications
from lp.code.model.branchmergeproposal import (
    BranchMergeProposal,
    BranchMergeProposalGetter,
    )
from lp.code.model.branchrevision import BranchRevision
from lp.code.model.branchsubscription import BranchSubscription
from lp.code.model.revision import (
    Revision,
    RevisionAuthor,
    )
from lp.code.model.seriessourcepackagebranch import SeriesSourcePackageBranch
from lp.codehosting.safe_open import safe_open
from lp.registry.enums import PersonVisibility
from lp.registry.errors import CannotChangeInformationType
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.person import (
    validate_person,
    validate_public_person,
    )
from lp.registry.interfaces.sharingjob import (
    IRemoveArtifactSubscriptionsJobSource,
    )
from lp.registry.model.accesspolicy import (
    AccessPolicyGrant,
    reconcile_access_for_artifact,
    )
from lp.registry.model.teammembership import TeamParticipation
from lp.services.config import config
from lp.services.database.bulk import load_related
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IMasterStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.database.stormexpr import (
    Array,
    ArrayAgg,
    ArrayIntersects,
    )
from lp.services.helpers import shortlist
from lp.services.job.interfaces.job import JobStatus
from lp.services.job.model.job import Job
from lp.services.mail.notificationrecipientset import NotificationRecipientSet
from lp.services.propertycache import cachedproperty
from lp.services.webapp import urlappend
from lp.services.webapp.authorization import check_permission


class Branch(SQLBase, BzrIdentityMixin):
    """A sequence of ordered revisions in Bazaar."""

    implements(IBranch, IBranchNavigationMenu, IPrivacy, IInformationType)
    _table = 'Branch'

    branch_type = EnumCol(enum=BranchType, notNull=True)

    name = StringCol(notNull=False)
    url = StringCol(dbName='url')
    description = StringCol(dbName='summary')
    branch_format = EnumCol(enum=BranchFormat)
    repository_format = EnumCol(enum=RepositoryFormat)
    # XXX: Aaron Bentley 2008-06-13
    # Rename the metadir_format in the database, see bug 239746
    control_format = EnumCol(enum=ControlFormat, dbName='metadir_format')
    whiteboard = StringCol(default=None)
    mirror_status_message = StringCol(default=None)
    information_type = EnumCol(
        enum=InformationType, default=InformationType.PUBLIC)
    access_policy = IntCol()

    @property
    def private(self):
        return self.information_type in PRIVATE_INFORMATION_TYPES

    explicitly_private = private

    def _reconcileAccess(self):
        """Reconcile the branch's sharing information.

        Takes the information_type and target and makes the related
        AccessArtifact and AccessPolicyArtifacts match.
        """
        wanted_links = None
        pillars = []
        # For private +junk branches, we calculate the wanted grants.
        if (not self.product and
            not self.sourcepackagename and
            not self.information_type in PUBLIC_INFORMATION_TYPES):
            aasource = getUtility(IAccessArtifactSource)
            [abstract_artifact] = aasource.ensure([self])
            wanted_links = set(
                (abstract_artifact, policy) for policy in
                getUtility(IAccessPolicySource).findByTeam([self.owner]))
        else:
            # We haven't yet quite worked out how distribution privacy
            # works, so only work for products for now.
            if self.product is not None:
                pillars = [self.product]
        reconcile_access_for_artifact(
            self, self.information_type, pillars, wanted_links)

    def setPrivate(self, private, user):
        """See `IBranch`."""
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        return self.transitionToInformationType(information_type, user)

    def getAllowedInformationTypes(self, who):
        """See `IBranch`."""
        if user_has_special_branch_access(who):
            # Until sharing settles down, admins can set any type.
            types = set(PUBLIC_INFORMATION_TYPES + PRIVATE_INFORMATION_TYPES)
        else:
            # Otherwise the permitted types are defined by the namespace.
            policy = IBranchNamespacePolicy(self.namespace)
            types = set(policy.getAllowedInformationTypes(who))
        return types

    def transitionToInformationType(self, information_type, who,
                                    verify_policy=True):
        """See `IBranch`."""
        if self.information_type == information_type:
            return
        if (self.stacked_on
            and self.stacked_on.information_type in PRIVATE_INFORMATION_TYPES
            and information_type in PUBLIC_INFORMATION_TYPES):
            raise CannotChangeInformationType("Must match stacked-on branch.")
        if (verify_policy
            and information_type not in self.getAllowedInformationTypes(who)):
            raise CannotChangeInformationType("Forbidden by project policy.")
        self.information_type = information_type
        self._reconcileAccess()
        if information_type in PRIVATE_INFORMATION_TYPES and self.subscribers:
            # Grant the subscriber access if they can't see the branch.
            service = getUtility(IService, 'sharing')
            blind_subscribers = service.getPeopleWithoutAccess(
                self, self.subscribers)
            if len(blind_subscribers):
                service.ensureAccessGrants(
                    blind_subscribers, who, branches=[self],
                    ignore_permissions=True)
        # As a result of the transition, some subscribers may no longer
        # have access to the branch. We need to run a job to remove any
        # such subscriptions.
        getUtility(IRemoveArtifactSubscriptionsJobSource).create(who, [self])

    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_person, notNull=True)

    def setOwner(self, new_owner, user):
        """See `IBranch`."""
        new_namespace = self.target.getNamespace(new_owner)
        new_namespace.moveBranch(self, user, rename_if_necessary=True)

    reviewer = ForeignKey(
        dbName='reviewer', foreignKey='Person',
        storm_validator=validate_person, default=None)

    product = ForeignKey(dbName='product', foreignKey='Product', default=None)

    distroseries = ForeignKey(
        dbName='distroseries', foreignKey='DistroSeries', default=None)
    sourcepackagename = ForeignKey(
        dbName='sourcepackagename', foreignKey='SourcePackageName',
        default=None)

    lifecycle_status = EnumCol(
        enum=BranchLifecycleStatus, notNull=True,
        default=BranchLifecycleStatus.DEVELOPMENT)

    last_mirrored = UtcDateTimeCol(default=None)
    last_mirrored_id = StringCol(default=None)
    last_mirror_attempt = UtcDateTimeCol(default=None)
    mirror_failures = IntCol(default=0, notNull=True)
    next_mirror_time = UtcDateTimeCol(default=None)

    last_scanned = UtcDateTimeCol(default=None)
    last_scanned_id = StringCol(default=None)
    revision_count = IntCol(default=DEFAULT, notNull=True)
    stacked_on = ForeignKey(
        dbName='stacked_on', foreignKey='Branch', default=None)

    # The unique_name is maintined by a SQL trigger.
    unique_name = StringCol()
    # Denormalised colums used primarily for sorting.
    owner_name = StringCol()
    target_suffix = StringCol()

    def __repr__(self):
        return '<Branch %r (%d)>' % (self.unique_name, self.id)

    @property
    def target(self):
        """See `IBranch`."""
        if self.product is None:
            if self.distroseries is None:
                target = self.owner
            else:
                target = self.sourcepackage
        else:
            target = self.product
        return IBranchTarget(target)

    def setTarget(self, user, project=None, source_package=None):
        """See `IBranch`."""
        if project is not None:
            if source_package is not None:
                raise BranchTargetError(
                    'Cannot specify both a project and a source package.')
            else:
                target = IBranchTarget(project)
                if target is None:
                    raise BranchTargetError(
                        '%r is not a valid project target' % project)
        elif source_package is not None:
            target = IBranchTarget(source_package)
            if target is None:
                raise BranchTargetError(
                    '%r is not a valid source package target' %
                    source_package)
        else:
            target = IBranchTarget(self.owner)
            if (self.information_type in PRIVATE_INFORMATION_TYPES and
                (not self.owner.is_team or
                 self.owner.visibility != PersonVisibility.PRIVATE)):
                raise BranchTargetError(
                    'Only private teams may have personal private branches.')
        namespace = target.getNamespace(self.owner)
        if (self.information_type not in
            namespace.getAllowedInformationTypes(user)):
            raise BranchTargetError(
                '%s branches are not allowed for target %s.' % (
                    self.information_type.title, target.displayname))
        namespace.moveBranch(self, user, rename_if_necessary=True)
        self._reconcileAccess()

    @property
    def namespace(self):
        """See `IBranch`."""
        return self.target.getNamespace(self.owner)

    @property
    def distribution(self):
        """See `IBranch`."""
        if self.distroseries is None:
            return None
        return self.distroseries.distribution

    @property
    def sourcepackage(self):
        """See `IBranch`."""
        # Avoid circular imports.
        from lp.registry.model.sourcepackage import SourcePackage
        if self.distroseries is None:
            return None
        return SourcePackage(self.sourcepackagename, self.distroseries)

    @property
    def revision_history(self):
        result = Store.of(self).find(
            (BranchRevision, Revision),
            BranchRevision.branch_id == self.id,
            Revision.id == BranchRevision.revision_id,
            BranchRevision.sequence != None)
        result = result.order_by(Desc(BranchRevision.sequence))
        return DecoratedResultSet(result, operator.itemgetter(0))

    subscriptions = SQLMultipleJoin(
        'BranchSubscription', joinColumn='branch', orderBy='id')
    subscribers = SQLRelatedJoin(
        'Person', joinColumn='branch', otherColumn='person',
        intermediateTable='BranchSubscription', orderBy='name')

    bug_branches = SQLMultipleJoin(
        'BugBranch', joinColumn='branch', orderBy='id')

    linked_bugs = SQLRelatedJoin(
        'Bug', joinColumn='branch', otherColumn='bug',
        intermediateTable='BugBranch', orderBy='id')

    def getLinkedBugTasks(self, user, status_filter=None):
        """See `IBranch`."""
        params = BugTaskSearchParams(user=user, linked_branches=self.id,
            status=status_filter)
        tasks = shortlist(getUtility(IBugTaskSet).search(params), 1000)
        # Post process to discard irrelevant tasks: we only return one task
        # per bug, and cannot easily express this in sql (yet).
        return filter_bugtasks_by_context(self.target.context, tasks)

    def linkBug(self, bug, registrant):
        """See `IBranch`."""
        return bug.linkBranch(self, registrant)

    def unlinkBug(self, bug, user):
        """See `IBranch`."""
        return bug.unlinkBranch(self, user)

    spec_links = SQLMultipleJoin(
        'SpecificationBranch', joinColumn='branch', orderBy='id')

    def getSpecificationLinks(self, user):
        """See `IBranch`."""
        tables = [
            SpecificationBranch,
            Join(
                Specification,
                SpecificationBranch.specificationID == Specification.id)]
        return Store.of(self).using(*tables).find(
            SpecificationBranch,
            SpecificationBranch.branchID == self.id,
            *get_specification_privacy_filter(user))

    def linkSpecification(self, spec, registrant):
        """See `IBranch`."""
        return spec.linkBranch(self, registrant)

    def unlinkSpecification(self, spec, user):
        """See `IBranch`."""
        return spec.unlinkBranch(self, user)

    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)
    date_last_modified = UtcDateTimeCol(notNull=True, default=DEFAULT)

    landing_targets = SQLMultipleJoin(
        'BranchMergeProposal', joinColumn='source_branch')

    @property
    def active_landing_targets(self):
        """Merge proposals not in final states where this branch is source."""
        return Store.of(self).find(
            BranchMergeProposal, BranchMergeProposal.source_branch == self,
            Not(BranchMergeProposal.queue_status.is_in(
                BRANCH_MERGE_PROPOSAL_FINAL_STATES)))

    @property
    def landing_candidates(self):
        """See `IBranch`."""
        return BranchMergeProposal.select("""
            BranchMergeProposal.target_branch = %s AND
            BranchMergeProposal.queue_status NOT IN %s
            """ % sqlvalues(self, BRANCH_MERGE_PROPOSAL_FINAL_STATES))

    @property
    def dependent_branches(self):
        """See `IBranch`."""
        return BranchMergeProposal.select("""
            BranchMergeProposal.dependent_branch = %s AND
            BranchMergeProposal.queue_status NOT IN %s
            """ % sqlvalues(self, BRANCH_MERGE_PROPOSAL_FINAL_STATES))

    def getMergeProposals(self, status=None, visible_by_user=None,
                          merged_revnos=None, eager_load=False):
        """See `IBranch`."""
        if not status:
            status = (
                BranchMergeProposalStatus.CODE_APPROVED,
                BranchMergeProposalStatus.NEEDS_REVIEW,
                BranchMergeProposalStatus.WORK_IN_PROGRESS)

        collection = getUtility(IAllBranches).visibleByUser(visible_by_user)
        return collection.getMergeProposals(
            status, target_branch=self, merged_revnos=merged_revnos,
            eager_load=eager_load)

    def isBranchMergeable(self, target_branch):
        """See `IBranch`."""
        # In some imaginary time we may actually check to see if this branch
        # and the target branch have common ancestry.
        return self.target.areBranchesMergeable(target_branch.target)

    def addLandingTarget(self, registrant, target_branch,
                         prerequisite_branch=None, whiteboard=None,
                         date_created=None, needs_review=False,
                         description=None, review_requests=None,
                         commit_message=None):
        """See `IBranch`."""
        if not self.target.supports_merge_proposals:
            raise InvalidBranchMergeProposal(
                '%s branches do not support merge proposals.'
                % self.target.displayname)
        if self == target_branch:
            raise InvalidBranchMergeProposal(
                'Source and target branches must be different.')
        if not target_branch.isBranchMergeable(self):
            raise InvalidBranchMergeProposal(
                '%s is not mergeable into %s' % (
                    self.displayname, target_branch.displayname))
        if prerequisite_branch is not None:
            if not self.isBranchMergeable(prerequisite_branch):
                raise InvalidBranchMergeProposal(
                    '%s is not mergeable into %s' % (
                        prerequisite_branch.displayname, self.displayname))
            if self == prerequisite_branch:
                raise InvalidBranchMergeProposal(
                    'Source and prerequisite branches must be different.')
            if target_branch == prerequisite_branch:
                raise InvalidBranchMergeProposal(
                    'Target and prerequisite branches must be different.')

        target = BranchMergeProposalGetter.activeProposalsForBranches(
            self, target_branch)
        for existing_proposal in target:
            raise BranchMergeProposalExists(existing_proposal)

        if date_created is None:
            date_created = UTC_NOW

        if needs_review:
            queue_status = BranchMergeProposalStatus.NEEDS_REVIEW
            date_review_requested = date_created
        else:
            queue_status = BranchMergeProposalStatus.WORK_IN_PROGRESS
            date_review_requested = None

        if review_requests is None:
            review_requests = []

        # If no reviewer is specified, use the default for the branch.
        if len(review_requests) == 0:
            review_requests.append((target_branch.code_reviewer, None))

        bmp = BranchMergeProposal(
            registrant=registrant, source_branch=self,
            target_branch=target_branch,
            prerequisite_branch=prerequisite_branch, whiteboard=whiteboard,
            date_created=date_created,
            date_review_requested=date_review_requested,
            queue_status=queue_status, commit_message=commit_message,
            description=description)

        for reviewer, review_type in review_requests:
            bmp.nominateReviewer(
                reviewer, registrant, review_type, _notify_listeners=False)

        notify(NewBranchMergeProposalEvent(bmp))
        if needs_review:
            notify(BranchMergeProposalNeedsReviewEvent(bmp))

        return bmp

    def _createMergeProposal(
        self, registrant, target_branch, prerequisite_branch=None,
        needs_review=True, initial_comment=None, commit_message=None,
        reviewers=None, review_types=None):
        """See `IBranch`."""
        if reviewers is None:
            reviewers = []
        if review_types is None:
            review_types = []
        if len(reviewers) != len(review_types):
            raise WrongNumberOfReviewTypeArguments(
                'reviewers and review_types must be equal length.')
        review_requests = zip(reviewers, review_types)
        return self.addLandingTarget(
            registrant, target_branch, prerequisite_branch,
            needs_review=needs_review, description=initial_comment,
            commit_message=commit_message, review_requests=review_requests)

    def scheduleDiffUpdates(self):
        """See `IBranch`."""
        from lp.code.model.branchmergeproposaljob import (
                GenerateIncrementalDiffJob,
                UpdatePreviewDiffJob,
            )
        jobs = []
        for merge_proposal in self.active_landing_targets:
            if merge_proposal.target_branch.last_scanned_id is None:
                continue
            jobs.append(UpdatePreviewDiffJob.create(merge_proposal))
            for old, new in merge_proposal.getMissingIncrementalDiffs():
                GenerateIncrementalDiffJob.create(
                    merge_proposal, old.revision_id, new.revision_id)
        return jobs

    def addToLaunchBag(self, launchbag):
        """See `IBranch`."""
        launchbag.add(self.product)
        if self.distroseries is not None:
            launchbag.add(self.distroseries)
            launchbag.add(self.distribution)
            launchbag.add(self.sourcepackage)

    def getStackedBranches(self):
        """See `IBranch`."""
        return Store.of(self).find(Branch, Branch.stacked_on == self)

    def getStackedOnBranches(self):
        """See `IBranch`."""
        # We need to ensure we avoid being caught by accidental circular
        # dependencies.
        stacked_on_branches = []
        branch = self
        while (branch.stacked_on and
               branch.stacked_on not in stacked_on_branches):
            stacked_on_branches.append(branch.stacked_on)
            branch = branch.stacked_on
        return stacked_on_branches

    @property
    def code_is_browseable(self):
        """See `IBranch`."""
        return (self.revision_count > 0 or self.last_mirrored != None)

    def codebrowse_url(self, *extras):
        """See `IBranch`."""
        if self.private:
            root = config.codehosting.secure_codebrowse_root
        else:
            root = config.codehosting.codebrowse_root
        return urlutils.join(root, self.unique_name, *extras)

    @property
    def browse_source_url(self):
        return self.codebrowse_url('files')

    def composePublicURL(self, scheme='http'):
        """See `IBranch`."""
        # Not all protocols work for private branches.
        public_schemes = ['http']
        assert not (self.private and scheme in public_schemes), (
            "Private branch %s has no public URL." % self.unique_name)
        return compose_public_url(scheme, self.unique_name)

    def getInternalBzrUrl(self):
        """See `IBranch`."""
        return 'lp-internal:///' + self.unique_name

    def getBzrBranch(self):
        """See `IBranch`."""
        return safe_open('lp-internal', self.getInternalBzrUrl())

    @property
    def displayname(self):
        """See `IBranch`."""
        return self.bzr_identity

    @property
    def code_reviewer(self):
        """See `IBranch`."""
        if self.reviewer:
            return self.reviewer
        else:
            return self.owner

    def isPersonTrustedReviewer(self, reviewer):
        """See `IBranch`."""
        if reviewer is None:
            return False
        # We trust Launchpad admins.
        lp_admins = getUtility(ILaunchpadCelebrities).admin
        # Both the branch owner and the review team are checked.
        owner = self.owner
        review_team = self.code_reviewer
        return (
            reviewer.inTeam(owner) or
            reviewer.inTeam(review_team) or
            reviewer.inTeam(lp_admins))

    def latest_revisions(self, quantity=10):
        """See `IBranch`."""
        return self.revision_history.config(limit=quantity)

    def getMainlineBranchRevisions(self, start_date, end_date=None,
                                   oldest_first=False):
        """See `IBranch`."""
        date_clause = Revision.revision_date >= start_date
        if end_date is not None:
            date_clause = And(date_clause, Revision.revision_date <= end_date)
        result = Store.of(self).find(
            (BranchRevision, Revision),
            BranchRevision.branch == self,
            BranchRevision.sequence != None,
            BranchRevision.revision == Revision.id,
            date_clause)
        if oldest_first:
            result = result.order_by(BranchRevision.sequence)
        else:
            result = result.order_by(Desc(BranchRevision.sequence))

        def eager_load(rows):
            revisions = map(operator.itemgetter(1), rows)
            load_related(RevisionAuthor, revisions, ['revision_author_id'])
        return DecoratedResultSet(result, pre_iter_hook=eager_load)

    def getRevisionsSince(self, timestamp):
        """See `IBranch`."""
        result = Store.of(self).find(
            (BranchRevision, Revision),
            Revision.id == BranchRevision.revision_id,
            BranchRevision.branch == self,
            BranchRevision.sequence != None,
            Revision.revision_date > timestamp)
        result = result.order_by(Desc(BranchRevision.sequence))
        # Return BranchRevision but prejoin Revision as well.
        return DecoratedResultSet(result, operator.itemgetter(0))

    def canBeDeleted(self):
        """See `IBranch`."""
        if ((len(self.deletionRequirements()) != 0) or not
            self.getStackedBranches().is_empty()):
            # Can't delete if the branch is associated with anything.
            return False
        else:
            return True

    @cachedproperty
    def code_import(self):
        from lp.code.model.codeimport import CodeImportSet
        return CodeImportSet().getByBranch(self)

    def _deletionRequirements(self):
        """Determine what operations must be performed to delete this branch.

        Two dictionaries are returned, one for items that must be deleted,
        one for items that must be altered.  The item in question is the
        key, and the value is a user-facing string explaining why the item
        is affected.

        As well as the dictionaries, this method returns two list of callables
        that may be called to perform the alterations and deletions needed.
        """
        alteration_operations = []
        deletion_operations = []
        # Merge proposals require their source and target branches to exist.
        for merge_proposal in self.landing_targets:
            deletion_operations.append(
                DeletionCallable(merge_proposal,
                    _('This branch is the source branch of this merge'
                    ' proposal.'), merge_proposal.deleteProposal))
        # Cannot use self.landing_candidates, because it ignores merged
        # merge proposals.
        for merge_proposal in BranchMergeProposal.selectBy(
            target_branch=self):
            deletion_operations.append(
                DeletionCallable(merge_proposal,
                    _('This branch is the target branch of this merge'
                    ' proposal.'), merge_proposal.deleteProposal))
        for merge_proposal in BranchMergeProposal.selectBy(
            prerequisite_branch=self):
            alteration_operations.append(ClearDependentBranch(merge_proposal))

        for bugbranch in self.bug_branches:
            deletion_operations.append(
                DeletionCallable(bugbranch.bug.default_bugtask,
                _('This bug is linked to this branch.'),
                bugbranch.destroySelf))
        for spec_link in self.spec_links:
            deletion_operations.append(
                DeletionCallable(spec_link,
                    _('This blueprint is linked to this branch.'),
                    spec_link.destroySelf))
        for series in self.associatedProductSeries():
            alteration_operations.append(ClearSeriesBranch(series, self))
        for series in self.getProductSeriesPushingTranslations():
            alteration_operations.append(
                ClearSeriesTranslationsBranch(series, self))

        series_set = getUtility(IFindOfficialBranchLinks)
        alteration_operations.extend(
            map(ClearOfficialPackageBranch, series_set.findForBranch(self)))
        deletion_operations.extend(
            DeletionCallable.forSourcePackageRecipe(recipe)
            for recipe in self.recipes)
        return (alteration_operations, deletion_operations)

    def deletionRequirements(self):
        """See `IBranch`."""
        alteration_operations, deletion_operations, = (
            self._deletionRequirements())
        result = dict(
            (operation.affected_object, ('alter', operation.rationale)) for
            operation in alteration_operations)
        # Deletion entries should overwrite alteration entries.
        result.update(
            (operation.affected_object, ('delete', operation.rationale)) for
            operation in deletion_operations)
        return result

    def _breakReferences(self):
        """Break all external references to this branch.

        NULLable references will be NULLed.  References which are not NULLable
        will cause the item holding the reference to be deleted.

        This function is guaranteed to perform the operations predicted by
        deletionRequirements, because it uses the same backing function.
        """
        (alteration_operations,
            deletion_operations) = self._deletionRequirements()
        for operation in alteration_operations:
            operation()
        for operation in deletion_operations:
            operation()
        # Special-case code import, since users don't have lp.Edit on them,
        # since if you can delete a branch you should be able to delete the
        # code import and since deleting the code import object itself isn't
        # actually a very interesting thing to tell the user about.
        if self.code_import is not None:
            DeleteCodeImport(self.code_import)()
        Store.of(self).flush()

    @cachedproperty
    def _associatedProductSeries(self):
        """Helper for eager loading associatedProductSeries."""
        # This is eager loaded by BranchCollection.getBranches.
        # Imported here to avoid circular import.
        from lp.registry.model.productseries import ProductSeries
        return Store.of(self).find(ProductSeries, ProductSeries.branch == self)

    def associatedProductSeries(self):
        """See `IBranch`."""
        return self._associatedProductSeries

    def getProductSeriesPushingTranslations(self):
        """See `IBranch`."""
        # Imported here to avoid circular import.
        from lp.registry.model.productseries import ProductSeries
        return Store.of(self).find(
            ProductSeries,
            ProductSeries.translations_branch == self)

    @cachedproperty
    def _associatedSuiteSourcePackages(self):
        """Helper for associatedSuiteSourcePackages."""
        # This is eager loaded by BranchCollection.getBranches.
        series_set = getUtility(IFindOfficialBranchLinks)
        # Order by the pocket to get the release one first. If changing this
        # be sure to also change BranchCollection.getBranches.
        links = series_set.findForBranch(self).order_by(
            SeriesSourcePackageBranch.pocket)
        return [link.suite_sourcepackage for link in links]

    def associatedSuiteSourcePackages(self):
        """See `IBranch`."""
        return self._associatedSuiteSourcePackages

    def userCanBeSubscribed(self, person):
        return not (person.is_team and self.information_type in
            PRIVATE_INFORMATION_TYPES and person.anyone_can_join())

    # subscriptions
    def subscribe(self, person, notification_level, max_diff_lines,
                  code_review_level, subscribed_by,
                  check_stacked_visibility=True):
        """See `IBranch`.

        Subscribe person to this branch and also to any editable stacked on
        branches they cannot see.
        """
        if not self.userCanBeSubscribed(person):
            raise SubscriptionPrivacyViolation(
                "Open and delegated teams cannot be subscribed to private "
                "branches.")
        # If the person is already subscribed, update the subscription with
        # the specified notification details.
        subscription = self.getSubscription(person)
        if subscription is None:
            subscription = BranchSubscription(
                branch=self, person=person,
                notification_level=notification_level,
                max_diff_lines=max_diff_lines, review_level=code_review_level,
                subscribed_by=subscribed_by)
            Store.of(subscription).flush()
        else:
            subscription.notification_level = notification_level
            subscription.max_diff_lines = max_diff_lines
            subscription.review_level = code_review_level
        # Grant the subscriber access if they can't see the branch.
        service = getUtility(IService, 'sharing')
        ignored, branches, ignored = service.getVisibleArtifacts(
            person, branches=[self], ignore_permissions=True)
        if not branches:
            service.ensureAccessGrants(
                [person], subscribed_by, branches=[self],
                ignore_permissions=True)

        if not check_stacked_visibility:
            return subscription

        # We now grant access to any stacked on branches which are not
        # currently accessible to the person but which the subscribed_by user
        # has edit permissions for.
        service = getUtility(IService, 'sharing')
        ignored, invisible_stacked_branches = service.getInvisibleArtifacts(
            person, branches=self.getStackedOnBranches())
        editable_stacked_on_branches = [
            branch for branch in invisible_stacked_branches
            if check_permission('launchpad.Edit', branch)]
        for invisible_branch in editable_stacked_on_branches:
            invisible_branch.subscribe(
                person, notification_level, max_diff_lines, code_review_level,
                subscribed_by, check_stacked_visibility=False)
        return subscription

    def getSubscription(self, person):
        """See `IBranch`."""
        if person is None:
            return None
        subscription = BranchSubscription.selectOneBy(
            person=person, branch=self)
        return subscription

    def getSubscriptionsByLevel(self, notification_levels):
        """See `IBranch`."""
        # XXX: JonathanLange 2009-05-07 bug=373026: This is only used by real
        # code to determine whether there are any subscribers at the given
        # notification levels. The only code that cares about the actual
        # object is in a test:
        # test_only_nodiff_subscribers_means_no_diff_generated.
        store = Store.of(self)
        return store.find(
            BranchSubscription,
            BranchSubscription.branch == self,
            BranchSubscription.notification_level.is_in(notification_levels))

    def hasSubscription(self, person):
        """See `IBranch`."""
        return self.getSubscription(person) is not None

    def unsubscribe(self, person, unsubscribed_by, ignore_permissions=False):
        """See `IBranch`."""
        subscription = self.getSubscription(person)
        if subscription is None:
            # Silent success seems order of the day (like bugs).
            return
        if (not ignore_permissions
            and not subscription.canBeUnsubscribedByUser(unsubscribed_by)):
            raise UserCannotUnsubscribePerson(
                '%s does not have permission to unsubscribe %s.' % (
                    unsubscribed_by.displayname,
                    person.displayname))
        store = Store.of(subscription)
        store.remove(subscription)
        artifact = getUtility(IAccessArtifactSource).find([self])
        getUtility(IAccessArtifactGrantSource).revokeByArtifact(
            artifact, [person])
        store.flush()

    def getBranchRevision(self, sequence=None, revision=None,
                          revision_id=None):
        """See `IBranch`."""
        params = (sequence, revision, revision_id)
        if len([p for p in params if p is not None]) != 1:
            raise AssertionError(
                "One and only one of sequence, revision, or revision_id "
                "should have a value.")
        if sequence is not None:
            query = BranchRevision.sequence == sequence
        elif revision is not None:
            query = BranchRevision.revision == revision
        else:
            query = And(BranchRevision.revision == Revision.id,
                        Revision.revision_id == revision_id)

        store = Store.of(self)

        return store.find(
            BranchRevision,
            BranchRevision.branch == self,
            query).one()

    def removeBranchRevisions(self, revision_ids):
        """See `IBranch`."""
        if isinstance(revision_ids, basestring):
            revision_ids = [revision_ids]
        IMasterStore(BranchRevision).find(
            BranchRevision,
            BranchRevision.branch == self,
            BranchRevision.revision_id.is_in(
                Select(Revision.id,
                       Revision.revision_id.is_in(revision_ids)))).remove()

    def createBranchRevision(self, sequence, revision):
        """See `IBranch`."""
        branch_revision = BranchRevision(
            branch=self, sequence=sequence, revision=revision)
        # Allocate karma if no karma has been allocated for this revision.
        if not revision.karma_allocated:
            revision.allocateKarma(self)
        return branch_revision

    def createBranchRevisionFromIDs(self, revision_id_sequence_pairs):
        """See `IBranch`."""
        if not revision_id_sequence_pairs:
            return
        store = Store.of(self)
        store.execute(
            """
            CREATE TEMPORARY TABLE RevidSequence
            (revision_id text, sequence integer)
            """)
        # Force to Unicode or we will end up with bad quoting under
        # PostgreSQL 9.1.
        unicode_revid_sequence_pairs = [
            (a and unicode(a) or None, b and unicode(b) or None)
                for a, b in revision_id_sequence_pairs]
        store.execute(Insert(('revision_id', 'sequence'),
            table=['RevidSequence'], values=unicode_revid_sequence_pairs))
        store.execute(
            """
            INSERT INTO BranchRevision (branch, revision, sequence)
            SELECT %s, Revision.id, RevidSequence.sequence
            FROM RevidSequence, Revision
            WHERE Revision.revision_id = RevidSequence.revision_id
            """ % sqlvalues(self))
        store.execute("DROP TABLE RevidSequence")

    def getTipRevision(self):
        """See `IBranch`."""
        tip_revision_id = self.last_scanned_id
        if tip_revision_id is None:
            return None
        return Revision.selectOneBy(revision_id=tip_revision_id)

    def updateScannedDetails(self, db_revision, revision_count):
        """See `IBranch`."""
        # By taking the minimum of the revision date and the date created, we
        # cap the revision date to make sure that we don't use a future date.
        # The date created is set to be the time that the revision was created
        # in the database, so if the revision_date is a future date, then we
        # use the date created instead.
        if db_revision is None:
            revision_id = NULL_REVISION
            revision_date = UTC_NOW
        else:
            revision_id = db_revision.revision_id
            revision_date = min(
                db_revision.revision_date, db_revision.date_created)

        # If the branch has changed through either a different tip revision or
        # revision count, then update.
        if ((revision_id != self.last_scanned_id) or
            (revision_count != self.revision_count)):
            # If the date of the last revision is greated than the date last
            # modified, then bring the date last modified forward to the last
            # revision date (as long as the revision date isn't in the
            # future).
            if db_revision is None or revision_date > self.date_last_modified:
                self.date_last_modified = revision_date
            self.last_scanned = UTC_NOW
            self.last_scanned_id = revision_id
            self.revision_count = revision_count
            if self.lifecycle_status in (BranchLifecycleStatus.MERGED,
                                         BranchLifecycleStatus.ABANDONED):
                self.lifecycle_status = BranchLifecycleStatus.DEVELOPMENT

    def getNotificationRecipients(self):
        """See `IBranch`."""
        recipients = NotificationRecipientSet()
        for subscription in self.subscriptions:
            if subscription.person.is_team:
                rationale = 'Subscriber @%s' % subscription.person.name
            else:
                rationale = 'Subscriber'
            recipients.add(subscription.person, subscription, rationale)
        return recipients

    @property
    def pending_writes(self):
        """See `IBranch`.

        A branch has pending writes if it has just been pushed to, if it has
        been mirrored and not yet scanned or if it is in the middle of being
        mirrored.
        """
        new_data_pushed = (
             self.branch_type == BranchType.IMPORTED
             and self.next_mirror_time is not None)
        # XXX 2010-04-22, MichaelHudson: This should really look for a branch
        # scan job.
        pulled_but_not_scanned = self.last_mirrored_id != self.last_scanned_id
        pull_in_progress = (
            self.last_mirror_attempt is not None
            and (self.last_mirrored is None
                 or self.last_mirror_attempt > self.last_mirrored))
        return (
            new_data_pushed or pulled_but_not_scanned or pull_in_progress)

    def getScannerData(self):
        """See `IBranch`."""
        columns = (BranchRevision.sequence, Revision.revision_id)
        rows = Store.of(self).using(Revision, BranchRevision).find(
            columns,
            Revision.id == BranchRevision.revision_id,
            BranchRevision.branch_id == self.id)
        rows = rows.order_by(BranchRevision.sequence)
        ancestry = set()
        history = []
        for sequence, revision_id in rows:
            ancestry.add(revision_id)
            if sequence is not None:
                history.append(revision_id)
        return ancestry, history

    def getPullURL(self):
        """See `IBranch`."""
        if self.branch_type == BranchType.MIRRORED:
            # This is a pull branch, hosted externally.
            return self.url
        elif self.branch_type == BranchType.IMPORTED:
            # This is an import branch, imported into bzr from
            # another RCS system such as CVS.
            prefix = config.launchpad.bzr_imports_root_url
            return urlappend(prefix, '%08x' % self.id)
        else:
            raise AssertionError("No pull URL for %r" % (self, ))

    def requestMirror(self):
        """See `IBranch`."""
        if self.branch_type in (BranchType.REMOTE, BranchType.HOSTED):
            raise BranchTypeError(self.unique_name)
        branch = Store.of(self).find(
            Branch,
            Branch.id == self.id,
            Or(Branch.next_mirror_time > UTC_NOW,
               Branch.next_mirror_time == None))
        branch.set(next_mirror_time=UTC_NOW)
        self.next_mirror_time = AutoReload
        return self.next_mirror_time

    def startMirroring(self):
        """See `IBranch`."""
        if self.branch_type in (BranchType.REMOTE, BranchType.HOSTED):
            raise BranchTypeError(self.unique_name)
        self.last_mirror_attempt = UTC_NOW
        self.next_mirror_time = None

    def _findStackedBranch(self, stacked_on_location):
        location = stacked_on_location.strip('/')
        if location.startswith(BRANCH_ID_ALIAS_PREFIX + '/'):
            try:
                branch_id = int(location.split('/', 1)[1])
            except (ValueError, IndexError):
                return None
            return getUtility(IBranchLookup).get(branch_id)
        else:
            return getUtility(IBranchLookup).getByUniqueName(location)

    def branchChanged(self, stacked_on_url, last_revision_id,
                      control_format, branch_format, repository_format):
        """See `IBranch`."""
        self.mirror_status_message = None
        if stacked_on_url == '' or stacked_on_url is None:
            stacked_on_branch = None
        else:
            stacked_on_branch = self._findStackedBranch(stacked_on_url)
            if stacked_on_branch is None:
                self.mirror_status_message = (
                    'Invalid stacked on location: ' + stacked_on_url)
        self.stacked_on = stacked_on_branch
        # If the branch we are stacking on is not public, and we are,
        # set our information_type to the stacked on's, since having a
        # public branch stacked on a private branch does not make sense.
        if (self.stacked_on
            and self.stacked_on.information_type in PRIVATE_INFORMATION_TYPES
            and self.information_type in PUBLIC_INFORMATION_TYPES):
            self.transitionToInformationType(
                self.stacked_on.information_type, self.owner,
                verify_policy=False)
        if self.branch_type == BranchType.HOSTED:
            self.last_mirrored = UTC_NOW
        else:
            self.last_mirrored = self.last_mirror_attempt
        self.mirror_failures = 0
        if (self.next_mirror_time is None
            and self.branch_type == BranchType.MIRRORED):
            # No mirror was requested since we started mirroring.
            increment = getUtility(IBranchPuller).MIRROR_TIME_INCREMENT
            self.next_mirror_time = (
                datetime.now(pytz.timezone('UTC')) + increment)
        self.last_mirrored_id = last_revision_id
        if self.last_scanned_id != last_revision_id:
            from lp.code.model.branchjob import BranchScanJob
            job = BranchScanJob.create(self)
            job.celeryRunOnCommit()
        self.control_format = control_format
        self.branch_format = branch_format
        self.repository_format = repository_format

    def mirrorFailed(self, reason):
        """See `IBranch`."""
        if self.branch_type in (BranchType.REMOTE, BranchType.HOSTED):
            raise BranchTypeError(self.unique_name)
        self.mirror_failures += 1
        self.mirror_status_message = reason
        branch_puller = getUtility(IBranchPuller)
        max_failures = branch_puller.MAXIMUM_MIRROR_FAILURES
        increment = branch_puller.MIRROR_TIME_INCREMENT
        if (self.branch_type == BranchType.MIRRORED
            and self.mirror_failures < max_failures):
            self.next_mirror_time = (
                datetime.now(pytz.timezone('UTC'))
                + increment * 2 ** (self.mirror_failures - 1))

    def destroySelfBreakReferences(self):
        """See `IBranch`."""
        return self.destroySelf(break_references=True)

    def _deleteBranchSubscriptions(self):
        """Delete subscriptions for this branch prior to deleting branch."""
        subscriptions = Store.of(self).find(
            BranchSubscription, BranchSubscription.branch == self)
        subscriptions.remove()

    def _deleteJobs(self):
        """Delete jobs for this branch prior to deleting branch.

        This deletion includes `BranchJob`s associated with the branch,
        as well as `BuildQueue` entries for `TranslationTemplateBuildJob`s
        and `TranslationTemplateBuild`s.
        """
        # Avoid circular imports.
        from lp.code.model.branchjob import BranchJob
        from lp.translations.model.translationtemplatesbuild import (
            TranslationTemplatesBuild,
            )

        store = Store.of(self)
        affected_jobs = Select(
            [BranchJob.jobID],
            And(BranchJob.job == Job.id, BranchJob.branch == self))

        # Delete BuildQueue entries for affected Jobs.  They would pin
        # the affected Jobs in the database otherwise.
        store.find(BuildQueue, BuildQueue.jobID.is_in(affected_jobs)).remove()

        # Find BuildFarmJobs to delete.
        bfjs = store.find(
            (BuildFarmJob.id,),
            TranslationTemplatesBuild.build_farm_job_id == BuildFarmJob.id,
            TranslationTemplatesBuild.branch == self)
        bfj_ids = [bfj[0] for bfj in bfjs]

        # Delete Jobs.  Their BranchJobs cascade along in the database.
        store.find(Job, Job.id.is_in(affected_jobs)).remove()

        store.find(
            TranslationTemplatesBuild,
            TranslationTemplatesBuild.branch == self).remove()
        store.find(BuildFarmJob, BuildFarmJob.id.is_in(bfj_ids)).remove()

    def destroySelf(self, break_references=False):
        """See `IBranch`."""
        from lp.code.interfaces.branchjob import IReclaimBranchSpaceJobSource
        if break_references:
            self._breakReferences()
        if not self.canBeDeleted():
            raise CannotDeleteBranch(
                "Cannot delete branch: %s" % self.unique_name)

        self._deleteBranchSubscriptions()
        self._deleteJobs()

        # Now destroy the branch.
        branch_id = self.id
        SQLBase.destroySelf(self)
        # And now create a job to remove the branch from disk when it's done.
        job = getUtility(IReclaimBranchSpaceJobSource).create(branch_id)
        job.celeryRunOnCommit()

    def commitsForDays(self, since):
        """See `IBranch`."""

        class DateTrunc(NamedFunc):
            name = "date_trunc"

        results = Store.of(self).find(
            (DateTrunc(u'day', Revision.revision_date), Count(Revision.id)),
            Revision.id == BranchRevision.revision_id,
            Revision.revision_date > since,
            BranchRevision.branch == self)
        results = results.group_by(
            DateTrunc(u'day', Revision.revision_date))
        return sorted(results)

    def checkUpgrade(self):
        if self.branch_type is not BranchType.HOSTED:
            raise CannotUpgradeNonHosted(self)
        if self.upgrade_pending:
            raise UpgradePending(self)
        if (
            self.branch_format in CURRENT_BRANCH_FORMATS and
            self.repository_format in CURRENT_REPOSITORY_FORMATS):
            raise AlreadyLatestFormat(self)

    @property
    def needs_upgrading(self):
        """See `IBranch`."""
        try:
            self.checkUpgrade()
        except CannotUpgradeBranch:
            return False
        else:
            return True

    @property
    def upgrade_pending(self):
        """See `IBranch`."""
        from lp.code.model.branchjob import BranchJob, BranchJobType
        store = Store.of(self)
        jobs = store.find(
            BranchJob,
            BranchJob.branch == self,
            Job.id == BranchJob.jobID,
            Job._status != JobStatus.COMPLETED,
            Job._status != JobStatus.FAILED,
            BranchJob.job_type == BranchJobType.UPGRADE_BRANCH)
        return not jobs.is_empty()

    def requestUpgrade(self, requester):
        """See `IBranch`."""
        from lp.code.interfaces.branchjob import IBranchUpgradeJobSource
        job = getUtility(IBranchUpgradeJobSource).create(self, requester)
        job.celeryRunOnCommit()
        return job

    @cachedproperty
    def _known_viewers(self):
        """A set of known persons able to view this branch.

        This method must return an empty set or branch searches will trigger
        late evaluation. Any 'should be set on load' properties must be done by
        the branch search.

        If you are tempted to change this method, don't. Instead see
        visibleByUser which defines the just-in-time policy for branch
        visibility, and IBranchCollection which honours visibility rules.
        """
        return set()

    def visibleByUser(self, user, checked_branches=None):
        """See `IBranch`."""
        if checked_branches is None:
            checked_branches = []
        if self.information_type in PUBLIC_INFORMATION_TYPES:
            can_access = True
        elif user is None:
            can_access = False
        elif user.id in self._known_viewers:
            can_access = True
        else:
            can_access = not getUtility(IAllBranches).withIds(
                self.id).visibleByUser(user).is_empty()
        if can_access and self.stacked_on is not None:
            checked_branches.append(self)
            if self.stacked_on not in checked_branches:
                can_access = self.stacked_on.visibleByUser(
                    user, checked_branches)
        return can_access

    @property
    def recipes(self):
        """See `IHasRecipes`."""
        from lp.code.model.sourcepackagerecipedata import (
            SourcePackageRecipeData)
        return SourcePackageRecipeData.findRecipes(self)

    merge_queue_id = Int(name='merge_queue', allow_none=True)
    merge_queue = Reference(merge_queue_id, 'BranchMergeQueue.id')

    merge_queue_config = StringCol(dbName='merge_queue_config')

    def addToQueue(self, queue):
        """See `IBranchEdit`."""
        self.merge_queue = queue

    def setMergeQueueConfig(self, config):
        """See `IBranchEdit`."""
        try:
            simplejson.loads(config)
            self.merge_queue_config = config
        except ValueError:  # The json string is invalid
            raise InvalidMergeQueueConfig


class DeletionOperation:
    """Represent an operation to perform as part of branch deletion."""

    def __init__(self, affected_object, rationale):
        self.affected_object = ProxyFactory(affected_object)
        self.rationale = rationale

    def __call__(self):
        """Perform the deletion operation."""
        raise NotImplementedError(DeletionOperation.__call__)


class DeletionCallable(DeletionOperation):
    """Deletion operation that invokes a callable."""

    def __init__(self, affected_object, rationale, func):
        DeletionOperation.__init__(self, affected_object, rationale)
        self.func = func

    def __call__(self):
        self.func()

    @classmethod
    def forSourcePackageRecipe(cls, recipe):
        return cls(
            recipe, _('This recipe uses this branch.'), recipe.destroySelf)


class ClearDependentBranch(DeletionOperation):
    """Delete operation that clears a merge proposal's prerequisite branch."""

    def __init__(self, merge_proposal):
        DeletionOperation.__init__(self, merge_proposal,
            _('This branch is the prerequisite branch of this merge'
              ' proposal.'))

    def __call__(self):
        self.affected_object.prerequisite_branch = None


class ClearSeriesBranch(DeletionOperation):
    """Deletion operation that clears a series' branch."""

    def __init__(self, series, branch):
        DeletionOperation.__init__(
            self, series, _('This series is linked to this branch.'))
        self.branch = branch

    def __call__(self):
        if self.affected_object.branch == self.branch:
            self.affected_object.branch = None


class ClearSeriesTranslationsBranch(DeletionOperation):
    """Deletion operation that clears a series' translations branch."""

    def __init__(self, series, branch):
        DeletionOperation.__init__(
            self, series,
            _('This series exports its translations to this branch.'))
        self.branch = branch

    def __call__(self):
        if self.affected_object.translations_branch == self.branch:
            self.affected_object.translations_branch = None


class ClearOfficialPackageBranch(DeletionOperation):
    """Deletion operation that clears an official package branch."""

    def __init__(self, sspb):
        # The affected object is really the sourcepackage.
        DeletionOperation.__init__(
            self, sspb.sourcepackage,
            _('Branch is officially linked to a source package.'))
        # But we'll need the pocket info.
        self.pocket = sspb.pocket

    def __call__(self):
        self.affected_object.setBranch(self.pocket, None, None)


class DeleteCodeImport(DeletionOperation):
    """Deletion operation that deletes a branch's import."""

    def __init__(self, code_import):
        DeletionOperation.__init__(
            self, code_import, _('This is the import data for this branch.'))

    def __call__(self):
        from lp.code.model.codeimport import CodeImportSet
        CodeImportSet().delete(self.affected_object)


class BranchSet:
    """The set of all branches."""

    implements(IBranchSet)

    def getRecentlyChangedBranches(
        self, branch_count=None,
        lifecycle_statuses=DEFAULT_BRANCH_STATUS_IN_LISTING,
        visible_by_user=None):
        """See `IBranchSet`."""
        all_branches = getUtility(IAllBranches)
        branches = all_branches.visibleByUser(
            visible_by_user).withLifecycleStatus(*lifecycle_statuses)
        branches = branches.withBranchType(
            BranchType.HOSTED, BranchType.MIRRORED).scanned().getBranches(
                eager_load=False)
        branches.order_by(
            Desc(Branch.date_last_modified), Desc(Branch.id))
        if branch_count is not None:
            branches.config(limit=branch_count)
        return branches

    def getRecentlyImportedBranches(
        self, branch_count=None,
        lifecycle_statuses=DEFAULT_BRANCH_STATUS_IN_LISTING,
        visible_by_user=None):
        """See `IBranchSet`."""
        all_branches = getUtility(IAllBranches)
        branches = all_branches.visibleByUser(
            visible_by_user).withLifecycleStatus(*lifecycle_statuses)
        branches = branches.withBranchType(
            BranchType.IMPORTED).scanned().getBranches(eager_load=False)
        branches.order_by(
            Desc(Branch.date_last_modified), Desc(Branch.id))
        if branch_count is not None:
            branches.config(limit=branch_count)
        return branches

    def getRecentlyRegisteredBranches(
        self, branch_count=None,
        lifecycle_statuses=DEFAULT_BRANCH_STATUS_IN_LISTING,
        visible_by_user=None):
        """See `IBranchSet`."""
        all_branches = getUtility(IAllBranches)
        branches = all_branches.withLifecycleStatus(
            *lifecycle_statuses).visibleByUser(visible_by_user).getBranches(
                eager_load=False)
        branches.order_by(
            Desc(Branch.date_created), Desc(Branch.id))
        if branch_count is not None:
            branches.config(limit=branch_count)
        return branches

    def getByUniqueName(self, unique_name):
        """See `IBranchSet`."""
        return getUtility(IBranchLookup).getByUniqueName(unique_name)

    def getByUrl(self, url):
        """See `IBranchSet`."""
        return getUtility(IBranchLookup).getByUrl(url)

    def getByUrls(self, urls):
        """See `IBranchSet`."""
        return getUtility(IBranchLookup).getByUrls(urls)

    def getBranches(self, limit=50, eager_load=True):
        """See `IBranchSet`."""
        anon_branches = getUtility(IAllBranches).visibleByUser(None)
        branches = anon_branches.scanned().getBranches(eager_load=eager_load)
        branches.order_by(
            Desc(Branch.date_last_modified), Desc(Branch.id))
        branches.config(limit=limit)
        return branches

    def getBranchVisibilityInfo(self, user, person, branch_names):
        """See `IBranchSet`."""
        if user is None:
            return dict()
        branch_set = getUtility(IBranchLookup)
        visible_branches = []
        for name in branch_names:
            branch = branch_set.getByUniqueName(name)
            try:
                if (branch is not None
                        and branch.visibleByUser(user)
                        and branch.visibleByUser(person)):
                    visible_branches.append(branch.unique_name)
            except Unauthorized:
                # We don't include branches user cannot see.
                pass
        return {
            'person_name': person.displayname,
            'visible_branches': visible_branches}

    def getMergeProposals(self, merged_revision, visible_by_user=None):
        """See IBranchSet."""
        collection = getUtility(IAllBranches).visibleByUser(visible_by_user)
        return collection.getMergeProposals(merged_revision=merged_revision)


def update_trigger_modified_fields(branch):
    """Make the trigger updated fields reload when next accessed."""
    # Not all the fields are exposed through the interface, and some are read
    # only, so remove the security proxy.
    naked_branch = removeSecurityProxy(branch)
    naked_branch.unique_name = AutoReload
    naked_branch.owner_name = AutoReload
    naked_branch.target_suffix = AutoReload


def branch_modified_subscriber(branch, event):
    """This method is subscribed to IObjectModifiedEvents for branches.

    We have a single subscriber registered and dispatch from here to ensure
    that the database fields are updated first before other subscribers.
    """
    update_trigger_modified_fields(branch)
    send_branch_modified_notifications(branch, event)


def get_branch_privacy_filter(user, branch_class=Branch):
    public_branch_filter = (
        branch_class.information_type.is_in(PUBLIC_INFORMATION_TYPES))

    if user is None:
        return [public_branch_filter]

    artifact_grant_query = Coalesce(
        ArrayIntersects(
            SQL('%s.access_grants' % branch_class.__storm_table__),
            Select(
                ArrayAgg(TeamParticipation.teamID),
                tables=TeamParticipation,
                where=(TeamParticipation.person == user)
            )), False)

    policy_grant_query = Coalesce(
        ArrayIntersects(
            Array(branch_class.access_policy),
            Select(
                ArrayAgg(AccessPolicyGrant.policy_id),
                tables=(AccessPolicyGrant,
                        Join(TeamParticipation,
                            TeamParticipation.teamID ==
                            AccessPolicyGrant.grantee_id)),
                where=(TeamParticipation.person == user)
            )), False)

    return [
        Or(public_branch_filter, artifact_grant_query, policy_grant_query)]
