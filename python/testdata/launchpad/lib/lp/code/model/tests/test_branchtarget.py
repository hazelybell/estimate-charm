# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for branch contexts."""

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.enums import (
    BranchType,
    RevisionControlSystems,
    )
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codeimport import ICodeImport
from lp.code.model.branchtarget import (
    check_default_stacked_on,
    PackageBranchTarget,
    PersonBranchTarget,
    ProductBranchTarget,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import IPrimaryContext
from lp.testing import (
    person_logged_in,
    run_with_login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class BaseBranchTargetTests:

    def test_provides_IBranchTarget(self):
        self.assertProvides(self.target, IBranchTarget)

    def test_context(self):
        # IBranchTarget.context is the original object.
        self.assertEqual(self.original, self.target.context)

    def test_canonical_url(self):
        # The canonical URL of a branch target is the canonical url of its
        # context.
        self.assertEqual(
            canonical_url(self.original), canonical_url(self.target))

    def test_collection(self):
        # The collection attribute is an IBranchCollection containing all
        # branches related to the branch target.
        self.assertEqual(self.target.collection.getBranches().count(), 0)
        branch = self.makeBranchForTarget()
        branches = self.target.collection.getBranches(eager_load=False)
        self.assertEqual([branch], list(branches))

    def test_retargetBranch_packageBranch(self):
        # Retarget an existing package branch to this target.
        branch = self.factory.makePackageBranch()
        self.target._retargetBranch(removeSecurityProxy(branch))
        self.assertEqual(self.target, branch.target)

    def test_retargetBranch_productBranch(self):
        # Retarget an existing product branch to this target.
        branch = self.factory.makeProductBranch()
        self.target._retargetBranch(removeSecurityProxy(branch))
        self.assertEqual(self.target, branch.target)

    def test_retargetBranch_personalBranch(self):
        # Retarget an existing personal branch to this target.
        branch = self.factory.makePersonalBranch()
        self.target._retargetBranch(removeSecurityProxy(branch))
        self.assertEqual(self.target, branch.target)


class TestPackageBranchTarget(TestCaseWithFactory, BaseBranchTargetTests):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.original = self.factory.makeSourcePackage()
        self.target = PackageBranchTarget(self.original)

    def makeBranchForTarget(self):
        return self.factory.makePackageBranch(sourcepackage=self.original)

    def test_name(self):
        # The name of a package context is distro/series/sourcepackage
        self.assertEqual(self.original.path, self.target.name)

    def test_getNamespace(self):
        """Get namespace produces the correct namespace."""
        person = self.factory.makePerson()
        namespace = self.target.getNamespace(person)
        self.assertEqual(person, namespace.owner)
        self.assertEqual(self.original, namespace.sourcepackage)

    def test_adapter(self):
        target = IBranchTarget(self.original)
        self.assertIsInstance(target, PackageBranchTarget)

    def test_distrosourcepackage_adapter(self):
        # Adapting a distrosourcepackage will make a branch target with the
        # current series of the distro as the distroseries.
        distro = self.original.distribution
        distro_sourcepackage = distro.getSourcePackage(
            self.original.sourcepackagename)
        target = IBranchTarget(distro_sourcepackage)
        self.assertIsInstance(target, PackageBranchTarget)
        self.assertEqual(
            [distro, distro.currentseries],
            target.components[:2])
        self.assertEqual(
            self.original.sourcepackagename,
            target.components[2].sourcepackagename)

    def test_components(self):
        target = IBranchTarget(self.original)
        self.assertEqual(
            [self.original.distribution, self.original.distroseries,
             self.original],
            list(target.components))

    def test_default_stacked_on_branch(self):
        # The default stacked-on branch for a source package is the branch
        # linked to the release pocket of the current series of that package.
        target = IBranchTarget(self.original)
        development_package = self.original.development_version
        default_branch = self.factory.makePackageBranch(
            sourcepackage=development_package)
        removeSecurityProxy(default_branch).branchChanged(
            '', self.factory.getUniqueString(), None, None, None)
        registrant = development_package.distribution.owner
        with person_logged_in(registrant):
            development_package.setBranch(
                PackagePublishingPocket.RELEASE, default_branch,
                registrant)
        self.assertEqual(default_branch, target.default_stacked_on_branch)

    def test_supports_merge_proposals(self):
        # Package branches do support merge proposals.
        self.assertTrue(self.target.supports_merge_proposals)

    def test_supports_short_identites(self):
        # Package branches do support short bzr identites.
        self.assertTrue(self.target.supports_short_identites)

    def test_displayname(self):
        # The display name of a source package target is the display name of
        # the source package.
        target = IBranchTarget(self.original)
        self.assertEqual(self.original.displayname, target.displayname)

    def test_areBranchesMergeable_same_sourcepackage(self):
        # Branches of the same sourcepackage are mergeable.
        same_target = PackageBranchTarget(self.original)
        self.assertTrue(self.target.areBranchesMergeable(same_target))

    def test_areBranchesMergeable_same_sourcepackagename(self):
        # Branches with the same sourcepackagename are mergeable.
        sourcepackage = self.factory.makeSourcePackage(
            self.original.sourcepackagename)
        same_name = PackageBranchTarget(sourcepackage)
        self.assertTrue(self.target.areBranchesMergeable(same_name))

    def test_areBranchesMergeable_different_sourcepackage(self):
        # Package branches for a different sorucepackagename are not
        # mergeable.
        branch = self.factory.makePackageBranch()
        self.assertFalse(self.target.areBranchesMergeable(branch.target))

    def test_areBranchesMergeable_personal_branches(self):
        # Personal branches are not mergeable.
        branch = self.factory.makePersonalBranch()
        self.assertFalse(self.target.areBranchesMergeable(branch.target))

    def test_areBranchesMergeable_unlinked_product(self):
        # Product branches are not normally mergeable into package branches.
        branch = self.factory.makeProductBranch()
        self.assertFalse(self.target.areBranchesMergeable(branch.target))

    def test_areBranchesMergeable_linked_product(self):
        # Products that are linked to the packages are mergeable.
        branch = self.factory.makeProductBranch()
        # Link it up.
        self.original.setPackaging(
            branch.product.development_focus, branch.owner)
        self.assertTrue(self.target.areBranchesMergeable(branch.target))

    def test_default_merge_target(self):
        # The default merge target is official release branch.
        self.assertIs(None, self.target.default_merge_target)
        # Now create and link a branch.
        branch = self.factory.makePackageBranch(sourcepackage=self.original)
        with person_logged_in(self.original.distribution.owner):
            self.original.setBranch(
                PackagePublishingPocket.RELEASE, branch,
                self.original.distribution.owner)
        self.assertEqual(branch, self.target.default_merge_target)

    def test_supports_code_imports(self):
        self.assertTrue(self.target.supports_code_imports)

    def test_creating_code_import_succeeds(self):
        target_url = self.factory.getUniqueURL()
        branch_name = self.factory.getUniqueString("name-")
        owner = self.factory.makePerson()
        code_import = self.target.newCodeImport(
            owner, branch_name, RevisionControlSystems.GIT, url=target_url)
        code_import = removeSecurityProxy(code_import)
        self.assertProvides(code_import, ICodeImport)
        self.assertEqual(target_url, code_import.url)
        self.assertEqual(branch_name, code_import.branch.name)
        self.assertEqual(owner, code_import.registrant)
        self.assertEqual(owner, code_import.branch.owner)
        self.assertEqual(self.target, code_import.branch.target)

    def test_related_branches(self):
        (branch, related_series_branch_info,
            related_package_branches) = (
                self.factory.makeRelatedBranchesForSourcePackage(
                sourcepackage=self.original))
        self.assertEqual(
            related_series_branch_info,
            self.target.getRelatedSeriesBranchInfo(branch))
        self.assertEqual(
            related_package_branches,
            self.target.getRelatedPackageBranchInfo(branch))

    def test_related_branches_with_private_branch(self):
        (branch, related_series_branch_info,
            related_package_branches) = (
                self.factory.makeRelatedBranchesForSourcePackage(
                sourcepackage=self.original, with_private_branches=True))
        self.assertEqual(
            related_series_branch_info,
            self.target.getRelatedSeriesBranchInfo(branch))
        self.assertEqual(
            related_package_branches,
            self.target.getRelatedPackageBranchInfo(branch))


class TestPersonBranchTarget(TestCaseWithFactory, BaseBranchTargetTests):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.original = self.factory.makePerson()
        self.target = PersonBranchTarget(self.original)

    def makeBranchForTarget(self):
        return self.factory.makeBranch(owner=self.original, product=None)

    def test_name(self):
        # The name of a junk context is '+junk'.
        self.assertEqual('+junk', self.target.name)

    def test_getNamespace(self):
        """Get namespace produces the correct namespace."""
        namespace = self.target.getNamespace(self.original)
        self.assertEqual(namespace.owner, self.original)
        self.assertRaises(AttributeError, lambda: namespace.product)
        self.assertRaises(AttributeError, lambda: namespace.sourcepackage)

    def test_adapter(self):
        target = IBranchTarget(self.original)
        self.assertIsInstance(target, PersonBranchTarget)

    def test_components(self):
        target = IBranchTarget(self.original)
        self.assertEqual([self.original], list(target.components))

    def test_default_stacked_on_branch(self):
        # Junk branches are not stacked by default, ever.
        target = IBranchTarget(self.original)
        self.assertIs(None, target.default_stacked_on_branch)

    def test_supports_merge_proposals(self):
        # Personal branches do not support merge proposals.
        self.assertFalse(self.target.supports_merge_proposals)

    def test_supports_short_identites(self):
        # Personal branches do not support short bzr identites.
        self.assertFalse(self.target.supports_short_identites)

    def test_displayname(self):
        # The display name of a person branch target is ~$USER/+junk.
        target = IBranchTarget(self.original)
        self.assertEqual('~%s/+junk' % self.original.name, target.displayname)

    def test_areBranchesMergeable(self):
        # No branches are mergeable with a PersonBranchTarget.
        branch = self.factory.makeAnyBranch()
        self.assertFalse(self.target.areBranchesMergeable(branch.target))

    def test_default_merge_target(self):
        # The default merge target is always None.
        self.assertIs(None, self.target.default_merge_target)

    def test_retargetBranch_packageBranch(self):
        # Retarget an existing package branch to this target.  Override the
        # mixin tests, and specify the owner of the branch.  This is needed to
        # match the target as the target is the branch owner for a personal
        # branch.
        branch = self.factory.makePackageBranch(owner=self.original)
        self.target._retargetBranch(removeSecurityProxy(branch))
        self.assertEqual(self.target, branch.target)

    def test_retargetBranch_productBranch(self):
        # Retarget an existing product branch to this target.  Override the
        # mixin tests, and specify the owner of the branch.  This is needed to
        # match the target as the target is the branch owner for a personal
        # branch.
        branch = self.factory.makeProductBranch(owner=self.original)
        self.target._retargetBranch(removeSecurityProxy(branch))
        self.assertEqual(self.target, branch.target)

    def test_retargetBranch_personalBranch(self):
        # Retarget an existing personal branch to this target.  Override the
        # mixin tests, and specify the owner of the branch.  This is needed to
        # match the target as the target is the branch owner for a personal
        # branch.
        branch = self.factory.makePersonalBranch(owner=self.original)
        self.target._retargetBranch(removeSecurityProxy(branch))
        self.assertEqual(self.target, branch.target)

    def test_doesnt_support_code_imports(self):
        self.assertFalse(self.target.supports_code_imports)

    def test_creating_code_import_fails(self):
        self.assertRaises(
            AssertionError, self.target.newCodeImport,
                self.factory.makePerson(),
                self.factory.getUniqueString("name-"),
                RevisionControlSystems.GIT, url=self.factory.getUniqueURL())


class TestProductBranchTarget(TestCaseWithFactory, BaseBranchTargetTests):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.original = self.factory.makeProduct()
        self.target = ProductBranchTarget(self.original)

    def makeBranchForTarget(self):
        return self.factory.makeBranch(product=self.original)

    def test_name(self):
        self.assertEqual(self.original.name, self.target.name)

    def test_getNamespace(self):
        """Get namespace produces the correct namespace."""
        person = self.factory.makePerson()
        namespace = self.target.getNamespace(person)
        self.assertEqual(namespace.product, self.original)
        self.assertEqual(namespace.owner, person)

    def test_adapter(self):
        target = IBranchTarget(self.original)
        self.assertIsInstance(target, ProductBranchTarget)

    def test_productseries_adapter(self):
        # Adapting a product series will make a product branch target.
        product = self.factory.makeProduct()
        series = self.factory.makeProductSeries(product)
        target = IBranchTarget(series)
        self.assertIsInstance(target, ProductBranchTarget)
        self.assertEqual([product], target.components)

    def test_components(self):
        target = IBranchTarget(self.original)
        self.assertEqual([self.original], list(target.components))

    def test_default_stacked_on_branch_no_dev_focus(self):
        # The default stacked-on branch for a product target that has no
        # development focus is None.
        target = IBranchTarget(self.original)
        self.assertIs(None, target.default_stacked_on_branch)

    def _setDevelopmentFocus(self, product, branch):
        removeSecurityProxy(product).development_focus.branch = branch

    def test_default_stacked_on_branch_unmirrored_dev_focus(self):
        # If the development focus hasn't been mirrored, then don't use it as
        # the default stacked-on branch.
        branch = self.factory.makeProductBranch(product=self.original)
        self._setDevelopmentFocus(self.original, branch)
        target = IBranchTarget(self.original)
        self.assertIs(None, target.default_stacked_on_branch)

    def test_default_stacked_on_branch_has_been_mirrored(self):
        # If the development focus has been mirrored, then use it as the
        # default stacked-on branch.
        branch = self.factory.makeProductBranch(product=self.original)
        self._setDevelopmentFocus(self.original, branch)
        removeSecurityProxy(branch).branchChanged(
            '', 'rev1', None, None, None)
        target = IBranchTarget(self.original)
        self.assertEqual(branch, target.default_stacked_on_branch)

    def test_supports_merge_proposals(self):
        # Product branches do support merge proposals.
        self.assertTrue(self.target.supports_merge_proposals)

    def test_supports_short_identites(self):
        # Product branches do support short bzr identites.
        self.assertTrue(self.target.supports_short_identites)

    def test_displayname(self):
        # The display name of a product branch target is the display name of
        # the product.
        target = IBranchTarget(self.original)
        self.assertEqual(self.original.displayname, target.displayname)

    def test_areBranchesMergeable_same_product(self):
        # Branches of the same product are mergeable.
        same_target = ProductBranchTarget(self.original)
        self.assertTrue(self.target.areBranchesMergeable(same_target))

    def test_areBranchesMergeable_different_product(self):
        # Branches of a different product are not mergeable.
        other_target = ProductBranchTarget(self.factory.makeProduct())
        self.assertFalse(self.target.areBranchesMergeable(other_target))

    def test_areBranchesMergeable_personal_branches(self):
        # Personal branches are not mergeable.
        branch = self.factory.makePersonalBranch()
        self.assertFalse(self.target.areBranchesMergeable(branch.target))

    def test_areBranchesMergeable_unlinked_package(self):
        # Package branches are not normally mergeable into products.
        branch = self.factory.makePackageBranch()
        self.assertFalse(self.target.areBranchesMergeable(branch.target))

    def test_areBranchesMergeable_linked_package(self):
        # Packages that are linked to the products are mergeable.
        branch = self.factory.makePackageBranch()
        # Link it up.
        branch.sourcepackage.setPackaging(
            self.original.development_focus, branch.owner)
        self.assertTrue(self.target.areBranchesMergeable(branch.target))

    def test_default_merge_target(self):
        # The default merge target is the development focus branch.
        self.assertIs(None, self.target.default_merge_target)
        # Now create and link a branch.
        branch = self.factory.makeProductBranch(product=self.original)
        run_with_login(
            self.original.owner,
            setattr, self.original.development_focus, 'branch', branch)
        self.assertEqual(branch, self.target.default_merge_target)

    def test_supports_code_imports(self):
        self.assertTrue(self.target.supports_code_imports)

    def test_creating_code_import_succeeds(self):
        target_url = self.factory.getUniqueURL()
        branch_name = self.factory.getUniqueString("name-")
        owner = self.factory.makePerson()
        code_import = self.target.newCodeImport(
            owner, branch_name, RevisionControlSystems.GIT, url=target_url)
        code_import = removeSecurityProxy(code_import)
        self.assertProvides(code_import, ICodeImport)
        self.assertEqual(target_url, code_import.url)
        self.assertEqual(branch_name, code_import.branch.name)
        self.assertEqual(owner, code_import.registrant)
        self.assertEqual(owner, code_import.branch.owner)
        self.assertEqual(self.target, code_import.branch.target)

    def test_related_branches(self):
        (branch, related_series_branch_info,
            related_package_branches) = (
                self.factory.makeRelatedBranchesForProduct(
                product=self.original))
        self.assertEqual(
            related_series_branch_info,
            self.target.getRelatedSeriesBranchInfo(branch))
        self.assertEqual(
            related_package_branches,
            self.target.getRelatedPackageBranchInfo(branch))

    def test_related_branches_with_private_branch(self):
        (branch, related_series_branch_info,
            related_package_branches) = (
                self.factory.makeRelatedBranchesForProduct(
                product=self.original, with_private_branches=True))
        self.assertEqual(
            related_series_branch_info,
            self.target.getRelatedSeriesBranchInfo(branch))
        self.assertEqual(
            related_package_branches,
            self.target.getRelatedPackageBranchInfo(branch))

    def test_related_branches_with_limit(self):
        (branch, related_series_branch_info,
            related_package_branches) = (
                self.factory.makeRelatedBranchesForProduct(
                product=self.original))
        self.assertEqual(
            related_series_branch_info[:2],
            self.target.getRelatedSeriesBranchInfo(branch, 2))
        self.assertEqual(
            related_package_branches[:2],
            self.target.getRelatedPackageBranchInfo(branch, 2))


class TestCheckDefaultStackedOnBranch(TestCaseWithFactory):
    """Only certain branches are allowed to be default stacked-on branches."""

    layer = DatabaseFunctionalLayer

    def test_none(self):
        # `check_default_stacked_on` returns None if passed None.
        self.assertIs(None, check_default_stacked_on(None))

    def test_unmirrored(self):
        # `check_default_stacked_on` returns None if passed an unmirrored
        # banch. This is because we don't want to stack things on unmirrored
        # branches.
        branch = self.factory.makeAnyBranch()
        self.assertIs(None, check_default_stacked_on(branch))

    def test_remote(self):
        # `check_default_stacked_on` returns None if passed a remote branch.
        # We have no Bazaar data for remote branches, so stacking on one is
        # futile.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.REMOTE)
        self.assertIs(None, check_default_stacked_on(branch))

    def test_remote_thats_been_mirrored(self):
        # Although REMOTE branches are not generally ever mirrored, it's
        # possible for a branch to be turned into a REMOTE branch later in
        # life.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.startMirroring()
        removeSecurityProxy(branch).branchChanged(
            '', self.factory.getUniqueString(), None, None, None)
        removeSecurityProxy(branch).branch_type = BranchType.REMOTE
        self.assertIs(None, check_default_stacked_on(branch))

    def test_invisible(self):
        # `check_default_stacked_on` returns None for branches invisible to
        # the current user.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        self.assertIs(None, check_default_stacked_on(branch))

    def test_invisible_been_mirrored(self):
        # `check_default_stacked_on` returns None for branches invisible to
        # the current user, even if those branches have already been mirrored.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        naked_branch = removeSecurityProxy(branch)
        naked_branch.branchChanged(
            '', self.factory.getUniqueString(), None, None, None)
        self.assertIs(None, check_default_stacked_on(branch))

    def test_been_mirrored(self):
        # `check_default_stacked_on` returns the branch if it has revisions.
        branch = self.factory.makeAnyBranch()
        removeSecurityProxy(branch).branchChanged(
            '', self.factory.getUniqueString(), None, None, None)
        self.assertEqual(branch, check_default_stacked_on(branch))


class TestPrimaryContext(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_package_branch(self):
        branch = self.factory.makePackageBranch()
        self.assertEqual(branch.target, IPrimaryContext(branch))

    def test_personal_branch(self):
        branch = self.factory.makePersonalBranch()
        self.assertEqual(branch.target, IPrimaryContext(branch))

    def test_product_branch(self):
        branch = self.factory.makeProductBranch()
        self.assertEqual(branch.target, IPrimaryContext(branch))
