# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `TranslationPolicyMixin`."""

__metaclass__ = type

from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.testing import TestCaseWithFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.translationgroup import TranslationPermission
from lp.translations.interfaces.translationpolicy import ITranslationPolicy
from lp.translations.interfaces.translationsperson import ITranslationsPerson
from lp.translations.interfaces.translator import ITranslatorSet
from lp.translations.model.translationpolicy import TranslationPolicyMixin


class TranslationPolicyImplementation(TranslationPolicyMixin):
    """An `ITranslationPolicy` implementation for testing."""
    implements(ITranslationPolicy)

    translationgroup = None

    translationpermission = TranslationPermission.OPEN


class TestTranslationPolicy(TestCaseWithFactory):
    """Test `TranslationPolicyMixin`.

    :ivar policy: A `TranslationPolicyImplementation` for testing.
    """
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTranslationPolicy, self).setUp()
        self.policy = TranslationPolicyImplementation()

    def _makeParentPolicy(self):
        """Create a policy that `self.policy` inherits from."""
        parent = TranslationPolicyImplementation()
        self.policy.getInheritedTranslationPolicy = FakeMethod(result=parent)
        return parent

    def _makeTranslationGroups(self, count):
        """Return a list of `count` freshly minted `TranslationGroup`s."""
        return [
            self.factory.makeTranslationGroup() for number in xrange(count)]

    def _makeTranslator(self, language, for_policy=None):
        """Create a translator for a policy object.

        Default is `self.policy`.  Creates a translation group if necessary.
        """
        if for_policy is None:
            for_policy = self.policy
        if for_policy.translationgroup is None:
            for_policy.translationgroup = self.factory.makeTranslationGroup()
        person = self.factory.makePerson()
        getUtility(ITranslatorSet).new(
            for_policy.translationgroup, language, person, None)
        return person

    def _setPermissions(self, child_permission, parent_permission):
        """Set `TranslationPermission`s for `self.policy` and its parent."""
        self.policy.translationpermission = child_permission
        self.policy.getInheritedTranslationPolicy().translationpermission = (
            parent_permission)

    def test_hasSpecialTranslationPrivileges_for_regular_joe(self):
        # A logged-in user has no special translationprivileges by
        # default.
        joe = self.factory.makePerson()
        self.assertFalse(self.policy._hasSpecialTranslationPrivileges(joe))

    def test_hasSpecialTranslationPrivileges_for_admin(self):
        # Admins have special translation privileges.
        admin = self.factory.makePerson()
        getUtility(ILaunchpadCelebrities).admin.addMember(admin, admin)
        self.assertTrue(self.policy._hasSpecialTranslationPrivileges(admin))

    def test_hasSpecialTranslationPrivileges_for_translations_owner(self):
        # A policy may define a "translations owner" who also gets
        # special translation privileges.
        self.policy.isTranslationsOwner = FakeMethod(result=True)
        owner = self.factory.makePerson()
        self.assertTrue(self.policy._hasSpecialTranslationPrivileges(owner))

    def test_canTranslate(self):
        # A user who has declined the licensing agreement can't
        # translate.  Someone who has agreed, or not made a decision
        # yet, can.
        user = self.factory.makePerson()
        translations_user = ITranslationsPerson(user)

        self.assertTrue(self.policy._canTranslate(user))

        translations_user.translations_relicensing_agreement = True
        self.assertTrue(self.policy._canTranslate(user))

        translations_user.translations_relicensing_agreement = False
        self.assertFalse(self.policy._canTranslate(user))

    def test_getTranslationGroups_returns_translation_group(self):
        # In the simple case, getTranslationGroup simply returns the
        # policy implementation's translation group.
        self.assertEqual([], self.policy.getTranslationGroups())
        self.policy.translationgroup = self.factory.makeTranslationGroup()
        self.assertEqual(
            [self.policy.translationgroup],
            self.policy.getTranslationGroups())

    def test_getTranslationGroups_enumerates_groups_inherited_first(self):
        parent = self._makeParentPolicy()
        groups = self._makeTranslationGroups(2)
        parent.translationgroup = groups[0]
        self.policy.translationgroup = groups[1]
        self.assertEqual(groups, self.policy.getTranslationGroups())

    def test_getTranslationGroups_inheritance_is_asymmetric(self):
        parent = self._makeParentPolicy()
        groups = self._makeTranslationGroups(2)
        parent.translationgroup = groups[0]
        self.policy.translationgroup = groups[1]
        self.assertEqual(groups[:1], parent.getTranslationGroups())

    def test_getTranslationGroups_eliminates_duplicates(self):
        parent = self._makeParentPolicy()
        groups = self._makeTranslationGroups(1)
        parent.translationgroup = groups[0]
        self.policy.translationgroup = groups[0]
        self.assertEqual(groups, self.policy.getTranslationGroups())

    def test_getTranslators_without_groups_returns_empty_list(self):
        language = self.factory.makeLanguage()
        self.assertEqual([], self.policy.getTranslators(language))

    def test_getTranslators_returns_group_even_without_translators(self):
        self.policy.translationgroup = self.factory.makeTranslationGroup()
        self.assertEqual(
            [(self.policy.translationgroup, None, None)],
            self.policy.getTranslators(self.factory.makeLanguage()))

    def test_getTranslators_returns_translator(self):
        language = self.factory.makeLanguage()
        language_translator = self._makeTranslator(language)
        translators = self.policy.getTranslators(language)
        self.assertEqual(1, len(translators))
        group, translator, person = translators[0]
        self.assertEqual(self.policy.translationgroup, group)
        self.assertEqual(
            self.policy.translationgroup, translator.translationgroup)
        self.assertEqual(person, translator.translator)
        self.assertEqual(language, translator.language)
        self.assertEqual(language_translator, person)

    def test_getEffectiveTranslationPermission_returns_permission(self):
        # In the basic case, getEffectiveTranslationPermission just
        # returns the policy's translation permission.
        self.policy.translationpermission = TranslationPermission.CLOSED
        self.assertEqual(
            self.policy.translationpermission,
            self.policy.getEffectiveTranslationPermission())

    def test_getEffectiveTranslationPermission_returns_maximum(self):
        # When combining permissions, getEffectiveTranslationPermission
        # returns the one with the highest numerical value.
        parent = self._makeParentPolicy()
        for child_permission in TranslationPermission.items:
            for parent_permission in TranslationPermission.items:
                self._setPermissions(child_permission, parent_permission)
                stricter = max(child_permission, parent_permission)
                self.assertEqual(
                    stricter, self.policy.getEffectiveTranslationPermission())

    def test_maximum_permission_is_strictest(self):
        # The TranslationPermissions are ordered from loosest to
        # strictest, so the maximum is always the strictest.
        self.assertEqual(TranslationPermission.STRUCTURED, max(
            TranslationPermission.OPEN, TranslationPermission.STRUCTURED))
        self.assertEqual(TranslationPermission.RESTRICTED, max(
            TranslationPermission.STRUCTURED,
            TranslationPermission.RESTRICTED))
        self.assertEqual(TranslationPermission.CLOSED, max(
            TranslationPermission.RESTRICTED,
            TranslationPermission.CLOSED))

    def test_nobodies_stay_out(self):
        # We neither allow nor invite suggestions or edits by anonymous
        # users.
        language = self.factory.makeLanguage()
        self.assertFalse(self.policy.invitesTranslationEdits(None, language))
        self.assertFalse(
            self.policy.invitesTranslationSuggestions(None, language))
        self.assertFalse(self.policy.allowsTranslationEdits(None, language))
        self.assertFalse(
            self.policy.allowsTranslationSuggestions(None, language))

    def test_privileged_users_allowed_but_not_invited(self):
        # Specially privileged users such as administrators and
        # "translations owners" can enter suggestions and edit
        # translations, but are not particularly invited to do so.
        owner = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationpermission = TranslationPermission.CLOSED
        self.policy.isTranslationsOwner = FakeMethod(result=True)
        self.assertFalse(self.policy.invitesTranslationEdits(owner, language))
        self.assertFalse(
            self.policy.invitesTranslationSuggestions(owner, language))
        self.assertTrue(self.policy.allowsTranslationEdits(owner, language))
        self.assertTrue(
            self.policy.allowsTranslationSuggestions(owner, language))

    def test_open_invites_anyone(self):
        # The OPEN model invites anyone to enter suggestions or even
        # edit translations.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationpermission = TranslationPermission.OPEN
        self.assertTrue(self.policy.invitesTranslationEdits(joe, language))
        self.assertTrue(
            self.policy.invitesTranslationSuggestions(joe, language))

    def test_translation_team_members_are_invited(self):
        # Members of a translation team are invited (and thus allowed)
        # to enter suggestions for or edit translations covered by the
        # translation team.
        language = self.factory.makeLanguage()
        translator = self._makeTranslator(language)
        for permission in TranslationPermission.items:
            self.policy.translationpermission = permission
            self.assertTrue(
                self.policy.invitesTranslationEdits(translator, language))
            self.assertTrue(
                self.policy.invitesTranslationSuggestions(
                    translator, language))

    def test_structured_is_open_for_untended_translations(self):
        # Without a translation team, STRUCTURED is like OPEN.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationpermission = TranslationPermission.STRUCTURED
        self.assertTrue(self.policy.invitesTranslationEdits(joe, language))
        self.assertTrue(
            self.policy.invitesTranslationSuggestions(joe, language))

    def test_restricted_is_closed_for_untended_translations(self):
        # Without a translation team, RESTRICTED is like CLOSED.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationpermission = TranslationPermission.RESTRICTED
        self.assertFalse(self.policy.invitesTranslationEdits(joe, language))
        self.assertFalse(
            self.policy.invitesTranslationSuggestions(joe, language))

    def test_structured_and_restricted_for_tended_translations(self):
        # If there's a translation team, STRUCTURED and RESTRICTED both
        # invite suggestions (but not editing) by non-members.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self._makeTranslator(language)
        intermediate_permissions = [
            TranslationPermission.STRUCTURED,
            TranslationPermission.RESTRICTED,
            ]
        for permission in intermediate_permissions:
            self.policy.translationpermission = permission
            self.assertFalse(
                self.policy.invitesTranslationEdits(joe, language))
            self.assertTrue(
                self.policy.invitesTranslationSuggestions(joe, language))

    def test_closed_invites_nobody_for_untended_translations(self):
        # The CLOSED model does not invite anyone for untended
        # translations.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationpermission = TranslationPermission.CLOSED

        self.assertFalse(self.policy.invitesTranslationEdits(joe, language))
        self.assertFalse(
            self.policy.invitesTranslationSuggestions(joe, language))

    def test_closed_does_not_invite_nonmembers_for_tended_translations(self):
        # The CLOSED model invites nobody outside the translation team.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self._makeTranslator(language)
        self.policy.translationpermission = TranslationPermission.CLOSED

        self.assertFalse(self.policy.invitesTranslationEdits(joe, language))
        self.assertFalse(
            self.policy.invitesTranslationSuggestions(joe, language))

    def test_untended_translation_means_no_team(self):
        # A translation is "untended" if there is no translation team,
        # even if there is a translation group.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationpermission = TranslationPermission.RESTRICTED

        self.assertFalse(
            self.policy.invitesTranslationSuggestions(joe, language))
        self.policy.translationgroup = self.factory.makeTranslationGroup()
        self.assertFalse(
            self.policy.invitesTranslationSuggestions(joe, language))

    def test_translation_can_be_tended_by_empty_team(self):
        # A translation that has an empty translation team is tended.
        joe = self.factory.makePerson()
        language = self.factory.makeLanguage()
        self.policy.translationgroup = self.factory.makeTranslationGroup()
        getUtility(ITranslatorSet).new(
            self.policy.translationgroup, language, self.factory.makeTeam(),
            None)
        self.policy.translationpermission = TranslationPermission.RESTRICTED

        self.assertTrue(
            self.policy.invitesTranslationSuggestions(joe, language))


class TestTranslationsOwners(TestCaseWithFactory):
    """Who exactly are "translations owners"?

    :ivar owner: A `Person` to be used as an owner of various things.
    """
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTranslationsOwners, self).setUp()
        self.owner = self.factory.makePerson()

    def isTranslationsOwnerOf(self, pillar):
        """Is `self.owner` a translations owner of `pillar`?"""
        return removeSecurityProxy(pillar).isTranslationsOwner(self.owner)

    def test_product_owners(self):
        # Product owners are "translations owners."
        product = self.factory.makeProduct(owner=self.owner)
        self.assertTrue(self.isTranslationsOwnerOf(product))

    def test_projectgroup_owners(self):
        # ProjectGroup owners are not translations owners.
        project = self.factory.makeProject(owner=self.owner)
        self.assertFalse(self.isTranslationsOwnerOf(project))

    def test_distribution_owners(self):
        # Distribution owners are not translations owners.
        distro = self.factory.makeDistribution(owner=self.owner)
        self.assertFalse(self.isTranslationsOwnerOf(distro))

    def test_product_translationgroup_owners(self):
        # Translation group owners are not translations owners in the
        # case of Products.
        group = self.factory.makeTranslationGroup(owner=self.owner)
        product = self.factory.makeProject()
        product.translationgroup = group
        self.assertFalse(self.isTranslationsOwnerOf(product))

    def test_distro_translationgroup_owners(self):
        # Translation group owners are not translations owners in the
        # case of Distributions.
        group = self.factory.makeTranslationGroup(owner=self.owner)
        distro = self.factory.makeDistribution()
        distro.translationgroup = group
        self.assertFalse(self.isTranslationsOwnerOf(distro))


class TestSharingPolicy(TestCaseWithFactory):
    """Test `ITranslationPolicy`'s sharing between Ubuntu and upstream."""
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestSharingPolicy, self).setUp()
        self.user = self.factory.makePerson()
        self.language = self.factory.makeLanguage()

    def _doesPackageShare(self, sourcepackage, by_maintainer=False):
        """Does this `SourcePackage` share with upstream?"""
        distro = sourcepackage.distroseries.distribution
        return distro.sharesTranslationsWithOtherSide(
            self.user, self.language, sourcepackage=sourcepackage,
            purportedly_upstream=by_maintainer)

    def test_product_always_shares(self):
        product = self.factory.makeProduct()
        self.assertTrue(
            product.sharesTranslationsWithOtherSide(self.user, self.language))

    def _makePackageAndProductSeries(self):
        package = self.factory.makeSourcePackage()
        self.factory.makePackagingLink(
            sourcepackagename=package.sourcepackagename,
            distroseries=package.distroseries)
        return (package, package.productseries)

    def test_distribution_shares_only_if_invited_with_template(self):
        # With an upstream template, translations will be shared if the
        # product invites edits.
        package, productseries = self._makePackageAndProductSeries()
        product = productseries.product
        self.factory.makePOTemplate(productseries=productseries)

        product.translationpermission = TranslationPermission.OPEN
        self.assertTrue(self._doesPackageShare(package))
        product.translationpermission = TranslationPermission.CLOSED
        self.assertFalse(self._doesPackageShare(package))

    def test_distribution_shares_not_without_template(self):
        # Without an upstream template, translations will not be shared
        # if they do not originate from uploads done by the maintainer.
        package, productseries = self._makePackageAndProductSeries()
        product = productseries.product

        product.translationpermission = TranslationPermission.OPEN
        self.assertFalse(self._doesPackageShare(package))
        product.translationpermission = TranslationPermission.CLOSED
        self.assertFalse(self._doesPackageShare(package))

    def test_distribution_shares_only_by_maintainer_without_template(self):
        # Without an upstream template, translations will be shared
        # if they do originate from uploads done by the maintainer.
        package, productseries = self._makePackageAndProductSeries()
        product = productseries.product

        product.translationpermission = TranslationPermission.OPEN
        self.assertTrue(self._doesPackageShare(package, by_maintainer=True))
        product.translationpermission = TranslationPermission.CLOSED
        self.assertTrue(self._doesPackageShare(package, by_maintainer=True))

    def test_distribution_shares_only_by_maintainer_without_upstream(self):
        # Without an upstream product series, translations will only be
        # shared if they do originate from uploads done by the maintainer.
        package = self.factory.makeSourcePackage()
        for by_maintainer in [False, True]:
            self.assertEqual(
                by_maintainer, self._doesPackageShare(package, by_maintainer))
