# Copyright 2012-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes for pillar and artifact sharing service."""

__metaclass__ = type
__all__ = [
    'SharingService',
    ]

from itertools import product

from lazr.restful.interfaces import IWebBrowserOriginatingRequest
from lazr.restful.utils import get_current_web_service_request
from storm.expr import (
    And,
    Count,
    Exists,
    In,
    Join,
    LeftJoin,
    Or,
    Select,
    SQL,
    With,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements
from zope.security.interfaces import Unauthorized
from zope.traversing.browser.absoluteurl import absoluteURL

from lp.app.browser.tales import ObjectImageDisplayAPI
from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.blueprints.model.specification import Specification
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.code.interfaces.branchcollection import IAllBranches
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    SharingPermission,
    SpecificationSharingPolicy,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    IAccessPolicyGrantFlatSource,
    IAccessPolicyGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.sharingjob import (
    IRemoveArtifactSubscriptionsJobSource,
    )
from lp.registry.interfaces.sharingservice import ISharingService
from lp.registry.model.accesspolicy import (
    AccessArtifact,
    AccessArtifactGrant,
    AccessPolicy,
    AccessPolicyArtifact,
    AccessPolicyGrant,
    AccessPolicyGrantFlat,
    )
from lp.registry.model.commercialsubscription import CommercialSubscription
from lp.registry.model.distribution import Distribution
from lp.registry.model.person import Person
from lp.registry.model.product import Product
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.bulk import load
from lp.services.database.interfaces import IStore
from lp.services.database.stormexpr import ColumnSelect
from lp.services.searchbuilder import any
from lp.services.webapp.authorization import (
    available_with_permission,
    check_permission,
    )


class SharingService:
    """Service providing operations for adding and removing pillar grantees.

    Service is accessed via a url of the form
    '/services/sharing?ws.op=...
    """

    implements(ISharingService)

    @property
    def name(self):
        """See `IService`."""
        return 'sharing'

    def checkPillarAccess(self, pillars, information_type, person):
        """See `ISharingService`."""
        policies = getUtility(IAccessPolicySource).find(
            [(pillar, information_type) for pillar in pillars])
        policy_ids = [policy.id for policy in policies]
        if not policy_ids:
            return False
        store = IStore(AccessPolicyGrant)
        tables = [
            AccessPolicyGrant,
            Join(
                TeamParticipation,
                TeamParticipation.teamID == AccessPolicyGrant.grantee_id),
            ]
        result = store.using(*tables).find(
            AccessPolicyGrant,
            AccessPolicyGrant.policy_id.is_in(policy_ids),
            TeamParticipation.personID == person.id)
        return not result.is_empty()

    def getAccessPolicyGrantCounts(self, pillar):
        """See `ISharingService`."""
        policies = getUtility(IAccessPolicySource).findByPillar([pillar])
        ids = [policy.id for policy in policies]
        store = IStore(AccessPolicyGrant)
        count_select = Select((Count(),), tables=(AccessPolicyGrant,),
            where=AccessPolicyGrant.policy == AccessPolicy.id)
        return store.find(
            (AccessPolicy.type,
            ColumnSelect(count_select)),
            AccessPolicy.id.is_in(ids)
        )

    def _getSharedPillars(self, person, user, pillar_class, extra_filter=None):
        """Helper method for getSharedProjects and getSharedDistributions.

        pillar_class is either Product or Distribution. Products define the
        owner foreign key attribute as _owner so we need to account for that,
        but otherwise the logic is the same for both pillar types.
        """
        if user is None:
            return []
        store = IStore(AccessPolicyGrantFlat)
        roles = IPersonRoles(user)
        if roles.in_admin:
            filter = True
        else:
            with_statement = With("teams",
                Select(TeamParticipation.teamID,
                    tables=TeamParticipation,
                    where=TeamParticipation.person == user.id))
            teams_sql = SQL("SELECT team from teams")
            store = store.with_(with_statement)
            if IProduct.implementedBy(pillar_class):
                ownerID = pillar_class._ownerID
            else:
                ownerID = pillar_class.ownerID
            filter = Or(
                extra_filter or False,
                ownerID.is_in(teams_sql),
                pillar_class.driverID.is_in(teams_sql))
        tables = [
            AccessPolicyGrantFlat,
            Join(
                AccessPolicy,
                AccessPolicyGrantFlat.policy_id == AccessPolicy.id)]
        if IProduct.implementedBy(pillar_class):
            access_policy_column = AccessPolicy.product_id
        else:
            access_policy_column = AccessPolicy.distribution_id
        result_set = store.find(
            pillar_class,
            pillar_class.id.is_in(
                Select(
                    columns=access_policy_column, tables=tables,
                    where=(AccessPolicyGrantFlat.grantee_id == person.id))
            ), filter)
        return result_set

    def getSharedProjects(self, person, user):
        """See `ISharingService`."""
        commercial_filter = None
        if user and IPersonRoles(user).in_commercial_admin:
            commercial_filter = Exists(Select(
                1, tables=CommercialSubscription,
                where=CommercialSubscription.product == Product.id))
        return self._getSharedPillars(person, user, Product, commercial_filter)

    def getSharedDistributions(self, person, user):
        """See `ISharingService`."""
        return self._getSharedPillars(person, user, Distribution)

    def getArtifactGrantsForPersonOnPillar(self, pillar, person):
        """Return the artifact grants for the given person and pillar."""
        policies = getUtility(IAccessPolicySource).findByPillar([pillar])
        flat_source = getUtility(IAccessPolicyGrantFlatSource)
        return flat_source.findArtifactsByGrantee(person, policies)

    @available_with_permission('launchpad.Driver', 'pillar')
    def getSharedArtifacts(self, pillar, person, user, include_bugs=True,
                           include_branches=True, include_specifications=True):
        """See `ISharingService`."""
        bug_ids = set()
        branch_ids = set()
        specification_ids = set()
        for artifact in self.getArtifactGrantsForPersonOnPillar(
            pillar, person):
            if artifact.bug_id and include_bugs:
                bug_ids.add(artifact.bug_id)
            elif artifact.branch_id and include_branches:
                branch_ids.add(artifact.branch_id)
            elif artifact.specification_id and include_specifications:
                specification_ids.add(artifact.specification_id)

        # Load the bugs.
        bugtasks = []
        if bug_ids:
            param = BugTaskSearchParams(user=user, bug=any(*bug_ids))
            param.setTarget(pillar)
            bugtasks = list(getUtility(IBugTaskSet).search(param))
        # Load the branches.
        branches = []
        if branch_ids:
            all_branches = getUtility(IAllBranches)
            wanted_branches = all_branches.visibleByUser(user).withIds(
                *branch_ids)
            branches = list(wanted_branches.getBranches())
        specifications = []
        if specification_ids:
            specifications = load(Specification, specification_ids)

        return bugtasks, branches, specifications

    def checkPillarArtifactAccess(self, pillar, user):
        """See `ISharingService`."""
        tables = [
            AccessPolicyGrantFlat,
            Join(
                TeamParticipation,
                TeamParticipation.teamID == AccessPolicyGrantFlat.grantee_id),
            Join(
                AccessPolicy,
                AccessPolicy.id == AccessPolicyGrantFlat.policy_id)]
        return not IStore(AccessPolicyGrantFlat).using(*tables).find(
            AccessPolicyGrantFlat,
            AccessPolicy.product_id == pillar.id,
            TeamParticipation.personID == user.id).is_empty()

    @available_with_permission('launchpad.Driver', 'pillar')
    def getSharedBugs(self, pillar, person, user):
        """See `ISharingService`."""
        bugtasks, ignore, ignore = self.getSharedArtifacts(
            pillar, person, user, include_branches=False,
            include_specifications=False)
        return bugtasks

    @available_with_permission('launchpad.Driver', 'pillar')
    def getSharedBranches(self, pillar, person, user):
        """See `ISharingService`."""
        ignore, branches, ignore = self.getSharedArtifacts(
            pillar, person, user, include_bugs=False,
            include_specifications=False)
        return branches

    @available_with_permission('launchpad.Driver', 'pillar')
    def getSharedSpecifications(self, pillar, person, user):
        """See `ISharingService`."""
        ignore, ignore, specifications = self.getSharedArtifacts(
            pillar, person, user, include_bugs=False,
            include_branches=False)
        return specifications

    def _getVisiblePrivateSpecificationIDs(self, person, specifications):
        store = Store.of(specifications[0])
        tables = (
            Specification,
            Join(
                AccessPolicy,
                And(
                    Or(
                        Specification.distributionID ==
                            AccessPolicy.distribution_id,
                        Specification.productID ==
                            AccessPolicy.product_id),
                    AccessPolicy.type == Specification.information_type)),
            Join(
                AccessPolicyGrantFlat,
                AccessPolicy.id == AccessPolicyGrantFlat.policy_id
                ),
            LeftJoin(
                AccessArtifact,
                AccessArtifact.id ==
                    AccessPolicyGrantFlat.abstract_artifact_id),
            Join(
                TeamParticipation,
                TeamParticipation.teamID ==
                    AccessPolicyGrantFlat.grantee_id))
        spec_ids = [spec.id for spec in specifications]
        return set(store.using(*tables).find(
            Specification.id,
            Or(
                AccessPolicyGrantFlat.abstract_artifact_id == None,
                AccessArtifact.specification == Specification.id),
            TeamParticipation.personID == person.id,
            In(Specification.id, spec_ids)))

    def getVisibleArtifacts(self, person, branches=None, bugs=None,
                            specifications=None, ignore_permissions=False):
        """See `ISharingService`."""
        bugs_by_id = {}
        branches_by_id = {}
        for bug in bugs or []:
            if (not ignore_permissions
                and not check_permission('launchpad.View', bug)):
                raise Unauthorized
            bugs_by_id[bug.id] = bug
        for branch in branches or []:
            if (not ignore_permissions
                and not check_permission('launchpad.View', branch)):
                raise Unauthorized
            branches_by_id[branch.id] = branch
        for spec in specifications or []:
            if (not ignore_permissions
                and not check_permission('launchpad.View', spec)):
                raise Unauthorized

        # Load the bugs.
        visible_bug_ids = []
        if bugs_by_id:
            param = BugTaskSearchParams(
                user=person, bug=any(*bugs_by_id.keys()))
            visible_bug_ids = set(getUtility(IBugTaskSet).searchBugIds(param))
        visible_bugs = [bugs_by_id[bug_id] for bug_id in visible_bug_ids]

        # Load the branches.
        visible_branches = []
        if branches_by_id:
            all_branches = getUtility(IAllBranches)
            wanted_branches = all_branches.visibleByUser(person).withIds(
                *branches_by_id.keys())
            visible_branches = list(wanted_branches.getBranches())

        visible_specs = []
        if specifications:
            visible_private_spec_ids = self._getVisiblePrivateSpecificationIDs(
                person, specifications)
            visible_specs = [
                spec for spec in specifications
                if spec.id in visible_private_spec_ids or not spec.private]

        return visible_bugs, visible_branches, visible_specs

    def getInvisibleArtifacts(self, person, branches=None, bugs=None):
        """See `ISharingService`."""
        bugs_by_id = {}
        branches_by_id = {}
        for bug in bugs or []:
            bugs_by_id[bug.id] = bug
        for branch in branches or []:
            branches_by_id[branch.id] = branch

        # Load the bugs.
        visible_bug_ids = set()
        if bugs_by_id:
            param = BugTaskSearchParams(
                user=person, bug=any(*bugs_by_id.keys()))
            visible_bug_ids = set(getUtility(IBugTaskSet).searchBugIds(param))
        invisible_bug_ids = set(bugs_by_id.keys()).difference(visible_bug_ids)
        invisible_bugs = [bugs_by_id[bug_id] for bug_id in invisible_bug_ids]

        # Load the branches.
        invisible_branches = []
        if branches_by_id:
            all_branches = getUtility(IAllBranches)
            visible_branch_ids = all_branches.visibleByUser(person).withIds(
                *branches_by_id.keys()).getBranchIds()
            invisible_branch_ids = (
                set(branches_by_id.keys()).difference(visible_branch_ids))
            invisible_branches = [
                branches_by_id[branch_id]
                for branch_id in invisible_branch_ids]

        return invisible_bugs, invisible_branches

    def getPeopleWithoutAccess(self, concrete_artifact, people):
        """See `ISharingService`."""
        # Public artifacts allow everyone to have access.
        access_artifacts = list(
            getUtility(IAccessArtifactSource).find([concrete_artifact]))
        if not access_artifacts:
            return []

        access_artifact = access_artifacts[0]
        # Determine the grantees who have access via an access policy grant.
        policy_grantees = (
            Select(
                (AccessPolicyGrant.grantee_id,),
                where=And(
                    AccessPolicyArtifact.abstract_artifact == access_artifact,
                    AccessPolicyGrant.policy_id ==
                        AccessPolicyArtifact.policy_id)))

        # Determine the grantees who have access via an access artifact grant.
        artifact_grantees = (
            Select(
                (AccessArtifactGrant.grantee_id,),
                where=And(
                    AccessArtifactGrant.abstract_artifact_id ==
                        access_artifact.id)))

        # Find the people who can see the artifacts.
        person_ids = [person.id for person in people]
        store = IStore(AccessArtifactGrant)
        tables = [
            Person,
            Join(TeamParticipation, TeamParticipation.personID == Person.id)]
        result_set = store.using(*tables).find(
            Person,
            Or(
                In(TeamParticipation.teamID, policy_grantees),
                In(TeamParticipation.teamID, artifact_grantees)),
            In(Person.id, person_ids))

        return set(people).difference(set(result_set))

    def _makeEnumData(self, enums):
        # Make a dict of data for the a view request cache.
        result_data = []
        for x, enum in enumerate(enums):
            item = dict(
                index=x,
                value=enum.name,
                title=enum.title,
                description=enum.description
            )
            result_data.append(item)
        return result_data

    def getAllowedInformationTypes(self, pillar):
        """See `ISharingService`."""
        allowed_private_types = [
            policy.type
            for policy in getUtility(IAccessPolicySource).findByPillar(
                [pillar])]
        # We want the types in a specific order.
        return self._makeEnumData([
            type for type in PRIVATE_INFORMATION_TYPES
            if type in allowed_private_types])

    def getBranchSharingPolicies(self, pillar):
        """See `ISharingService`."""
        # Only Products have branch sharing policies. Distributions just
        # default to Public.
        # If the branch sharing policy is EMBARGOED_OR_PROPRIETARY, then we
        # do not allow any other policies.
        allowed_policies = [BranchSharingPolicy.PUBLIC]
        # Commercial projects also allow proprietary branches.
        if (IProduct.providedBy(pillar)
            and pillar.has_current_commercial_subscription):

            if pillar.private:
                allowed_policies = [
                    BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                    BranchSharingPolicy.PROPRIETARY,
                ]
            else:
                allowed_policies = [
                    BranchSharingPolicy.PUBLIC,
                    BranchSharingPolicy.PUBLIC_OR_PROPRIETARY,
                    BranchSharingPolicy.PROPRIETARY_OR_PUBLIC,
                    BranchSharingPolicy.PROPRIETARY,
                ]

        if (pillar.branch_sharing_policy and
            not pillar.branch_sharing_policy in allowed_policies):
            allowed_policies.append(pillar.branch_sharing_policy)

        return self._makeEnumData(allowed_policies)

    def getBugSharingPolicies(self, pillar):
        """See `ISharingService`."""
        # Only Products have bug sharing policies. Distributions just
        # default to Public.
        allowed_policies = [BugSharingPolicy.PUBLIC]
        # Commercial projects also allow proprietary bugs.
        if (IProduct.providedBy(pillar)
            and pillar.has_current_commercial_subscription):

            if pillar.private:
                allowed_policies = [
                    BugSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                    BugSharingPolicy.PROPRIETARY,
                ]
            else:
                allowed_policies = [
                    BugSharingPolicy.PUBLIC,
                    BugSharingPolicy.PUBLIC_OR_PROPRIETARY,
                    BugSharingPolicy.PROPRIETARY_OR_PUBLIC,
                    BugSharingPolicy.PROPRIETARY,
                ]

        if (pillar.bug_sharing_policy and
            not pillar.bug_sharing_policy in allowed_policies):
            allowed_policies.append(pillar.bug_sharing_policy)

        return self._makeEnumData(allowed_policies)

    def getSpecificationSharingPolicies(self, pillar):
        """See `ISharingService`."""
        # Only Products have specification sharing policies. Distributions just
        # default to Public.
        allowed_policies = [SpecificationSharingPolicy.PUBLIC]
        # Commercial projects also allow proprietary specifications.
        if (IProduct.providedBy(pillar)
            and pillar.has_current_commercial_subscription):

            if pillar.private:
                allowed_policies = [
                    SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                    SpecificationSharingPolicy.PROPRIETARY,
                ]
            else:
                allowed_policies = [
                    SpecificationSharingPolicy.PUBLIC,
                    SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY,
                    SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC,
                    SpecificationSharingPolicy.PROPRIETARY,
                ]

        if (pillar.specification_sharing_policy and
            not pillar.specification_sharing_policy in allowed_policies):
            allowed_policies.append(pillar.specification_sharing_policy)

        return self._makeEnumData(allowed_policies)

    def getSharingPermissions(self):
        """See `ISharingService`."""
        # We want the permissions displayed in the following order.
        ordered_permissions = [
            SharingPermission.ALL,
            SharingPermission.SOME,
            SharingPermission.NOTHING
        ]
        sharing_permissions = []
        for x, permission in enumerate(ordered_permissions):
            item = dict(
                index=x,
                value=permission.name,
                title=permission.title,
                description=permission.description
            )
            sharing_permissions.append(item)
        return sharing_permissions

    @available_with_permission('launchpad.Driver', 'pillar')
    def getPillarGrantees(self, pillar):
        """See `ISharingService`."""
        policies = getUtility(IAccessPolicySource).findByPillar([pillar])
        ap_grant_flat = getUtility(IAccessPolicyGrantFlatSource)
        # XXX 2012-03-22 wallyworld bug 961836
        # We want to use person_sort_key(Person.displayname, Person.name) but
        # StormRangeFactory doesn't support that yet.
        grant_permissions = ap_grant_flat.findGranteePermissionsByPolicy(
            policies).order_by(Person.displayname, Person.name)
        return grant_permissions

    @available_with_permission('launchpad.Driver', 'pillar')
    def getPillarGranteeData(self, pillar):
        """See `ISharingService`."""
        grant_permissions = list(self.getPillarGrantees(pillar))
        if not grant_permissions:
            return None
        return self.jsonGranteeData(grant_permissions)

    def jsonGranteeData(self, grant_permissions):
        """See `ISharingService`."""
        result = []
        request = get_current_web_service_request()
        browser_request = IWebBrowserOriginatingRequest(request)
        # We need to precache icon and validity information for the batch.
        grantee_ids = [grantee[0].id for grantee in grant_permissions]
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            grantee_ids, need_icon=True, need_validity=True))
        for (grantee, permissions, shared_artifact_types) in grant_permissions:
            some_things_shared = len(shared_artifact_types) > 0
            grantee_permissions = {}
            for (policy, permission) in permissions.iteritems():
                grantee_permissions[policy.type.name] = permission.name
            shared_artifact_type_names = [
                info_type.name for info_type in shared_artifact_types]
            display_api = ObjectImageDisplayAPI(grantee)
            icon_url = display_api.custom_icon_url()
            sprite_css = display_api.sprite_css()
            result.append({
                'name': grantee.name,
                'icon_url': icon_url,
                'sprite_css': sprite_css,
                'display_name': grantee.displayname,
                'self_link': absoluteURL(grantee, request),
                'web_link': absoluteURL(grantee, browser_request),
                'permissions': grantee_permissions,
                'shared_artifact_types': shared_artifact_type_names,
                'shared_items_exist': some_things_shared})
        return result

    @available_with_permission('launchpad.Edit', 'pillar')
    def sharePillarInformation(self, pillar, grantee, user, permissions):
        """See `ISharingService`."""

        # We do not support adding grantees to project groups.
        assert not IProjectGroup.providedBy(pillar)

        # Separate out the info types according to permission.
        information_types = permissions.keys()
        info_types_for_all = [
            info_type for info_type in information_types
            if permissions[info_type] == SharingPermission.ALL]
        info_types_for_some = [
            info_type for info_type in information_types
            if permissions[info_type] == SharingPermission.SOME]
        info_types_for_nothing = [
            info_type for info_type in information_types
            if permissions[info_type] == SharingPermission.NOTHING]

        # The wanted policies are for the information_types in all.
        required_pillar_info_types = [
            (pillar, information_type)
            for information_type in information_types
            if information_type in info_types_for_all]
        policy_source = getUtility(IAccessPolicySource)
        policy_grant_source = getUtility(IAccessPolicyGrantSource)
        if len(required_pillar_info_types) > 0:
            wanted_pillar_policies = policy_source.find(
                required_pillar_info_types)
            # We need to figure out which policy grants to create or delete.
            wanted_policy_grants = [(policy, grantee)
                for policy in wanted_pillar_policies]
            existing_policy_grants = [
                (grant.policy, grant.grantee)
                for grant in policy_grant_source.find(wanted_policy_grants)]
            # Create any newly required policy grants.
            policy_grants_to_create = (
                set(wanted_policy_grants).difference(existing_policy_grants))
            if len(policy_grants_to_create) > 0:
                policy_grant_source.grant(
                    [(policy, grantee, user)
                    for policy, grantee in policy_grants_to_create])

        # Now revoke any existing policy grants for types with
        # permission 'some'.
        all_pillar_policies = policy_source.findByPillar([pillar])
        policy_grants_to_revoke = [
            (policy, grantee)
            for policy in all_pillar_policies
            if policy.type in info_types_for_some]
        if len(policy_grants_to_revoke) > 0:
            policy_grant_source.revoke(policy_grants_to_revoke)

        # For information types with permission 'nothing', we can simply
        # call the deletePillarGrantee method directly.
        if len(info_types_for_nothing) > 0:
            self.deletePillarGrantee(
                pillar, grantee, user, info_types_for_nothing)

        # Return grantee data to the caller.
        ap_grant_flat = getUtility(IAccessPolicyGrantFlatSource)
        grant_permissions = list(ap_grant_flat.findGranteePermissionsByPolicy(
            all_pillar_policies, [grantee]))

        grant_counts = list(self.getAccessPolicyGrantCounts(pillar))
        invisible_types = [
            count_info[0].title for count_info in grant_counts
            if count_info[1] == 0]
        grantee = None
        if grant_permissions:
            [grantee] = self.jsonGranteeData(grant_permissions)
        result = {
            'grantee_entry': grantee,
            'invisible_information_types': invisible_types}
        return result

    @available_with_permission('launchpad.Edit', 'pillar')
    def deletePillarGrantee(self, pillar, grantee, user,
                             information_types=None):
        """See `ISharingService`."""

        policy_source = getUtility(IAccessPolicySource)
        if information_types is None:
            # We delete all policy grants for the pillar.
            pillar_policies = policy_source.findByPillar([pillar])
        else:
            # We delete selected policy grants for the pillar.
            pillar_policy_types = [
                (pillar, information_type)
                for information_type in information_types]
            pillar_policies = list(policy_source.find(pillar_policy_types))

        # First delete any access policy grants.
        policy_grant_source = getUtility(IAccessPolicyGrantSource)
        policy_grants = [(policy, grantee) for policy in pillar_policies]
        grants_to_revoke = [
            (grant.policy, grant.grantee)
            for grant in policy_grant_source.find(policy_grants)]
        if len(grants_to_revoke) > 0:
            policy_grant_source.revoke(grants_to_revoke)

        # Second delete any access artifact grants.
        ap_grant_flat = getUtility(IAccessPolicyGrantFlatSource)
        artifacts_to_revoke = list(ap_grant_flat.findArtifactsByGrantee(
            grantee, pillar_policies))
        if len(artifacts_to_revoke) > 0:
            getUtility(IAccessArtifactGrantSource).revokeByArtifact(
                artifacts_to_revoke, [grantee])

        # Create a job to remove subscriptions for artifacts the grantee can no
        # longer see.
        if grants_to_revoke or artifacts_to_revoke:
            getUtility(IRemoveArtifactSubscriptionsJobSource).create(
                user, artifacts=None, grantee=grantee, pillar=pillar,
                information_types=information_types)

        grant_counts = list(self.getAccessPolicyGrantCounts(pillar))
        invisible_types = [
            count_info[0].title for count_info in grant_counts
            if count_info[1] == 0]
        return invisible_types

    @available_with_permission('launchpad.Edit', 'pillar')
    def revokeAccessGrants(self, pillar, grantee, user, branches=None,
                           bugs=None, specifications=None):
        """See `ISharingService`."""

        if not branches and not bugs and not specifications:
            raise ValueError(
                "Either bugs, branches or specifications must be specified")

        artifacts = []
        if branches:
            artifacts.extend(branches)
        if bugs:
            artifacts.extend(bugs)
        if specifications:
            artifacts.extend(specifications)
        # Find the access artifacts associated with the bugs and branches.
        accessartifact_source = getUtility(IAccessArtifactSource)
        artifacts_to_delete = accessartifact_source.find(artifacts)
        # Revoke access to bugs/branches for the specified grantee.
        getUtility(IAccessArtifactGrantSource).revokeByArtifact(
            artifacts_to_delete, [grantee])

        # Create a job to remove subscriptions for artifacts the grantee can no
        # longer see.
        getUtility(IRemoveArtifactSubscriptionsJobSource).create(
            user, artifacts, grantee=grantee, pillar=pillar)

    def ensureAccessGrants(self, grantees, user, branches=None, bugs=None,
                           specifications=None, ignore_permissions=False):
        """See `ISharingService`."""

        artifacts = []
        if branches:
            artifacts.extend(branches)
        if bugs:
            artifacts.extend(bugs)
        if specifications:
            artifacts.extend(specifications)
        if not ignore_permissions:
            # The user needs to have launchpad.Edit permission on all supplied
            # bugs and branches or else we raise an Unauthorized exception.
            for artifact in artifacts or []:
                if not check_permission('launchpad.Edit', artifact):
                    raise Unauthorized

        # Ensure there are access artifacts associated with the bugs and
        # branches.
        artifacts = getUtility(IAccessArtifactSource).ensure(artifacts)
        aagsource = getUtility(IAccessArtifactGrantSource)
        artifacts_with_grants = [
            artifact_grant.abstract_artifact
            for artifact_grant in
            aagsource.find(product(artifacts, grantees))]
        # Create access to bugs/branches for the specified grantee for which a
        # grant does not already exist.
        missing_artifacts = set(artifacts) - set(artifacts_with_grants)
        getUtility(IAccessArtifactGrantSource).grant(
            list(product(missing_artifacts, grantees, [user])))

    @available_with_permission('launchpad.Edit', 'pillar')
    def updatePillarSharingPolicies(self, pillar, branch_sharing_policy=None,
                                    bug_sharing_policy=None,
                                    specification_sharing_policy=None):
        if (not branch_sharing_policy and not bug_sharing_policy and not
            specification_sharing_policy):
            return None
        # Only Products have sharing policies.
        if not IProduct.providedBy(pillar):
            raise ValueError(
                "Sharing policies are only supported for products.")
        if branch_sharing_policy:
            pillar.setBranchSharingPolicy(branch_sharing_policy)
        if bug_sharing_policy:
            pillar.setBugSharingPolicy(bug_sharing_policy)
        if specification_sharing_policy:
            pillar.setSpecificationSharingPolicy(specification_sharing_policy)
