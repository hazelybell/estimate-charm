# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `IBranchNamespace` implementations."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import (
    FREE_INFORMATION_TYPES,
    InformationType,
    NON_EMBARGOED_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    )
from lp.app.interfaces.services import IService
from lp.app.validators import LaunchpadValidationError
from lp.code.enums import (
    BranchLifecycleStatus,
    BranchType,
    )
from lp.code.errors import (
    BranchCreatorNotMemberOfOwnerTeam,
    BranchCreatorNotOwner,
    BranchExists,
    InvalidNamespace,
    NoSuchBranch,
    )
from lp.code.interfaces.branchnamespace import (
    get_branch_namespace,
    IBranchNamespace,
    IBranchNamespacePolicy,
    IBranchNamespaceSet,
    lookup_branch_namespace,
    )
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.model.branchnamespace import (
    PackageNamespace,
    PersonalNamespace,
    ProductNamespace,
    )
from lp.registry.enums import (
    BranchSharingPolicy,
    PersonVisibility,
    SharingPermission,
    )
from lp.registry.errors import (
    NoSuchDistroSeries,
    NoSuchSourcePackageName,
    )
from lp.registry.interfaces.distribution import NoSuchDistribution
from lp.registry.interfaces.person import NoSuchPerson
from lp.registry.interfaces.product import NoSuchProduct
from lp.registry.model.sourcepackage import SourcePackage
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class NamespaceMixin:
    """Tests common to all namespace implementations.

    You might even call these 'interface tests'.
    """

    def test_provides_interface(self):
        # All branch namespaces provide IBranchNamespace.
        self.assertProvides(self.getNamespace(), IBranchNamespace)

    def test_getBranchName(self):
        # getBranchName returns the thing that would be the
        # IBranch.unique_name of a branch with that name in the namespace.
        namespace = self.getNamespace()
        branch_name = self.factory.getUniqueString()
        self.assertEqual(
            '%s/%s' % (namespace.name, branch_name),
            namespace.getBranchName(branch_name))

    def test_createBranch_right_namespace(self):
        # createBranch creates a branch in that namespace.
        namespace = self.getNamespace()
        branch_name = self.factory.getUniqueString()
        expected_unique_name = namespace.getBranchName(branch_name)
        registrant = removeSecurityProxy(namespace).owner
        branch = namespace.createBranch(
            BranchType.HOSTED, branch_name, registrant)
        self.assertEqual(
            expected_unique_name, branch.unique_name)
        self.assertEqual(InformationType.PUBLIC, branch.information_type)

    def test_createBranch_passes_through(self):
        # createBranch takes all the arguments that the `Branch` constructor
        # takes, except for the ones that define the namespace.
        namespace = self.getNamespace()
        branch_name = self.factory.getUniqueString()
        registrant = removeSecurityProxy(namespace).owner
        title = self.factory.getUniqueString()
        summary = self.factory.getUniqueString()
        whiteboard = self.factory.getUniqueString()
        branch = namespace.createBranch(
            BranchType.HOSTED, branch_name, registrant, url=None,
            title=title, lifecycle_status=BranchLifecycleStatus.EXPERIMENTAL,
            summary=summary, whiteboard=whiteboard)
        self.assertEqual(BranchType.HOSTED, branch.branch_type)
        self.assertEqual(branch_name, branch.name)
        self.assertEqual(registrant, branch.registrant)
        self.assertIs(None, branch.url)
        self.assertEqual(
            BranchLifecycleStatus.EXPERIMENTAL, branch.lifecycle_status)
        self.assertEqual(whiteboard, branch.whiteboard)

    def test_createBranch_subscribes_owner(self):
        owner = self.factory.makeTeam()
        namespace = self.getNamespace(owner)
        branch_name = self.factory.getUniqueString()
        registrant = owner.teamowner
        branch = namespace.createBranch(
            BranchType.HOSTED, branch_name, registrant)
        self.assertEqual([owner], list(branch.subscribers))

    def test_getBranches_no_branches(self):
        # getBranches on an IBranchNamespace returns a result set of branches
        # in that namespace. If there are no branches, the result set is
        # empty.
        namespace = self.getNamespace()
        self.assertEqual([], list(namespace.getBranches()))

    def test_getBranches_some_branches(self):
        # getBranches on an IBranchNamespace returns a result set of branches
        # in that namespace.
        namespace = self.getNamespace()
        branch_name = self.factory.getUniqueString()
        branch = namespace.createBranch(
            BranchType.HOSTED, branch_name,
            removeSecurityProxy(namespace).owner)
        self.assertEqual([branch], list(namespace.getBranches()))

    def test_getByName_default(self):
        # getByName returns the given default if there is no branch in the
        # namespace with that name.
        namespace = self.getNamespace()
        default = object()
        match = namespace.getByName(self.factory.getUniqueString(), default)
        self.assertIs(default, match)

    def test_getByName_default_is_none(self):
        # The default 'default' return value is None.
        namespace = self.getNamespace()
        match = namespace.getByName(self.factory.getUniqueString())
        self.assertIs(None, match)

    def test_getByName_matches(self):
        namespace = self.getNamespace()
        branch_name = self.factory.getUniqueString()
        branch = namespace.createBranch(
            BranchType.HOSTED, branch_name,
            removeSecurityProxy(namespace).owner)
        match = namespace.getByName(branch_name)
        self.assertEqual(branch, match)

    def test_isNameUsed_not(self):
        namespace = self.getNamespace()
        name = self.factory.getUniqueString()
        self.assertEqual(False, namespace.isNameUsed(name))

    def test_isNameUsed_yes(self):
        namespace = self.getNamespace()
        branch_name = self.factory.getUniqueString()
        namespace.createBranch(
            BranchType.HOSTED, branch_name,
            removeSecurityProxy(namespace).owner)
        self.assertEqual(True, namespace.isNameUsed(branch_name))

    def test_findUnusedName_unused(self):
        # findUnusedName returns the given name if that name is not used.
        namespace = self.getNamespace()
        name = self.factory.getUniqueString()
        unused_name = namespace.findUnusedName(name)
        self.assertEqual(name, unused_name)

    def test_findUnusedName_used(self):
        # findUnusedName returns the given name with a numeric suffix if its
        # already used.
        namespace = self.getNamespace()
        name = self.factory.getUniqueString()
        namespace.createBranch(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        unused_name = namespace.findUnusedName(name)
        self.assertEqual('%s-1' % name, unused_name)

    def test_findUnusedName_used_twice(self):
        # findUnusedName returns the given name with a numeric suffix if its
        # already used.
        namespace = self.getNamespace()
        name = self.factory.getUniqueString()
        namespace.createBranch(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        namespace.createBranch(
            BranchType.HOSTED, name + '-1',
            removeSecurityProxy(namespace).owner)
        unused_name = namespace.findUnusedName(name)
        self.assertEqual('%s-2' % name, unused_name)

    def test_createBranchWithPrefix_unused(self):
        # createBranch with prefix creates a branch with the same name as the
        # given prefix if there's no branch with that name already.
        namespace = self.getNamespace()
        name = self.factory.getUniqueString()
        branch = namespace.createBranchWithPrefix(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        self.assertEqual(name, branch.name)

    def test_createBranchWithPrefix_used(self):
        # createBranch with prefix creates a branch with the same name as the
        # given prefix if there's no branch with that name already.
        namespace = self.getNamespace()
        name = self.factory.getUniqueString()
        namespace.createBranch(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        branch = namespace.createBranchWithPrefix(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        self.assertEqual(name + '-1', branch.name)

    def test_validateMove(self):
        # If the mover is allowed to move the branch into the namespace, if
        # there are absolutely no problems at all, then validateMove raises
        # nothing and returns None.
        namespace = self.getNamespace()
        namespace_owner = removeSecurityProxy(namespace).owner
        branch = self.factory.makeAnyBranch()
        # Doesn't raise an exception.
        self.assertIs(None, namespace.validateMove(branch, namespace_owner))

    def test_validateMove_branch_with_name_exists(self):
        # If a branch with the same name as the given branch already exists in
        # the namespace, validateMove raises a BranchExists error.
        namespace = self.getNamespace()
        namespace_owner = removeSecurityProxy(namespace).owner
        name = self.factory.getUniqueString()
        namespace.createBranch(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        branch = self.factory.makeAnyBranch(name=name)
        self.assertRaises(
            BranchExists, namespace.validateMove, branch, namespace_owner)

    def test_validateMove_forbidden_owner(self):
        # If the mover isn't allowed to create branches in the namespace, then
        # they aren't allowed to move branches in there either, so
        # validateMove wil raise a BranchCreatorNotOwner error.
        namespace = self.getNamespace()
        branch = self.factory.makeAnyBranch()
        mover = self.factory.makePerson()
        self.assertRaises(
            BranchCreatorNotOwner, namespace.validateMove, branch, mover)

    def test_validateMove_not_team_member(self):
        # If the mover isn't allowed to create branches in the namespace
        # because they aren't a member of the team that owns the namespace,
        # validateMove raises a BranchCreatorNotMemberOfOwnerTeam error.
        team = self.factory.makeTeam()
        namespace = self.getNamespace(person=team)
        branch = self.factory.makeAnyBranch()
        mover = self.factory.makePerson()
        self.assertRaises(
            BranchCreatorNotMemberOfOwnerTeam,
            namespace.validateMove, branch, mover)

    def test_validateMove_with_other_name(self):
        # If you pass a name to validateMove, that'll check to see whether the
        # branch could be safely moved given a rename.
        namespace = self.getNamespace()
        namespace_owner = removeSecurityProxy(namespace).owner
        name = self.factory.getUniqueString()
        namespace.createBranch(
            BranchType.HOSTED, name, removeSecurityProxy(namespace).owner)
        branch = self.factory.makeAnyBranch()
        self.assertRaises(
            BranchExists, namespace.validateMove, branch, namespace_owner,
            name=name)


class TestPersonalNamespace(TestCaseWithFactory, NamespaceMixin):
    """Tests for `PersonalNamespace`."""

    layer = DatabaseFunctionalLayer

    def getNamespace(self, person=None):
        if person is None:
            person = self.factory.makePerson()
        return get_branch_namespace(person=person)

    def test_name(self):
        # A personal namespace has branches with names starting with
        # ~foo/+junk.
        person = self.factory.makePerson()
        namespace = PersonalNamespace(person)
        self.assertEqual('~%s/+junk' % person.name, namespace.name)

    def test_owner(self):
        # The person passed to a personal namespace is the owner.
        person = self.factory.makePerson()
        namespace = PersonalNamespace(person)
        self.assertEqual(person, removeSecurityProxy(namespace).owner)

    def test_target(self):
        # The target of a personal namespace is the branch target of the owner
        # of that namespace.
        person = self.factory.makePerson()
        namespace = PersonalNamespace(person)
        self.assertEqual(IBranchTarget(person), namespace.target)


class TestProductNamespace(TestCaseWithFactory, NamespaceMixin):
    """Tests for `ProductNamespace`."""

    layer = DatabaseFunctionalLayer

    def getNamespace(self, person=None):
        if person is None:
            person = self.factory.makePerson()
        return get_branch_namespace(
            person=person, product=self.factory.makeProduct())

    def test_name(self):
        # A product namespace has branches with names starting with ~foo/bar.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = ProductNamespace(person, product)
        self.assertEqual(
            '~%s/%s' % (person.name, product.name), namespace.name)

    def test_owner(self):
        # The person passed to a product namespace is the owner.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = ProductNamespace(person, product)
        self.assertEqual(person, removeSecurityProxy(namespace).owner)

    def test_target(self):
        # The target for a product namespace is the branch target of the
        # product.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = ProductNamespace(person, product)
        self.assertEqual(IBranchTarget(product), namespace.target)

    def test_validateMove_vcs_imports_rename_import_branch(self):
        # Members of ~vcs-imports can rename any imported branch.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        name = self.factory.getUniqueString()
        code_import = self.factory.makeCodeImport(
            registrant=owner, target=IBranchTarget(product), branch_name=name)
        branch = code_import.branch
        new_name = self.factory.getUniqueString()
        namespace = ProductNamespace(owner, product)
        with celebrity_logged_in('vcs_imports') as mover:
            self.assertIsNone(
                namespace.validateMove(branch, mover, name=new_name))

    def test_validateMove_vcs_imports_change_owner_import_branch(self):
        # Members of ~vcs-imports can change the owner any imported branch.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        code_import = self.factory.makeCodeImport(
            registrant=owner, target=IBranchTarget(product))
        branch = code_import.branch
        new_owner = self.factory.makePerson()
        new_namespace = ProductNamespace(new_owner, product)
        with celebrity_logged_in('vcs_imports') as mover:
            self.assertIsNone(new_namespace.validateMove(branch, mover))


class TestProductNamespacePrivacyWithInformationType(TestCaseWithFactory):
    """Tests for the privacy aspects of `ProductNamespace`.

    This tests the behaviour for a product using the new
    branch_sharing_policy rules.
    """

    layer = DatabaseFunctionalLayer

    def makeProductNamespace(self, sharing_policy, person=None):
        if person is None:
            person = self.factory.makePerson()
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product=product)
        with person_logged_in(product.owner):
            product.setBranchSharingPolicy(sharing_policy)
        namespace = ProductNamespace(person, product)
        return namespace

    def test_public_anyone(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PUBLIC)
        self.assertContentEqual(
            FREE_INFORMATION_TYPES, namespace.getAllowedInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC, namespace.getDefaultInformationType())

    def test_forbidden_anyone(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.FORBIDDEN)
        self.assertContentEqual([], namespace.getAllowedInformationTypes())
        self.assertEqual(None, namespace.getDefaultInformationType())

    def test_public_or_proprietary_anyone(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PUBLIC_OR_PROPRIETARY)
        self.assertContentEqual(
            NON_EMBARGOED_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC, namespace.getDefaultInformationType())

    def test_proprietary_or_public_anyone(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PROPRIETARY_OR_PUBLIC)
        self.assertContentEqual([], namespace.getAllowedInformationTypes())
        self.assertIs(None, namespace.getDefaultInformationType())

    def test_proprietary_or_public_owner_grantee(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PROPRIETARY_OR_PUBLIC)
        with person_logged_in(namespace.product.owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                namespace.product, namespace.owner, namespace.product.owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertContentEqual(
            NON_EMBARGOED_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes())
        self.assertEqual(
            InformationType.PROPRIETARY,
            namespace.getDefaultInformationType())

    def test_proprietary_or_public_caller_grantee(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PROPRIETARY_OR_PUBLIC)
        grantee = self.factory.makePerson()
        with person_logged_in(namespace.product.owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                namespace.product, grantee, namespace.product.owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertContentEqual(
            NON_EMBARGOED_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes(grantee))
        self.assertEqual(
            InformationType.PROPRIETARY,
            namespace.getDefaultInformationType(grantee))

    def test_proprietary_anyone(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PROPRIETARY)
        self.assertContentEqual([], namespace.getAllowedInformationTypes())
        self.assertIs(None, namespace.getDefaultInformationType())

    def test_proprietary_branch_owner_grantee(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PROPRIETARY)
        with person_logged_in(namespace.product.owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                namespace.product, namespace.owner, namespace.product.owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertContentEqual(
            [InformationType.PROPRIETARY],
            namespace.getAllowedInformationTypes())
        self.assertEqual(
            InformationType.PROPRIETARY,
            namespace.getDefaultInformationType())

    def test_proprietary_caller_grantee(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.PROPRIETARY)
        grantee = self.factory.makePerson()
        with person_logged_in(namespace.product.owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                namespace.product, grantee, namespace.product.owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertContentEqual(
            [InformationType.PROPRIETARY],
            namespace.getAllowedInformationTypes(grantee))
        self.assertEqual(
            InformationType.PROPRIETARY,
            namespace.getDefaultInformationType(grantee))

    def test_embargoed_or_proprietary_anyone(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY)
        self.assertContentEqual([], namespace.getAllowedInformationTypes())
        self.assertIs(None, namespace.getDefaultInformationType())

    def test_embargoed_or_proprietary_owner_grantee(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY)
        with person_logged_in(namespace.product.owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                namespace.product, namespace.owner, namespace.product.owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertContentEqual(
            [InformationType.PROPRIETARY, InformationType.EMBARGOED],
            namespace.getAllowedInformationTypes())
        self.assertEqual(
            InformationType.EMBARGOED,
            namespace.getDefaultInformationType())

    def test_embargoed_or_proprietary_caller_grantee(self):
        namespace = self.makeProductNamespace(
            BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY)
        grantee = self.factory.makePerson()
        with person_logged_in(namespace.product.owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                namespace.product, grantee, namespace.product.owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertContentEqual(
            [InformationType.PROPRIETARY, InformationType.EMBARGOED],
            namespace.getAllowedInformationTypes(grantee))
        self.assertEqual(
            InformationType.EMBARGOED,
            namespace.getDefaultInformationType(grantee))


class TestPackageNamespace(TestCaseWithFactory, NamespaceMixin):
    """Tests for `PackageNamespace`."""

    layer = DatabaseFunctionalLayer

    def getNamespace(self, person=None):
        if person is None:
            person = self.factory.makePerson()
        return get_branch_namespace(
            person=person,
            distroseries=self.factory.makeDistroSeries(),
            sourcepackagename=self.factory.makeSourcePackageName())

    def test_name(self):
        # A package namespace has branches that start with
        # ~foo/ubuntu/spicy/packagename.
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        namespace = PackageNamespace(
            person, SourcePackage(sourcepackagename, distroseries))
        self.assertEqual(
            '~%s/%s/%s/%s' % (
                person.name, distroseries.distribution.name,
                distroseries.name, sourcepackagename.name),
            namespace.name)

    def test_owner(self):
        # The person passed to a package namespace is the owner.
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        namespace = PackageNamespace(
            person, SourcePackage(sourcepackagename, distroseries))
        self.assertEqual(person, removeSecurityProxy(namespace).owner)

    def test_target(self):
        # The target for a package namespace is the branch target of the
        # sourcepackage.
        person = self.factory.makePerson()
        package = self.factory.makeSourcePackage()
        namespace = PackageNamespace(person, package)
        self.assertEqual(IBranchTarget(package), namespace.target)


class TestNamespaceSet(TestCaseWithFactory):
    """Tests for `get_namespace`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.namespace_set = getUtility(IBranchNamespaceSet)

    def test_get_personal(self):
        person = self.factory.makePerson()
        namespace = get_branch_namespace(person=person)
        self.assertIsInstance(namespace, PersonalNamespace)

    def test_get_product(self):
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = get_branch_namespace(person=person, product=product)
        self.assertIsInstance(namespace, ProductNamespace)

    def test_get_package(self):
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        namespace = get_branch_namespace(
            person=person, distroseries=distroseries,
            sourcepackagename=sourcepackagename)
        self.assertIsInstance(namespace, PackageNamespace)

    def test_lookup_personal(self):
        # lookup_branch_namespace returns a personal namespace if given a junk
        # path.
        person = self.factory.makePerson()
        namespace = lookup_branch_namespace('~%s/+junk' % person.name)
        self.assertIsInstance(namespace, PersonalNamespace)
        self.assertEqual(person, removeSecurityProxy(namespace).owner)

    def test_lookup_personal_not_found(self):
        # lookup_branch_namespace raises NoSuchPerson error if the given
        # person doesn't exist.
        self.assertRaises(
            NoSuchPerson, lookup_branch_namespace, '~no-such-person/+junk')

    def test_lookup_product(self):
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = lookup_branch_namespace(
            '~%s/%s' % (person.name, product.name))
        self.assertIsInstance(namespace, ProductNamespace)
        self.assertEqual(person, removeSecurityProxy(namespace).owner)
        self.assertEqual(product, removeSecurityProxy(namespace).product)

    def test_lookup_product_not_found(self):
        person = self.factory.makePerson()
        self.assertRaises(
            NoSuchProduct, lookup_branch_namespace,
            '~%s/no-such-product' % person.name)

    def test_lookup_package(self):
        person = self.factory.makePerson()
        sourcepackage = self.factory.makeSourcePackage()
        namespace = lookup_branch_namespace(
            '~%s/%s' % (person.name, sourcepackage.path))
        self.assertIsInstance(namespace, PackageNamespace)
        self.assertEqual(person, removeSecurityProxy(namespace).owner)
        namespace = removeSecurityProxy(namespace)
        self.assertEqual(sourcepackage, namespace.sourcepackage)

    def test_lookup_package_no_distribution(self):
        person = self.factory.makePerson()
        self.assertRaises(
            NoSuchDistribution, lookup_branch_namespace,
            '~%s/no-such-distro/whocares/whocares' % person.name)

    def test_lookup_package_no_distroseries(self):
        person = self.factory.makePerson()
        distribution = self.factory.makeDistribution()
        self.assertRaises(
            NoSuchDistroSeries, lookup_branch_namespace,
            '~%s/%s/no-such-series/whocares'
            % (person.name, distribution.name))

    def test_lookup_package_no_source_package(self):
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        self.assertRaises(
            NoSuchSourcePackageName, lookup_branch_namespace,
            '~%s/%s/%s/no-such-spn' % (
                person.name, distroseries.distribution.name,
                distroseries.name))

    def assertInvalidName(self, name):
        """Assert that 'name' is an invalid namespace name."""
        self.assertRaises(InvalidNamespace, self.namespace_set.parse, name)

    def test_lookup_invalid_name(self):
        # Namespace paths must start with a tilde. Thus, lookup will raise an
        # InvalidNamespace error if it is given a path without one.
        person = self.factory.makePerson()
        self.assertInvalidName(person.name)

    def test_lookup_short_name_person_only(self):
        # Given a path that only has a person in it, lookup will raise an
        # InvalidNamespace error.
        person = self.factory.makePerson()
        self.assertInvalidName('~' + person.name)

    def test_lookup_short_name_person_and_distro(self):
        # We can't tell the difference between ~user/distro,
        # ~user/no-such-product and ~user/no-such-distro, so we just raise
        # NoSuchProduct, which is perhaps the most common case.
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        self.assertRaises(
            NoSuchProduct, lookup_branch_namespace,
            '~%s/%s' % (person.name, distroseries.distribution.name))

    def test_lookup_short_name_distroseries(self):
        # Given a too-short path to a package branch namespace, lookup will
        # raise an InvalidNamespace error.
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        self.assertInvalidName(
            '~%s/%s/%s' % (
                person.name, distroseries.distribution.name,
                distroseries.name))

    def test_lookup_long_name_junk(self):
        # Given a too-long personal path, lookup will raise an
        # InvalidNamespace error.
        person = self.factory.makePerson()
        self.assertInvalidName('~%s/+junk/foo' % person.name)

    def test_lookup_long_name_product(self):
        # Given a too-long product path, lookup will raise an InvalidNamespace
        # error.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        self.assertInvalidName('~%s/%s/foo' % (person.name, product.name))

    def test_lookup_long_name_sourcepackage(self):
        # Given a too-long name, lookup will raise an InvalidNamespace error.
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        self.assertInvalidName(
            '~%s/%s/%s/%s/foo' % (
                person.name, distroseries.distribution.name,
                distroseries.name, sourcepackagename.name))

    def test_parse_junk_namespace(self):
        # parse takes a path to a personal (i.e. junk) branch namespace and
        # returns a dict that has the person field set but all others set to
        # None.
        self.assertEqual(
            dict(person='foo', product='+junk', distroseries=None,
                 distribution=None, sourcepackagename=None),
            self.namespace_set.parse('~foo/+junk'))

    def test_parse_product_namespace(self):
        # parse take a path to a product branch namespace and returns a dict
        # with the product set and the distro-related keys set to None.
        self.assertEqual(
            dict(person='foo', product='bar', distroseries=None,
                 distribution=None, sourcepackagename=None),
            self.namespace_set.parse('~foo/bar'))

    def test_parse_package_namespace(self):
        # parse takes a path to a package branch namespace and returns a dict
        # with the distro-related keys populated, and the product set to None.
        self.assertEqual(
            dict(person='foo', product=None, distribution='ubuntu',
                 distroseries='jaunty', sourcepackagename='foo'),
            self.namespace_set.parse('~foo/ubuntu/jaunty/foo'))

    def test_interpret_product_aliases(self):
        # Products can have aliases. IBranchNamespaceSet.interpret will find a
        # product given its alias.
        branch = self.factory.makeProductBranch()
        product_alias = self.factory.getUniqueString()
        removeSecurityProxy(branch.product).setAliases([product_alias])
        namespace = self.namespace_set.interpret(
            branch.owner.name, product=product_alias)
        self.assertEqual(
            branch.product, removeSecurityProxy(namespace).product)

    def _getSegments(self, branch):
        """Return an iterable of the branch name segments.

        Note that the person element is *not* proceeded by a tilde.
        """
        return iter(branch.unique_name[1:].split('/'))

    def test_traverse_junk_branch(self):
        # IBranchNamespaceSet.traverse returns a branch based on an iterable
        # of path segments, including junk branches.
        branch = self.factory.makePersonalBranch()
        segments = self._getSegments(branch)
        found_branch = self.namespace_set.traverse(segments)
        self.assertEqual(branch, found_branch)

    def test_traverse_junk_branch_not_found(self):
        person = self.factory.makePerson()
        segments = iter([person.name, '+junk', 'no-such-branch'])
        self.assertRaises(
            NoSuchBranch, self.namespace_set.traverse, segments)
        self.assertEqual([], list(segments))

    def test_traverse_person_not_found(self):
        segments = iter(['no-such-person', 'whatever'])
        self.assertRaises(
            NoSuchPerson, self.namespace_set.traverse, segments)
        self.assertEqual(['whatever'], list(segments))

    def test_traverse_product_branch(self):
        # IBranchNamespaceSet.traverse returns a branch based on an iterable
        # of path segments, including product branches.
        branch = self.factory.makeProductBranch()
        segments = self._getSegments(branch)
        found_branch = self.namespace_set.traverse(segments)
        self.assertEqual(branch, found_branch)

    def test_traverse_project_branch(self):
        # IBranchNamespaceSet.traverse raises NoSuchProduct if the product is
        # actually a project.
        person = self.factory.makePerson()
        project = self.factory.makeProject()
        segments = iter([person.name, project.name, 'branch'])
        self.assertRaises(
            NoSuchProduct, self.namespace_set.traverse, segments)

    def test_traverse_package_branch(self):
        # IBranchNamespaceSet.traverse returns a branch based on an iterable
        # of path segments, including package branches.
        branch = self.factory.makePackageBranch()
        segments = self._getSegments(branch)
        found_branch = self.namespace_set.traverse(segments)
        self.assertEqual(branch, found_branch)

    def test_traverse_product_not_found(self):
        # IBranchNamespaceSet.traverse raises NoSuchProduct if it cannot find
        # the product.
        person = self.factory.makePerson()
        segments = iter([person.name, 'no-such-product', 'branch'])
        self.assertRaises(
            NoSuchProduct, self.namespace_set.traverse, segments)
        self.assertEqual(['branch'], list(segments))

    def test_traverse_package_branch_aliases(self):
        # Distributions can have aliases. IBranchNamespaceSet.traverse will
        # find a branch where its distro is given as an alias.
        branch = self.factory.makePackageBranch()
        pillar_alias = self.factory.getUniqueString()
        removeSecurityProxy(branch.distribution).setAliases([pillar_alias])
        segments = iter([
            branch.owner.name, pillar_alias, branch.distroseries.name,
            branch.sourcepackagename.name, branch.name,
            ])
        found_branch = self.namespace_set.traverse(segments)
        self.assertEqual(branch, found_branch)

    def test_traverse_distribution_not_found(self):
        # IBranchNamespaceSet.traverse raises NoSuchProduct if it cannot find
        # the distribution. We do this since we can't tell the difference
        # between a non-existent product and a non-existent distro.
        person = self.factory.makePerson()
        segments = iter(
            [person.name, 'no-such-distro', 'jaunty', 'evolution', 'branch'])
        self.assertRaises(
            NoSuchProduct, self.namespace_set.traverse, segments)
        self.assertEqual(['jaunty', 'evolution', 'branch'], list(segments))

    def test_traverse_distroseries_not_found(self):
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution()
        segments = iter(
            [person.name, distro.name, 'no-such-series', 'package', 'branch'])
        self.assertRaises(
            NoSuchDistroSeries, self.namespace_set.traverse, segments)
        self.assertEqual(['package', 'branch'], list(segments))

    def test_traverse_sourcepackagename_not_found(self):
        person = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        distro = distroseries.distribution
        segments = iter(
            [person.name, distro.name, distroseries.name, 'no-such-package',
             'branch'])
        self.assertRaises(
            NoSuchSourcePackageName, self.namespace_set.traverse, segments)
        self.assertEqual(['branch'], list(segments))

    def test_traverse_leaves_trailing_segments(self):
        # traverse doesn't consume all the elements of the iterable. It only
        # consumes those it needs to find a branch.
        branch = self.factory.makeAnyBranch()
        trailing_segments = ['+foo', 'bar']
        segments = iter(branch.unique_name[1:].split('/') + trailing_segments)
        found_branch = self.namespace_set.traverse(segments)
        self.assertEqual(branch, found_branch)
        self.assertEqual(trailing_segments, list(segments))

    def test_too_few_segments(self):
        # If there aren't enough segments, raise InvalidNamespace.
        person = self.factory.makePerson()
        self.assertRaises(
            InvalidNamespace,
            self.namespace_set.traverse, iter([person.name]))

    def test_last_segment_none(self):
        # If the last name passed to traverse is None, raise an error (rather
        # than returning None).
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        self.assertRaises(
            AssertionError,
            self.namespace_set.traverse,
            iter([person.name, product.name, None]))


class BaseCanCreateBranchesMixin:
    """Common tests for all namespaces."""

    layer = DatabaseFunctionalLayer

    def _getNamespace(self, owner):
        # Return a namespace appropriate for the owner specified.
        raise NotImplementedError(self._getNamespace)

    def test_individual(self):
        # For a BranchTarget for an individual, only the individual can own
        # branches there.
        person = self.factory.makePerson()
        namespace = self._getNamespace(person)
        self.assertTrue(namespace.canCreateBranches(person))

    def test_other_user(self):
        # Any other individual cannot own branches targeted to the person.
        person = self.factory.makePerson()
        namespace = self._getNamespace(person)
        self.assertFalse(
            namespace.canCreateBranches(self.factory.makePerson()))

    def test_team_member(self):
        # A member of a team is able to create a branch on this namespace.
        # This is a team junk branch.
        person = self.factory.makePerson()
        self.factory.makeTeam(owner=person)
        namespace = self._getNamespace(person)
        self.assertTrue(namespace.canCreateBranches(person))

    def test_team_non_member(self):
        # A person who is not part of the team cannot create branches for the
        # personal team target.
        person = self.factory.makePerson()
        self.factory.makeTeam(owner=person)
        namespace = self._getNamespace(person)
        self.assertFalse(
            namespace.canCreateBranches(self.factory.makePerson()))


class TestPersonalNamespaceCanCreateBranches(TestCaseWithFactory,
                                             BaseCanCreateBranchesMixin):

    def _getNamespace(self, owner):
        return PersonalNamespace(owner)


class TestPackageNamespaceCanCreateBranches(TestCaseWithFactory,
                                            BaseCanCreateBranchesMixin):

    def _getNamespace(self, owner):
        source_package = self.factory.makeSourcePackage()
        return PackageNamespace(owner, source_package)


class TestProductNamespaceCanCreateBranches(TestCaseWithFactory,
                                            BaseCanCreateBranchesMixin):

    def _getNamespace(self, owner,
                      branch_sharing_policy=BranchSharingPolicy.PUBLIC):
        product = self.factory.makeProduct(
            branch_sharing_policy=branch_sharing_policy)
        return ProductNamespace(owner, product)

    def setUp(self):
        # Setting visibility policies is an admin only task.
        TestCaseWithFactory.setUp(self, 'admin@canonical.com')

    def test_any_person(self):
        # If there is no privacy set up, any person can create a personal
        # branch on the product.
        person = self.factory.makePerson()
        namespace = self._getNamespace(person, BranchSharingPolicy.PUBLIC)
        self.assertTrue(namespace.canCreateBranches(person))

    def test_any_person_with_proprietary_branches(self):
        # If the sharing policy defaults to PROPRIETARY, then
        # non-privileged users cannot create a branch.
        person = self.factory.makePerson()
        namespace = self._getNamespace(person, BranchSharingPolicy.PROPRIETARY)
        self.assertFalse(namespace.canCreateBranches(person))

    def test_grantee_with_proprietary_branches(self):
        # If the sharing policy defaults to PROPRIETARY, then
        # non-privileged users cannot create a branch.
        person = self.factory.makePerson()
        other_person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        namespace = self._getNamespace(team, BranchSharingPolicy.PROPRIETARY)
        getUtility(IService, 'sharing').sharePillarInformation(
            namespace.product, team, namespace.product.owner,
            {InformationType.PROPRIETARY: SharingPermission.ALL})
        self.assertTrue(namespace.canCreateBranches(person))
        self.assertFalse(namespace.canCreateBranches(other_person))


class TestPersonalNamespaceAllowedInformationTypes(TestCaseWithFactory):
    """Tests for PersonalNamespace.getAllowedInformationTypes."""

    layer = DatabaseFunctionalLayer

    def test_anyone(self):
        # +junk branches are not private for individuals
        person = self.factory.makePerson()
        namespace = PersonalNamespace(person)
        self.assertContentEqual(
            FREE_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes())

    def test_public_team(self):
        # +junk branches for public teams cannot be private
        team = self.factory.makeTeam()
        namespace = PersonalNamespace(team)
        self.assertContentEqual(
            FREE_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes())

    def test_private_team(self):
        # +junk branches can be private or public for private teams
        team = self.factory.makeTeam(visibility=PersonVisibility.PRIVATE)
        namespace = PersonalNamespace(team)
        self.assertContentEqual(
            NON_EMBARGOED_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes())


class TestPackageNamespaceAllowedInformationTypes(TestCaseWithFactory):
    """Tests for PackageNamespace.getAllowedInformationTypes."""

    layer = DatabaseFunctionalLayer

    def test_anyone(self):
        # Source package branches are always public.
        source_package = self.factory.makeSourcePackage()
        person = self.factory.makePerson()
        namespace = PackageNamespace(person, source_package)
        self.assertContentEqual(
            PUBLIC_INFORMATION_TYPES,
            namespace.getAllowedInformationTypes())


class BaseValidateNewBranchMixin:

    layer = DatabaseFunctionalLayer

    def _getNamespace(self, owner):
        # Return a namespace appropraite for the owner specified.
        raise NotImplementedError(self._getNamespace)

    def test_registrant_not_owner(self):
        # If the namespace owner is an individual, and the registrant is not
        # the owner, BranchCreatorNotOwner is raised.
        namespace = self._getNamespace(self.factory.makePerson())
        self.assertRaises(
            BranchCreatorNotOwner,
            namespace.validateRegistrant,
            self.factory.makePerson())

    def test_registrant_not_in_owner_team(self):
        # If the namespace owner is a team, and the registrant is not
        # in the team, BranchCreatorNotMemberOfOwnerTeam is raised.
        namespace = self._getNamespace(self.factory.makeTeam())
        self.assertRaises(
            BranchCreatorNotMemberOfOwnerTeam,
            namespace.validateRegistrant,
            self.factory.makePerson())

    def test_existing_branch(self):
        # If a branch exists with the same name, then BranchExists is raised.
        namespace = self._getNamespace(self.factory.makePerson())
        branch = namespace.createBranch(
            BranchType.HOSTED, self.factory.getUniqueString(),
            namespace.owner)
        self.assertRaises(
            BranchExists,
            namespace.validateBranchName,
            branch.name)

    def test_invalid_name(self):
        # If the branch name is not valid, a LaunchpadValidationError is
        # raised.
        namespace = self._getNamespace(self.factory.makePerson())
        self.assertRaises(
            LaunchpadValidationError,
            namespace.validateBranchName,
            '+foo')

    def test_permitted_first_character(self):
        # The first character of a branch name must be a letter or a number.
        namespace = self._getNamespace(self.factory.makePerson())
        for c in [chr(i) for i in range(128)]:
            if c.isalnum():
                namespace.validateBranchName(c)
            else:
                self.assertRaises(
                    LaunchpadValidationError,
                    namespace.validateBranchName, c)

    def test_permitted_subsequent_character(self):
        # After the first character, letters, numbers and certain punctuation
        # is permitted.
        namespace = self._getNamespace(self.factory.makePerson())
        for c in [chr(i) for i in range(128)]:
            if c.isalnum() or c in '+-_@.':
                namespace.validateBranchName('a' + c)
            else:
                self.assertRaises(
                    LaunchpadValidationError,
                    namespace.validateBranchName, 'a' + c)


class TestPersonalNamespaceValidateNewBranch(TestCaseWithFactory,
                                             BaseValidateNewBranchMixin):

    def _getNamespace(self, owner):
        return PersonalNamespace(owner)


class TestPackageNamespaceValidateNewBranch(TestCaseWithFactory,
                                            BaseValidateNewBranchMixin):

    def _getNamespace(self, owner):
        source_package = self.factory.makeSourcePackage()
        return PackageNamespace(owner, source_package)


class TestProductNamespaceValidateNewBranch(TestCaseWithFactory,
                                            BaseValidateNewBranchMixin):

    def _getNamespace(self, owner):
        product = self.factory.makeProduct()
        return ProductNamespace(owner, product)


class JunkBranches(TestCaseWithFactory):
    """Branches are considered junk if they have no associated product.
    It is the product that has the branch visibility policy, so junk branches
    have no related visibility policy."""

    layer = DatabaseFunctionalLayer

    def assertPublic(self, creator, owner):
        """Assert that the policy check would result in a public branch.

        :param creator: The user creating the branch.
        :param owner: The person or team that will be the owner of the branch.
        """
        namespace = get_branch_namespace(owner)
        self.assertNotIn(
            InformationType.PROPRIETARY,
            namespace.getAllowedInformationTypes())

    def assertPolicyCheckRaises(self, error, creator, owner):
        """Assert that the policy check raises an exception.

        :param error: The exception class that should be raised.
        :param creator: The user creating the branch.
        :param owner: The person or team that will be the owner of the branch.
        """
        policy = IBranchNamespacePolicy(get_branch_namespace(owner))
        self.assertRaises(
            error,
            policy.validateRegistrant,
            registrant=creator)

    def test_junk_branches_public(self):
        """Branches created by anyone that has no product defined are created
        as public branches.
        """
        person = self.factory.makePerson()
        self.assertPublic(person, person)

    def test_team_junk_branches(self):
        """Team junk branches are allowed, and are public."""
        person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        self.assertPublic(person, team)

    def test_no_create_junk_branch_for_other_user(self):
        """One user can't create +junk branches owned by another."""
        self.assertPolicyCheckRaises(
            BranchCreatorNotOwner, self.factory.makePerson(),
            self.factory.makePerson())


class TestBranchNamespaceMoveBranch(TestCaseWithFactory):
    """Test the IBranchNamespace.moveBranch method.

    The edge cases of the validateMove are tested in the NamespaceMixin for
    each of the namespaces.
    """

    layer = DatabaseFunctionalLayer

    def assertNamespacesEqual(self, expected, result):
        """Assert that the namespaces refer to the same thing.

        The name of the namespace contains the user name and the context
        parts, so is the easiest thing to check.
        """
        self.assertEqual(expected.name, result.name)

    def test_move_to_same_namespace(self):
        # Moving to the same namespace is effectively a no-op.  No exceptions
        # about matching branch names should be raised.
        branch = self.factory.makeAnyBranch()
        namespace = branch.namespace
        namespace.moveBranch(branch, branch.owner)
        self.assertNamespacesEqual(namespace, branch.namespace)

    def test_name_clash_raises(self):
        # A name clash will raise an exception.
        branch = self.factory.makeAnyBranch(name="test")
        another = self.factory.makeAnyBranch(owner=branch.owner, name="test")
        namespace = another.namespace
        self.assertRaises(
            BranchExists, namespace.moveBranch, branch, branch.owner)

    def test_move_with_rename(self):
        # A name clash with 'rename_if_necessary' set to True will cause the
        # branch to be renamed instead of raising an error.
        branch = self.factory.makeAnyBranch(name="test")
        another = self.factory.makeAnyBranch(owner=branch.owner, name="test")
        namespace = another.namespace
        namespace.moveBranch(branch, branch.owner, rename_if_necessary=True)
        self.assertEqual("test-1", branch.name)
        self.assertNamespacesEqual(namespace, branch.namespace)

    def test_move_with_new_name(self):
        # A new name for the branch can be specified as part of the move.
        branch = self.factory.makeAnyBranch(name="test")
        another = self.factory.makeAnyBranch(owner=branch.owner, name="test")
        namespace = another.namespace
        namespace.moveBranch(branch, branch.owner, new_name="foo")
        self.assertEqual("foo", branch.name)
        self.assertNamespacesEqual(namespace, branch.namespace)

    def test_sets_branch_owner(self):
        # Moving to a new namespace may change the owner of the branch if the
        # owner of the namespace is different.
        branch = self.factory.makeAnyBranch(name="test")
        team = self.factory.makeTeam(branch.owner)
        product = self.factory.makeProduct()
        namespace = ProductNamespace(team, product)
        namespace.moveBranch(branch, branch.owner)
        self.assertEqual(team, branch.owner)
        # And for paranoia.
        self.assertNamespacesEqual(namespace, branch.namespace)
