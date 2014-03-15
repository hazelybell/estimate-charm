# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the translation permissions model."""

__metaclass__ = type

from zope.component import getUtility

from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.translationgroup import TranslationPermission
from lp.translations.interfaces.translator import ITranslatorSet

# A user can be translating either a translation that's not covered by a
# translation team ("untended"), or one that is ("tended"), or one whose
# translation team the user is a member of ("member").
team_coverage = [
    'untended',
    'tended',
    'member',
    ]


class PrivilegeLevel:
    """What is a given user allowed to do with a given translation?"""
    NOTHING = 'Nothing'
    SUGGEST = 'Suggest only'
    EDIT = 'Edit'

    _level_mapping = {
        (False, False): NOTHING,
        (False, True): SUGGEST,
        (True, True): EDIT,
    }

    @classmethod
    def check(cls, pofile, user):
        """Return privilege level that `user` has on `pofile`."""
        can_edit = pofile.canEditTranslations(user)
        can_suggest = pofile.canAddSuggestions(user)
        return cls._level_mapping[can_edit, can_suggest]


permissions_model = {
    (TranslationPermission.OPEN, 'untended'): PrivilegeLevel.EDIT,
    (TranslationPermission.OPEN, 'tended'): PrivilegeLevel.EDIT,
    (TranslationPermission.OPEN, 'member'): PrivilegeLevel.EDIT,
    (TranslationPermission.STRUCTURED, 'untended'): PrivilegeLevel.EDIT,
    (TranslationPermission.STRUCTURED, 'tended'): PrivilegeLevel.SUGGEST,
    (TranslationPermission.STRUCTURED, 'member'): PrivilegeLevel.EDIT,
    (TranslationPermission.RESTRICTED, 'untended'): PrivilegeLevel.NOTHING,
    (TranslationPermission.RESTRICTED, 'tended'): PrivilegeLevel.SUGGEST,
    (TranslationPermission.RESTRICTED, 'member'): PrivilegeLevel.EDIT,
    (TranslationPermission.CLOSED, 'untended'): PrivilegeLevel.NOTHING,
    (TranslationPermission.CLOSED, 'tended'): PrivilegeLevel.NOTHING,
    (TranslationPermission.CLOSED, 'member'): PrivilegeLevel.EDIT,
}


def combine_permissions(product):
    """Return the effective translation permission for `product`.

    This combines the translation permissions for `product` and
    `product.project`.
    """
    return max(
        product.project.translationpermission, product.translationpermission)


class TestTranslationPermission(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def makeProductInProjectGroup(self):
        """Create a `Product` that's in a `ProjectGroup`."""
        project = self.factory.makeProject()
        return self.factory.makeProduct(project=project)

    def closeTranslations(self, product):
        """Set translation permissions for `product` to Closed.

        If `product` is part of a project group, the project group's
        translation permissions are set to Closed as well.

        This is useful for showing that a particular person has
        rights to work on a translation despite it being generally
        closed to the public.
        """
        product.translationpermission = TranslationPermission.CLOSED
        if product.project is not None:
            product.project.translationpermission = (
                TranslationPermission.CLOSED)

    def makePOTemplateForProduct(self, product):
        """Create a `POTemplate` for a given `Product`."""
        return self.factory.makePOTemplate(
            productseries=self.factory.makeProductSeries(product=product))

    def makePOFileForProduct(self, product):
        """Create a `POFile` for a given `Product`."""
        return self.factory.makePOFile(
            potemplate=self.makePOTemplateForProduct(product))

    def makeTranslationTeam(self, group, language, members=None):
        """Create a translation team containing `person`.

        If `members` is None, a member will be created.
        """
        if members is None:
            members = [self.factory.makePerson()]
        team = self.factory.makeTeam(members=members)
        getUtility(ITranslatorSet).new(group, language, team)
        return team

    def makePOFilesForCoverageLevels(self, product, user):
        """Map each `team_coverage` level to a matching `POFile`.

        Produces a dict mapping containing one `POFile` for each
        coverage level:
         * 'untended' maps to a `POFile` not covered by a translation
           team.
         * 'tended' maps to a `POFile` covered by a translation team
           that `user` is not a member of.
         * 'member' maps to a `POFile` covered by a translation team
           that `user` is a member of.

        All `POFile`s are for the same `POTemplate`, on `product`.
        """
        potemplate = self.makePOTemplateForProduct(product)
        group = self.factory.makeTranslationGroup()
        potemplate.productseries.product.translationgroup = group
        pofiles = dict(
            (coverage, self.factory.makePOFile(potemplate=potemplate))
            for coverage in team_coverage)
        self.makeTranslationTeam(group, pofiles['tended'].language)
        self.makeTranslationTeam(
            group, pofiles['member'].language, members=[user])
        return pofiles

    def assertPrivilege(self, permission, coverage, privilege_level):
        """Assert that `privilege_level` is as the model says it should be."""
        self.assertEqual(
            permissions_model[permission, coverage],
            privilege_level,
            "Wrong privileges for %s with translation team coverage '%s'." % (
                permission.name, coverage))

    def test_translationgroup_models(self):
        # Test that a translation group bestows the expected privilege
        # level to a user for each possible combination of
        # TranslationPermission, existence of a translation team, and
        # the user's membership of a translation team.
        user = self.factory.makePerson()
        product = self.factory.makeProduct()
        pofiles = self.makePOFilesForCoverageLevels(product, user)
        for permission in TranslationPermission.items:
            product.translationpermission = permission
            for coverage in team_coverage:
                pofile = pofiles[coverage]
                privilege_level = PrivilegeLevel.check(pofile, user)
                self.assertPrivilege(permission, coverage, privilege_level)

    def test_translationgroupless_models(self):
        # In the absence of a translation group, translation models
        # behave as if there were a group that did not cover any
        # languages (and which no user is ever a member of).
        user = self.factory.makePerson()
        pofile = self.factory.makePOFile()
        product = pofile.potemplate.productseries.product
        for permission in TranslationPermission.items:
            product.translationpermission = permission
            privilege_level = PrivilegeLevel.check(pofile, user)
            self.assertPrivilege(permission, 'untended', privilege_level)

    def test_projectgroup_stands_in_for_product(self):
        # If a Product has no translation group but its project group
        # does, the project group's translation group applies.
        product = self.makeProductInProjectGroup()
        self.closeTranslations(product)
        user = self.factory.makePerson()
        group = self.factory.makeTranslationGroup()
        product.project.translationgroup = group
        pofile = self.makePOFileForProduct(product)
        getUtility(ITranslatorSet).new(group, pofile.language, user)

        self.assertTrue(pofile.canEditTranslations(user))

    def test_projectgroup_and_product_combine_translation_teams(self):
        # If a Product with a translation group is in a project group
        # that also has a translation group, the product's translation
        # teams are effectively the unions of the two translation
        # groups' respective teams.
        product = self.makeProductInProjectGroup()
        self.closeTranslations(product)
        pofile = self.makePOFileForProduct(product)
        product_translator = self.factory.makePerson()
        project_translator = self.factory.makePerson()
        product.project.translationgroup = self.factory.makeTranslationGroup()
        product.translationgroup = self.factory.makeTranslationGroup()
        self.makeTranslationTeam(
            product.project.translationgroup, pofile.language,
            [project_translator])
        self.makeTranslationTeam(
            product.translationgroup, pofile.language, [product_translator])

        # Both the translator from the project group's translation team
        # and the one from the product's translation team have edit
        # privileges on the translation.
        self.assertTrue(pofile.canEditTranslations(project_translator))
        self.assertTrue(pofile.canEditTranslations(product_translator))

    def test_projectgroup_and_product_permissions_combine(self):
        # If a product is in a project group, each has a translation
        # permission.  The two are combined to produce a single
        # effective permission.
        product = self.makeProductInProjectGroup()
        user = self.factory.makePerson()
        pofiles = self.makePOFilesForCoverageLevels(product, user)
        for project_permission in TranslationPermission.items:
            product.project.translationpermission = project_permission
            for product_permission in TranslationPermission.items:
                product.translationpermission = product_permission
                effective_permission = combine_permissions(product)

                for coverage in team_coverage:
                    pofile = pofiles[coverage]
                    privilege_level = PrivilegeLevel.check(pofile, user)
                    self.assertPrivilege(
                        effective_permission, coverage, privilege_level)

    def test_combine_permissions_yields_strictest(self):
        # Combining the translation permissions of a product and its
        # project group yields the strictest of the two.
        product = self.makeProductInProjectGroup()

        # The expected combined permission for each combination of
        # project-group and product permissions.
        combinations = {
            TranslationPermission.OPEN: {
                TranslationPermission.OPEN: TranslationPermission.OPEN,
                TranslationPermission.STRUCTURED:
                    TranslationPermission.STRUCTURED,
                TranslationPermission.RESTRICTED:
                    TranslationPermission.RESTRICTED,
                TranslationPermission.CLOSED: TranslationPermission.CLOSED,
            },
            TranslationPermission.STRUCTURED: {
                TranslationPermission.OPEN: TranslationPermission.STRUCTURED,
                TranslationPermission.STRUCTURED:
                    TranslationPermission.STRUCTURED,
                TranslationPermission.RESTRICTED:
                    TranslationPermission.RESTRICTED,
                TranslationPermission.CLOSED: TranslationPermission.CLOSED,
            },
            TranslationPermission.RESTRICTED: {
                TranslationPermission.OPEN: TranslationPermission.RESTRICTED,
                TranslationPermission.STRUCTURED:
                    TranslationPermission.RESTRICTED,
                TranslationPermission.RESTRICTED:
                    TranslationPermission.RESTRICTED,
                TranslationPermission.CLOSED: TranslationPermission.CLOSED,
            },
            TranslationPermission.CLOSED: {
                TranslationPermission.OPEN: TranslationPermission.CLOSED,
                TranslationPermission.STRUCTURED:
                    TranslationPermission.CLOSED,
                TranslationPermission.RESTRICTED:
                    TranslationPermission.CLOSED,
                TranslationPermission.CLOSED: TranslationPermission.CLOSED,
            },
        }

        # The strictest of Open and something else is always the
        # something else.
        for project_permission in TranslationPermission.items:
            product.project.translationpermission = project_permission
            for product_permission in TranslationPermission.items:
                product.translationpermission = product_permission
                expected_permission = (
                    combinations[project_permission][product_permission])
                self.assertEqual(
                    expected_permission, combine_permissions(product))
