# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementations of `IBranchNamespace`."""

__metaclass__ = type
__all__ = [
    'BranchNamespaceSet',
    'PackageNamespace',
    'PersonalNamespace',
    'BRANCH_POLICY_ALLOWED_TYPES',
    'ProductNamespace',
    ]


from lazr.lifecycle.event import ObjectCreatedEvent
from storm.locals import And
from zope.component import getUtility
from zope.event import notify
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import (
    FREE_INFORMATION_TYPES,
    InformationType,
    NON_EMBARGOED_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.app.interfaces.services import IService
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchSubscriptionDiffSize,
    BranchSubscriptionNotificationLevel,
    CodeReviewNotificationLevel,
    )
from lp.code.errors import (
    BranchCreationForbidden,
    BranchCreatorNotMemberOfOwnerTeam,
    BranchCreatorNotOwner,
    BranchExists,
    InvalidNamespace,
    NoSuchBranch,
    )
from lp.code.interfaces.branch import (
    IBranch,
    user_has_special_branch_access,
    )
from lp.code.interfaces.branchnamespace import (
    IBranchNamespace,
    IBranchNamespacePolicy,
    )
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.model.branch import Branch
from lp.registry.enums import (
    BranchSharingPolicy,
    PersonVisibility,
    )
from lp.registry.errors import (
    NoSuchDistroSeries,
    NoSuchSourcePackageName,
    )
from lp.registry.interfaces.distribution import (
    IDistributionSet,
    NoSuchDistribution,
    )
from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.registry.interfaces.person import (
    IPersonSet,
    NoSuchPerson,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    NoSuchProduct,
    )
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.model.sourcepackage import SourcePackage
from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore


BRANCH_POLICY_ALLOWED_TYPES = {
    BranchSharingPolicy.PUBLIC: FREE_INFORMATION_TYPES,
    BranchSharingPolicy.PUBLIC_OR_PROPRIETARY: NON_EMBARGOED_INFORMATION_TYPES,
    BranchSharingPolicy.PROPRIETARY_OR_PUBLIC: (
        NON_EMBARGOED_INFORMATION_TYPES),
    BranchSharingPolicy.PROPRIETARY: [InformationType.PROPRIETARY],
    BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY:
        [InformationType.PROPRIETARY, InformationType.EMBARGOED],
    BranchSharingPolicy.FORBIDDEN: [],
    }

BRANCH_POLICY_DEFAULT_TYPES = {
    BranchSharingPolicy.PUBLIC: InformationType.PUBLIC,
    BranchSharingPolicy.PUBLIC_OR_PROPRIETARY: InformationType.PUBLIC,
    BranchSharingPolicy.PROPRIETARY_OR_PUBLIC: InformationType.PROPRIETARY,
    BranchSharingPolicy.PROPRIETARY: InformationType.PROPRIETARY,
    BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY: InformationType.EMBARGOED,
    BranchSharingPolicy.FORBIDDEN: None,
    }

BRANCH_POLICY_REQUIRED_GRANTS = {
    BranchSharingPolicy.PUBLIC: None,
    BranchSharingPolicy.PUBLIC_OR_PROPRIETARY: None,
    BranchSharingPolicy.PROPRIETARY_OR_PUBLIC: InformationType.PROPRIETARY,
    BranchSharingPolicy.PROPRIETARY: InformationType.PROPRIETARY,
    BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY: InformationType.PROPRIETARY,
    BranchSharingPolicy.FORBIDDEN: None,
    }


class _BaseNamespace:
    """Common code for branch namespaces."""

    def createBranch(self, branch_type, name, registrant, url=None,
                     title=None,
                     lifecycle_status=BranchLifecycleStatus.DEVELOPMENT,
                     summary=None, whiteboard=None, date_created=None,
                     branch_format=None, repository_format=None,
                     control_format=None):
        """See `IBranchNamespace`."""

        self.validateRegistrant(registrant)
        self.validateBranchName(name)

        if date_created is None:
            date_created = UTC_NOW

        # Run any necessary data massage on the branch URL.
        if url is not None:
            url = IBranch['url'].normalize(url)

        product = getattr(self, 'product', None)
        sourcepackage = getattr(self, 'sourcepackage', None)
        if sourcepackage is None:
            distroseries = None
            sourcepackagename = None
        else:
            distroseries = sourcepackage.distroseries
            sourcepackagename = sourcepackage.sourcepackagename

        information_type = self.getDefaultInformationType(registrant)
        if information_type is None:
            raise BranchCreationForbidden()

        branch = Branch(
            registrant=registrant, name=name, owner=self.owner,
            product=product, url=url, title=title,
            lifecycle_status=lifecycle_status, summary=summary,
            whiteboard=whiteboard, information_type=information_type,
            date_created=date_created, branch_type=branch_type,
            date_last_modified=date_created, branch_format=branch_format,
            repository_format=repository_format,
            control_format=control_format, distroseries=distroseries,
            sourcepackagename=sourcepackagename)

        # The registrant of the branch should also be automatically subscribed
        # in order for them to get code review notifications.  The implicit
        # registrant subscription does not cause email to be sent about
        # attribute changes, just merge proposals and code review comments.
        branch.subscribe(
            self.owner,
            BranchSubscriptionNotificationLevel.NOEMAIL,
            BranchSubscriptionDiffSize.NODIFF,
            CodeReviewNotificationLevel.FULL,
            registrant)

        branch._reconcileAccess()

        notify(ObjectCreatedEvent(branch))
        return branch

    def validateRegistrant(self, registrant, branch=None):
        """See `IBranchNamespace`."""
        if user_has_special_branch_access(registrant, branch):
            return
        owner = self.owner
        if not registrant.inTeam(owner):
            if owner.is_team:
                raise BranchCreatorNotMemberOfOwnerTeam(
                    "%s is not a member of %s"
                    % (registrant.displayname, owner.displayname))
            else:
                raise BranchCreatorNotOwner(
                    "%s cannot create branches owned by %s"
                    % (registrant.displayname, owner.displayname))

        if not self.getAllowedInformationTypes(registrant):
            raise BranchCreationForbidden(
                'You cannot create branches in "%s"' % self.name)

    def validateBranchName(self, name):
        """See `IBranchNamespace`."""
        existing_branch = self.getByName(name)
        if existing_branch is not None:
            raise BranchExists(existing_branch)

        # Not all code paths that lead to branch creation go via a
        # schema-validated form (e.g. the register_branch XML-RPC call or
        # pushing a new branch to codehosting), so we validate the branch name
        # here to give a nicer error message than 'ERROR: new row for relation
        # "branch" violates check constraint "valid_name"...'.
        IBranch['name'].validate(unicode(name))

    def validateMove(self, branch, mover, name=None):
        """See `IBranchNamespace`."""
        if name is None:
            name = branch.name
        self.validateBranchName(name)
        self.validateRegistrant(mover, branch)

    def moveBranch(self, branch, mover, new_name=None,
                   rename_if_necessary=False):
        """See `IBranchNamespace`."""
        # Check to see if the branch is already in this namespace.
        old_namespace = branch.namespace
        if self.name == old_namespace.name:
            return
        if new_name is None:
            new_name = branch.name
        if rename_if_necessary:
            new_name = self.findUnusedName(new_name)
        self.validateMove(branch, mover, new_name)
        # Remove the security proxy of the branch as the owner and target
        # attributes are readonly through the interface.
        naked_branch = removeSecurityProxy(branch)
        naked_branch.owner = self.owner
        self.target._retargetBranch(naked_branch)
        naked_branch.name = new_name

    def createBranchWithPrefix(self, branch_type, prefix, registrant,
                               url=None):
        """See `IBranchNamespace`."""
        name = self.findUnusedName(prefix)
        return self.createBranch(branch_type, name, registrant, url=url)

    def findUnusedName(self, prefix):
        """See `IBranchNamespace`."""
        name = prefix
        count = 0
        while self.isNameUsed(name):
            count += 1
            name = "%s-%s" % (prefix, count)
        return name

    def getBranches(self, eager_load=False):
        """See `IBranchNamespace`."""
        return IStore(Branch).find(Branch, self._getBranchesClause())

    def getBranchName(self, branch_name):
        """See `IBranchNamespace`."""
        return '%s/%s' % (self.name, branch_name)

    def getByName(self, branch_name, default=None):
        """See `IBranchNamespace`."""
        match = IStore(Branch).find(
            Branch, self._getBranchesClause(),
            Branch.name == branch_name).one()
        if match is None:
            match = default
        return match

    def isNameUsed(self, branch_name):
        return self.getByName(branch_name) is not None

    def canCreateBranches(self, user):
        """See `IBranchNamespace`."""
        try:
            self.validateRegistrant(user)
        except BranchCreatorNotMemberOfOwnerTeam:
            return False
        except BranchCreatorNotOwner:
            return False
        except BranchCreationForbidden:
            return False
        else:
            return True

    def getAllowedInformationTypes(self, who=None):
        """See `IBranchNamespace`."""
        raise NotImplementedError

    def getDefaultInformationType(self, who=None):
        """See `IBranchNamespace`."""
        raise NotImplementedError


class PersonalNamespace(_BaseNamespace):
    """A namespace for personal (or 'junk') branches.

    Branches in this namespace have names like '~foo/+junk/bar'.
    """

    implements(IBranchNamespace, IBranchNamespacePolicy)

    def __init__(self, person):
        self.owner = person

    def _getBranchesClause(self):
        return And(
            Branch.owner == self.owner, Branch.product == None,
            Branch.distroseries == None, Branch.sourcepackagename == None)

    @property
    def name(self):
        """See `IBranchNamespace`."""
        return '~%s/+junk' % self.owner.name

    @property
    def _is_private_team(self):
        return (
            self.owner.is_team
            and self.owner.visibility == PersonVisibility.PRIVATE)

    def getAllowedInformationTypes(self, who=None):
        """See `IBranchNamespace`."""
        # Private teams get private branches, everyone else gets public ones.
        if self._is_private_team:
            return NON_EMBARGOED_INFORMATION_TYPES
        else:
            return FREE_INFORMATION_TYPES

    def getDefaultInformationType(self, who=None):
        """See `IBranchNamespace`."""
        if self._is_private_team:
            return InformationType.PROPRIETARY
        else:
            return InformationType.PUBLIC

    @property
    def target(self):
        """See `IBranchNamespace`."""
        return IBranchTarget(self.owner)


class ProductNamespace(_BaseNamespace):
    """A namespace for product branches.

    This namespace is for all the branches owned by a particular person in a
    particular product.
    """

    implements(IBranchNamespace, IBranchNamespacePolicy)

    def __init__(self, person, product):
        self.owner = person
        self.product = product

    def _getBranchesClause(self):
        return And(Branch.owner == self.owner, Branch.product == self.product)

    @property
    def name(self):
        """See `IBranchNamespace`."""
        return '~%s/%s' % (self.owner.name, self.product.name)

    @property
    def target(self):
        """See `IBranchNamespace`."""
        return IBranchTarget(self.product)

    def getAllowedInformationTypes(self, who=None):
        """See `IBranchNamespace`."""
        # The project uses the new simplified branch_sharing_policy
        # rules, so check them.

        # Some policies require that the branch owner or current user have
        # full access to an information type. If it's required and the user
        # doesn't hold it, no information types are legal.
        required_grant = BRANCH_POLICY_REQUIRED_GRANTS[
            self.product.branch_sharing_policy]
        if (required_grant is not None
            and not getUtility(IService, 'sharing').checkPillarAccess(
                [self.product], required_grant, self.owner)
            and (who is None
                or not getUtility(IService, 'sharing').checkPillarAccess(
                    [self.product], required_grant, who))):
            return []

        return BRANCH_POLICY_ALLOWED_TYPES[
            self.product.branch_sharing_policy]

    def getDefaultInformationType(self, who=None):
        """See `IBranchNamespace`."""
        default_type = BRANCH_POLICY_DEFAULT_TYPES[
            self.product.branch_sharing_policy]
        if default_type not in self.getAllowedInformationTypes(who):
            return None
        return default_type


class PackageNamespace(_BaseNamespace):
    """A namespace for source package branches.

    This namespace is for all the branches owned by a particular person in a
    particular source package in a particular distroseries.
    """

    implements(IBranchNamespace, IBranchNamespacePolicy)

    def __init__(self, person, sourcepackage):
        self.owner = person
        self.sourcepackage = sourcepackage

    def _getBranchesClause(self):
        return And(
            Branch.owner == self.owner,
            Branch.distroseries == self.sourcepackage.distroseries,
            Branch.sourcepackagename == self.sourcepackage.sourcepackagename)

    @property
    def name(self):
        """See `IBranchNamespace`."""
        return '~%s/%s' % (self.owner.name, self.sourcepackage.path)

    @property
    def target(self):
        """See `IBranchNamespace`."""
        return IBranchTarget(self.sourcepackage)

    def getAllowedInformationTypes(self, who=None):
        """See `IBranchNamespace`."""
        return PUBLIC_INFORMATION_TYPES

    def getDefaultInformationType(self, who=None):
        """See `IBranchNamespace`."""
        return InformationType.PUBLIC


class BranchNamespaceSet:
    """Only implementation of `IBranchNamespaceSet`."""

    def get(self, person, product=None, distroseries=None,
            sourcepackagename=None):
        """See `IBranchNamespaceSet`."""
        if product is not None:
            assert (distroseries is None and sourcepackagename is None), (
                "product implies no distroseries or sourcepackagename. "
                "Got %r, %r, %r."
                % (product, distroseries, sourcepackagename))
            return ProductNamespace(person, product)
        elif distroseries is not None:
            assert sourcepackagename is not None, (
                "distroseries implies sourcepackagename. Got %r, %r"
                % (distroseries, sourcepackagename))
            return PackageNamespace(
                person, SourcePackage(sourcepackagename, distroseries))
        else:
            return PersonalNamespace(person)

    def parse(self, namespace_name):
        """See `IBranchNamespaceSet`."""
        data = dict(
            person=None, product=None, distribution=None, distroseries=None,
            sourcepackagename=None)
        tokens = namespace_name.split('/')
        if len(tokens) == 2:
            data['person'] = tokens[0]
            data['product'] = tokens[1]
        elif len(tokens) == 4:
            data['person'] = tokens[0]
            data['distribution'] = tokens[1]
            data['distroseries'] = tokens[2]
            data['sourcepackagename'] = tokens[3]
        else:
            raise InvalidNamespace(namespace_name)
        if not data['person'].startswith('~'):
            raise InvalidNamespace(namespace_name)
        data['person'] = data['person'][1:]
        return data

    def lookup(self, namespace_name):
        """See `IBranchNamespaceSet`."""
        names = self.parse(namespace_name)
        return self.interpret(**names)

    def interpret(self, person=None, product=None, distribution=None,
                  distroseries=None, sourcepackagename=None):
        """See `IBranchNamespaceSet`."""
        names = dict(
            person=person, product=product, distribution=distribution,
            distroseries=distroseries, sourcepackagename=sourcepackagename)
        data = self._realize(names)
        return self.get(**data)

    def traverse(self, segments):
        """See `IBranchNamespaceSet`."""
        traversed_segments = []

        def get_next_segment():
            try:
                result = segments.next()
            except StopIteration:
                raise InvalidNamespace('/'.join(traversed_segments))
            if result is None:
                raise AssertionError("None segment passed to traverse()")
            traversed_segments.append(result)
            return result

        person_name = get_next_segment()
        person = self._findPerson(person_name)
        pillar_name = get_next_segment()
        pillar = self._findPillar(pillar_name)
        if pillar is None or IProduct.providedBy(pillar):
            namespace = self.get(person, product=pillar)
        else:
            distroseries_name = get_next_segment()
            distroseries = self._findDistroSeries(pillar, distroseries_name)
            sourcepackagename_name = get_next_segment()
            sourcepackagename = self._findSourcePackageName(
                sourcepackagename_name)
            namespace = self.get(
                person, distroseries=distroseries,
                sourcepackagename=sourcepackagename)
        branch_name = get_next_segment()
        return self._findOrRaise(
            NoSuchBranch, branch_name, namespace.getByName)

    def _findOrRaise(self, error, name, finder, *args):
        if name is None:
            return None
        args = list(args)
        args.append(name)
        result = finder(*args)
        if result is None:
            raise error(name)
        return result

    def _findPerson(self, person_name):
        return self._findOrRaise(
            NoSuchPerson, person_name, getUtility(IPersonSet).getByName)

    def _findPillar(self, pillar_name):
        """Find and return the pillar with the given name.

        If the given name is '+junk' or None, return None.

        :raise NoSuchProduct if there's no pillar with the given name or it is
            a project.
        """
        if pillar_name == '+junk':
            return None
        pillar = self._findOrRaise(
            NoSuchProduct, pillar_name, getUtility(IPillarNameSet).getByName)
        if IProjectGroup.providedBy(pillar):
            raise NoSuchProduct(pillar_name)
        return pillar

    def _findProduct(self, product_name):
        if product_name == '+junk':
            return None
        return self._findOrRaise(
            NoSuchProduct, product_name,
            getUtility(IProductSet).getByName)

    def _findDistribution(self, distribution_name):
        return self._findOrRaise(
            NoSuchDistribution, distribution_name,
            getUtility(IDistributionSet).getByName)

    def _findDistroSeries(self, distribution, distroseries_name):
        return self._findOrRaise(
            NoSuchDistroSeries, distroseries_name,
            getUtility(IDistroSeriesSet).queryByName, distribution)

    def _findSourcePackageName(self, sourcepackagename_name):
        return self._findOrRaise(
            NoSuchSourcePackageName, sourcepackagename_name,
            getUtility(ISourcePackageNameSet).queryByName)

    def _realize(self, names):
        """Turn a dict of object names into a dict of objects.

        Takes the results of `IBranchNamespaceSet.parse` and turns them into a
        dict where the values are Launchpad objects.
        """
        data = {}
        data['person'] = self._findPerson(names['person'])
        data['product'] = self._findProduct(names['product'])
        distribution = self._findDistribution(names['distribution'])
        data['distroseries'] = self._findDistroSeries(
            distribution, names['distroseries'])
        data['sourcepackagename'] = self._findSourcePackageName(
            names['sourcepackagename'])
        return data
