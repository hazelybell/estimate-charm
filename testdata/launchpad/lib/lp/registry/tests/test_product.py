# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from cStringIO import StringIO
from datetime import (
    datetime,
    timedelta,
    )

import pytz
from storm.locals import Store
from testtools.matchers import MatchesAll
from testtools.testcase import ExpectedException
import transaction
from zope.component import getUtility
from zope.lifecycleevent.interfaces import IObjectModifiedEvent
from zope.security.checker import (
    CheckerPublic,
    getChecker,
    )
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.answers.interfaces.faqtarget import IFAQTarget
from lp.app.enums import (
    FREE_INFORMATION_TYPES,
    InformationType,
    PROPRIETARY_INFORMATION_TYPES,
    PUBLIC_PROPRIETARY_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.app.errors import ServiceUsageForbidden
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.launchpad import (
    IHasIcon,
    IHasLogo,
    IHasMugshot,
    ILaunchpadCelebrities,
    ILaunchpadUsage,
    IServiceUsage,
    )
from lp.app.interfaces.services import IService
from lp.blueprints.enums import (
    NewSpecificationDefinitionStatus,
    SpecificationDefinitionStatus,
    SpecificationFilter,
    SpecificationImplementationStatus,
    SpecificationPriority,
    SpecificationSort,
    )
from lp.blueprints.model.specification import (
    SPECIFICATION_POLICY_ALLOWED_TYPES,
    )
from lp.bugs.interfaces.bugsummary import IBugSummaryDimension
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.bugs.interfaces.bugtarget import BUG_POLICY_ALLOWED_TYPES
from lp.code.model.branchnamespace import BRANCH_POLICY_ALLOWED_TYPES
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    SharingPermission,
    SpecificationSharingPolicy,
    TeamMembershipPolicy,
    )
from lp.registry.errors import (
    CannotChangeInformationType,
    CommercialSubscribersOnly,
    InclusiveTeamLinkageError,
    ProprietaryProduct,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessPolicyGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.oopsreferences import IHasOOPSReferences
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    License,
    valid_sourceforge_project_name,
    )
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.product import (
    Product,
    ProductSet,
    UnDeactivateable,
    )
from lp.registry.model.productlicense import ProductLicense
from lp.services.database.interfaces import IStore
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.escaping import html_escape
from lp.testing import (
    celebrity_logged_in,
    login,
    person_logged_in,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    WebServiceTestCase,
    )
from lp.testing.event import TestEventListener
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.matchers import (
    DoesNotSnapshot,
    Provides,
    )
from lp.testing.pages import (
    find_main_content,
    get_feedback_messages,
    setupBrowser,
    )
from lp.translations.enums import TranslationPermission
from lp.translations.interfaces.customlanguagecode import (
    IHasCustomLanguageCodes,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )


class ValidationTestCase(TestCase):
    """Test IProduct validators."""

    def test_valid_sourceforge_project_name(self):
        self.assertTrue(valid_sourceforge_project_name('mailman'))
        self.assertTrue(valid_sourceforge_project_name('hop-2-hop'))
        self.assertTrue(valid_sourceforge_project_name('mailman3'))
        self.assertFalse(valid_sourceforge_project_name('1mailman'))
        self.assertFalse(valid_sourceforge_project_name('-mailman'))
        self.assertFalse(valid_sourceforge_project_name('mailman-'))

    def test_valid_sourceforge_project_name_length(self):
        self.assertFalse(valid_sourceforge_project_name('x' * 0))
        self.assertTrue(valid_sourceforge_project_name('x' * 1))
        self.assertTrue(valid_sourceforge_project_name('x' * 63))
        self.assertFalse(valid_sourceforge_project_name('x' * 64))


class TestProduct(TestCaseWithFactory):
    """Tests product object."""

    layer = LaunchpadFunctionalLayer

    def test_pillar_category(self):
        # Products are really called Projects
        product = self.factory.makeProduct()
        self.assertEqual("Project", product.pillar_category)

    def test_implements_interfaces(self):
        # Product fully implements its interfaces.
        product = removeSecurityProxy(self.factory.makeProduct())
        expected_interfaces = [
            IProduct,
            IBugSummaryDimension,
            IFAQTarget,
            IHasBugSupervisor,
            IHasCustomLanguageCodes,
            IHasIcon,
            IHasLogo,
            IHasMugshot,
            IHasOOPSReferences,
            IInformationType,
            ILaunchpadUsage,
            IServiceUsage,
            ]
        provides_all = MatchesAll(*map(Provides, expected_interfaces))
        self.assertThat(product, provides_all)

    def test_deactivation_failure(self):
        # Ensure that a product cannot be deactivated if
        # it is linked to source packages.
        login('admin@canonical.com')
        product = self.factory.makeProduct()
        source_package = self.factory.makeSourcePackage()
        self.assertEqual(True, product.active)
        source_package.setPackaging(
            product.development_focus, self.factory.makePerson())
        self.assertRaises(
            UnDeactivateable,
            setattr, product, 'active', False)

    def test_deactivation_success(self):
        # Ensure that a product can be deactivated if
        # it is not linked to source packages.
        login('admin@canonical.com')
        product = self.factory.makeProduct()
        self.assertEqual(True, product.active)
        product.active = False
        self.assertEqual(False, product.active)

    def test_milestone_sorting_getMilestonesAndReleases(self):
        product = self.factory.makeProduct()
        series = self.factory.makeProductSeries(product=product)
        milestone_0_1 = self.factory.makeMilestone(
            product=product,
            productseries=series,
            name='0.1')
        milestone_0_2 = self.factory.makeMilestone(
            product=product,
            productseries=series,
            name='0.2')
        release_1 = self.factory.makeProductRelease(
            product=product,
            milestone=milestone_0_1)
        release_2 = self.factory.makeProductRelease(
            product=product,
            milestone=milestone_0_2)
        expected = [(milestone_0_2, release_2), (milestone_0_1, release_1)]
        self.assertEqual(
            expected,
            list(product.getMilestonesAndReleases()))

    def test_getTimeline_limit(self):
        # Only 20 milestones/releases per series should be included in the
        # getTimeline() results. The results are sorted by
        # descending dateexpected and name, so the presumed latest
        # milestones should be included.
        product = self.factory.makeProduct(name='foo')
        for i in range(25):
            self.factory.makeMilestone(
                product=product,
                productseries=product.development_focus,
                name=str(i))

        # 0 through 4 should not be in the list.
        expected_milestones = [
            '/foo/+milestone/24',
            '/foo/+milestone/23',
            '/foo/+milestone/22',
            '/foo/+milestone/21',
            '/foo/+milestone/20',
            '/foo/+milestone/19',
            '/foo/+milestone/18',
            '/foo/+milestone/17',
            '/foo/+milestone/16',
            '/foo/+milestone/15',
            '/foo/+milestone/14',
            '/foo/+milestone/13',
            '/foo/+milestone/12',
            '/foo/+milestone/11',
            '/foo/+milestone/10',
            '/foo/+milestone/9',
            '/foo/+milestone/8',
            '/foo/+milestone/7',
            '/foo/+milestone/6',
            '/foo/+milestone/5',
            ]

        [series] = product.getTimeline()
        timeline_milestones = [
            landmark['uri']
            for landmark in series.landmarks]
        self.assertEqual(
            expected_milestones,
            timeline_milestones)

    def test_getVersionSortedSeries(self):
        # The product series should be sorted with the development focus
        # series first, the series starting with a number in descending
        # order, and then the series starting with a letter in
        # descending order.
        product = self.factory.makeProduct()
        for name in ('1', '2', '3', '3a', '3b', 'alpha', 'beta'):
            self.factory.makeProductSeries(product=product, name=name)
        self.assertEqual(
            [u'trunk', u'3b', u'3a', u'3', u'2', u'1', u'beta', u'alpha'],
            [series.name for series in product.getVersionSortedSeries()])

    def test_getVersionSortedSeries_with_specific_statuses(self):
        # The obsolete series should be included in the results if
        # statuses=[SeriesStatus.OBSOLETE]. The development focus will
        # also be included since it does not get filtered.
        login('admin@canonical.com')
        product = self.factory.makeProduct()
        self.factory.makeProductSeries(
            product=product, name='frozen-series')
        obsolete_series = self.factory.makeProductSeries(
            product=product, name='obsolete-series')
        obsolete_series.status = SeriesStatus.OBSOLETE
        active_series = product.getVersionSortedSeries(
            statuses=[SeriesStatus.OBSOLETE])
        self.assertEqual(
            [u'trunk', u'obsolete-series'],
            [series.name for series in active_series])

    def test_getVersionSortedSeries_without_specific_statuses(self):
        # The obsolete series should not be included in the results if
        # filter_statuses=[SeriesStatus.OBSOLETE]. The development focus will
        # always be included since it does not get filtered.
        login('admin@canonical.com')
        product = self.factory.makeProduct()
        self.factory.makeProductSeries(product=product, name='active-series')
        obsolete_series = self.factory.makeProductSeries(
            product=product, name='obsolete-series')
        obsolete_series.status = SeriesStatus.OBSOLETE
        product.development_focus.status = SeriesStatus.OBSOLETE
        active_series = product.getVersionSortedSeries(
            filter_statuses=[SeriesStatus.OBSOLETE])
        self.assertEqual(
            [u'trunk', u'active-series'],
            [series.name for series in active_series])

    def test_owner_cannot_be_open_team(self):
        """Product owners cannot be open teams."""
        for policy in INCLUSIVE_TEAM_POLICY:
            open_team = self.factory.makeTeam(membership_policy=policy)
            self.assertRaises(
                InclusiveTeamLinkageError, self.factory.makeProduct,
                owner=open_team)

    def test_owner_can_be_closed_team(self):
        """Product owners can be exclusive teams."""
        for policy in EXCLUSIVE_TEAM_POLICY:
            closed_team = self.factory.makeTeam(membership_policy=policy)
            self.factory.makeProduct(owner=closed_team)

    def test_product_creation_grants_maintainer_access(self):
        # Creating a new product creates an access grant for the maintainer
        # for all default policies.
        owner = self.factory.makePerson()
        product = getUtility(IProductSet).createProduct(
            owner, 'carrot', 'Carrot', 'Carrot', 'testing',
            licenses=[License.MIT])
        policies = getUtility(IAccessPolicySource).findByPillar((product,))
        grants = getUtility(IAccessPolicyGrantSource).findByPolicy(policies)
        expected_grantess = set([product.owner])
        grantees = set([grant.grantee for grant in grants])
        self.assertEqual(expected_grantess, grantees)

    def test_open_product_creation_sharing_policies(self):
        # Creating a new open (non-proprietary) product sets the bug and
        # branch sharing polices to public, and creates policies if required.
        owner = self.factory.makePerson()
        with person_logged_in(owner):
            product = getUtility(IProductSet).createProduct(
                owner, 'carrot', 'Carrot', 'Carrot', 'testing',
                licenses=[License.MIT])
        self.assertEqual(BugSharingPolicy.PUBLIC, product.bug_sharing_policy)
        self.assertEqual(
            BranchSharingPolicy.PUBLIC, product.branch_sharing_policy)
        self.assertEqual(
            SpecificationSharingPolicy.PUBLIC,
            product.specification_sharing_policy)
        aps = getUtility(IAccessPolicySource).findByPillar([product])
        expected = [
            InformationType.USERDATA, InformationType.PRIVATESECURITY]
        self.assertContentEqual(expected, [policy.type for policy in aps])

    def test_proprietary_product_creation_sharing_policies(self):
        # Creating a new proprietary product sets the bug, branch, and
        # specification sharing polices to proprietary.
        owner = self.factory.makePerson()
        with person_logged_in(owner):
            product = getUtility(IProductSet).createProduct(
                owner, 'carrot', 'Carrot', 'Carrot', 'testing',
                licenses=[License.OTHER_PROPRIETARY],
                information_type=InformationType.PROPRIETARY)
            self.assertEqual(
                BugSharingPolicy.PROPRIETARY, product.bug_sharing_policy)
            self.assertEqual(
                BranchSharingPolicy.PROPRIETARY, product.branch_sharing_policy)
            self.assertEqual(
                SpecificationSharingPolicy.PROPRIETARY,
                product.specification_sharing_policy)
        aps = getUtility(IAccessPolicySource).findByPillar([product])
        expected = [InformationType.PROPRIETARY]
        self.assertContentEqual(expected, [policy.type for policy in aps])

    def test_embargoed_product_creation_sharing_policies(self):
        # Creating a new embargoed product sets the branch and
        # specification sharing polices to embargoed or proprietary, and the
        # bug sharing policy to proprietary.
        owner = self.factory.makePerson()
        with person_logged_in(owner):
            product = getUtility(IProductSet).createProduct(
                owner, 'carrot', 'Carrot', 'Carrot', 'testing',
                licenses=[License.OTHER_PROPRIETARY],
                information_type=InformationType.EMBARGOED)
            self.assertEqual(
                BugSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                product.bug_sharing_policy)
            self.assertEqual(
                BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                product.branch_sharing_policy)
            self.assertEqual(
                SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                product.specification_sharing_policy)
        aps = getUtility(IAccessPolicySource).findByPillar([product])
        expected = [InformationType.PROPRIETARY, InformationType.EMBARGOED]
        self.assertContentEqual(expected, [policy.type for policy in aps])

    def test_other_proprietary_product_creation_sharing_policies(self):
        # Creating a new product with other/proprietary license leaves bug
        # and branch sharing polices at their default.
        owner = self.factory.makePerson()
        with person_logged_in(owner):
            product = getUtility(IProductSet).createProduct(
                owner, 'carrot', 'Carrot', 'Carrot', 'testing',
                licenses=[License.OTHER_PROPRIETARY])
            self.assertEqual(
                BugSharingPolicy.PUBLIC, product.bug_sharing_policy)
            self.assertEqual(
                BranchSharingPolicy.PUBLIC, product.branch_sharing_policy)
        aps = getUtility(IAccessPolicySource).findByPillar([product])
        expected = [InformationType.USERDATA, InformationType.PRIVATESECURITY]
        self.assertContentEqual(expected, [policy.type for policy in aps])

    def test_change_info_type_proprietary_check_artifacts(self):
        # Cannot change product information_type if any artifacts are public.
        spec_policy = SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY],
            specification_sharing_policy=spec_policy,
            bug_sharing_policy=BugSharingPolicy.PUBLIC_OR_PROPRIETARY,
            branch_sharing_policy=BranchSharingPolicy.PUBLIC_OR_PROPRIETARY,
        )
        self.useContext(person_logged_in(product.owner))
        spec = self.factory.makeSpecification(product=product)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with ExpectedException(
                CannotChangeInformationType, 'Some blueprints are public.'):
                product.information_type = info_type
        spec.transitionToInformationType(
            InformationType.PROPRIETARY, product.owner)
        bug = self.factory.makeBug(target=product)
        for bug_info_type in FREE_INFORMATION_TYPES:
            bug.transitionToInformationType(bug_info_type, product.owner)
            for info_type in PROPRIETARY_INFORMATION_TYPES:
                with ExpectedException(
                    CannotChangeInformationType,
                    'Some bugs are neither proprietary nor embargoed.'):
                    product.information_type = info_type
        bug.transitionToInformationType(InformationType.PROPRIETARY,
                                        product.owner)
        branch = self.factory.makeBranch(product=product)
        for branch_info_type in FREE_INFORMATION_TYPES:
            branch.transitionToInformationType(branch_info_type,
                                               product.owner)
            for info_type in PROPRIETARY_INFORMATION_TYPES:
                with ExpectedException(
                    CannotChangeInformationType,
                    'Some branches are neither proprietary nor embargoed.'):
                    product.information_type = info_type
        branch.transitionToInformationType(InformationType.PROPRIETARY,
                                           product.owner)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            product.information_type = info_type

    def test_change_info_type_proprietary_check_translations(self):
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        with person_logged_in(product.owner):
            for usage in ServiceUsage:
                product.information_type = InformationType.PUBLIC
                product.translations_usage = usage.value
                for info_type in PROPRIETARY_INFORMATION_TYPES:
                    if product.translations_usage == ServiceUsage.LAUNCHPAD:
                        with ExpectedException(
                            CannotChangeInformationType,
                            'Translations are enabled.'):
                            product.information_type = info_type
                    else:
                        product.information_type = info_type

    def test_change_info_type_proprietary_sets_policies(self):
        # Changing information type from public to proprietary sets the
        # appropriate policies
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            product.information_type = InformationType.PROPRIETARY
            self.assertEqual(
                BranchSharingPolicy.PROPRIETARY, product.branch_sharing_policy)
            self.assertEqual(
                BugSharingPolicy.PROPRIETARY, product.bug_sharing_policy)
            self.assertEqual(
                SpecificationSharingPolicy.PROPRIETARY,
                product.specification_sharing_policy)

    def test_change_info_type_embargoed_sets_policies(self):
        # Changing information type from public to embargoed sets the
        # appropriate policies
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            product.information_type = InformationType.EMBARGOED
            self.assertEqual(
                BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                product.branch_sharing_policy)
            self.assertEqual(
                BugSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                product.bug_sharing_policy)
            self.assertEqual(
                SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY,
                product.specification_sharing_policy)

    def test_proprietary_to_public_leaves_policies(self):
        # Changing information type from public leaves sharing policies
        # unchanged.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY, owner=owner)
        with person_logged_in(owner):
            product.information_type = InformationType.PUBLIC
            # Setting information type to the current type should be a no-op
            product.information_type = InformationType.PUBLIC
        self.assertEqual(
            BranchSharingPolicy.PROPRIETARY, product.branch_sharing_policy)
        self.assertEqual(
            BugSharingPolicy.PROPRIETARY, product.bug_sharing_policy)
        self.assertEqual(
            SpecificationSharingPolicy.PROPRIETARY,
            product.specification_sharing_policy)

    def test_checkInformationType_bug_supervisor(self):
        # Bug supervisors of proprietary products must not have inclusive
        # membership policies.
        team = self.factory.makeTeam()
        product = self.factory.makeProduct(bug_supervisor=team)
        for policy in (token.value for token in TeamMembershipPolicy):
            with person_logged_in(team.teamowner):
                team.membership_policy = policy
            for info_type in PROPRIETARY_INFORMATION_TYPES:
                with person_logged_in(product.owner):
                    errors = list(product.checkInformationType(info_type))
                if policy in EXCLUSIVE_TEAM_POLICY:
                    self.assertEqual([], errors)
                else:
                    with ExpectedException(
                        CannotChangeInformationType,
                        'Bug supervisor has inclusive membership.'):
                        raise errors[0]

    def test_checkInformationType_questions(self):
        # Proprietary products must not have questions
        product = self.factory.makeProduct()
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with person_logged_in(product.owner):
                self.assertEqual([],
                    list(product.checkInformationType(info_type)))
        self.factory.makeQuestion(target=product)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with person_logged_in(product.owner):
                error, = list(product.checkInformationType(info_type))
            with ExpectedException(CannotChangeInformationType,
                                   'This project has questions.'):
                raise error

    def test_checkInformationType_translations(self):
        # Proprietary products must not have translations
        productseries = self.factory.makeProductSeries()
        product = productseries.product
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with person_logged_in(product.owner):
                self.assertEqual([],
                    list(product.checkInformationType(info_type)))
        self.factory.makePOTemplate(productseries=productseries)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with person_logged_in(product.owner):
                error, = list(product.checkInformationType(info_type))
            with ExpectedException(CannotChangeInformationType,
                                   'This project has translations.'):
                raise error

    def test_checkInformationType_queued_translations(self):
        # Proprietary products must not have queued translations
        productseries = self.factory.makeProductSeries()
        product = productseries.product
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=productseries)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with person_logged_in(product.owner):
                error, = list(product.checkInformationType(info_type))
            with ExpectedException(CannotChangeInformationType,
                                   'This project has queued translations.'):
                raise error
        removeSecurityProxy(entry).delete(entry.id)
        with person_logged_in(product.owner):
            for info_type in PROPRIETARY_INFORMATION_TYPES:
                self.assertContentEqual(
                    [], product.checkInformationType(info_type))

    def test_checkInformationType_auto_translation_imports(self):
        # Proprietary products must not be at risk of creating translations.
        productseries = self.factory.makeProductSeries()
        product = productseries.product
        self.useContext(person_logged_in(product.owner))
        for mode in TranslationsBranchImportMode.items:
            if mode == TranslationsBranchImportMode.NO_IMPORT:
                continue
            productseries.translations_autoimport_mode = mode
            for info_type in PROPRIETARY_INFORMATION_TYPES:
                error, = list(product.checkInformationType(info_type))
                with ExpectedException(CannotChangeInformationType,
                    'Some product series have translation imports enabled.'):
                    raise error
        productseries.translations_autoimport_mode = (
            TranslationsBranchImportMode.NO_IMPORT)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            self.assertContentEqual(
                [], product.checkInformationType(info_type))

    def test_private_forbids_translations(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        self.useContext(person_logged_in(owner))
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            product.information_type = info_type
            with ExpectedException(
                ProprietaryProduct,
                "Translations are not supported for proprietary products."):
                product.translations_usage = ServiceUsage.LAUNCHPAD
            for usage in ServiceUsage.items:
                if usage == ServiceUsage.LAUNCHPAD:
                    continue
                product.translations_usage = usage

    def createProduct(self, information_type=None, license=None):
        # convenience method for testing IProductSet.createProduct rather than
        # self.factory.makeProduct
        owner = self.factory.makePerson()
        kwargs = {}
        if information_type is not None:
            kwargs['information_type'] = information_type
        if license is not None:
            kwargs['licenses'] = [license]
        with person_logged_in(owner):
            return getUtility(IProductSet).createProduct(
                owner, self.factory.getUniqueString('product'),
                'Fnord', 'Fnord', 'test 1', 'test 2', **kwargs)

    def test_product_information_type(self):
        # Product is created with specified information_type
        product = self.createProduct(
            information_type=InformationType.EMBARGOED,
            license=License.OTHER_PROPRIETARY)
        self.assertEqual(InformationType.EMBARGOED, product.information_type)
        # Owner can set information_type
        with person_logged_in(removeSecurityProxy(product).owner):
            product.information_type = InformationType.PROPRIETARY
        self.assertEqual(InformationType.PROPRIETARY, product.information_type)
        # Database persists information_type value
        store = Store.of(product)
        store.flush()
        store.reset()
        product = store.get(Product, product.id)
        self.assertEqual(InformationType.PROPRIETARY, product.information_type)
        self.assertTrue(product.private)

    def test_switching_product_to_public_does_not_create_policy(self):
        # Creating a Embargoed product and switching it to Public does not
        # create a PUBLIC AccessPolicy.
        product = self.createProduct(
            information_type=InformationType.EMBARGOED,
            license=License.OTHER_PROPRIETARY)
        aps = getUtility(IAccessPolicySource).findByPillar([product])
        self.assertContentEqual(
            [InformationType.PROPRIETARY, InformationType.EMBARGOED],
            [ap.type for ap in aps])
        removeSecurityProxy(product).information_type = InformationType.PUBLIC
        aps = getUtility(IAccessPolicySource).findByPillar([product])
        self.assertContentEqual(
            [InformationType.PROPRIETARY, InformationType.EMBARGOED],
            [ap.type for ap in aps])

    def test_product_information_type_default(self):
        # Default information_type is PUBLIC
        owner = self.factory.makePerson()
        product = getUtility(IProductSet).createProduct(
            owner, 'fnord', 'Fnord', 'Fnord', 'test 1', 'test 2')
        self.assertEqual(InformationType.PUBLIC, product.information_type)
        self.assertFalse(product.private)

    invalid_information_types = [info_type for info_type in
            InformationType.items if info_type not in
            PUBLIC_PROPRIETARY_INFORMATION_TYPES]

    def test_product_information_type_init_invalid_values(self):
        # Cannot create Product.information_type with invalid values.
        for info_type in self.invalid_information_types:
            with ExpectedException(
                CannotChangeInformationType, 'Not supported for Projects.'):
                self.createProduct(information_type=info_type)

    def test_product_information_type_set_invalid_values(self):
        # Cannot set Product.information_type to invalid values.
        product = self.factory.makeProduct()
        for info_type in self.invalid_information_types:
            with ExpectedException(
                CannotChangeInformationType, 'Not supported for Projects.'):
                with person_logged_in(product.owner):
                    product.information_type = info_type

    def test_set_proprietary_gets_commerical_subscription(self):
        # Changing a Product to Proprietary will auto generate a complimentary
        # subscription just as choosing a proprietary license at creation time.
        owner = self.factory.makePerson(name='pting')
        product = self.factory.makeProduct(owner=owner)
        self.useContext(person_logged_in(owner))
        self.assertIsNone(product.commercial_subscription)

        product.information_type = InformationType.PROPRIETARY
        self.assertEqual(InformationType.PROPRIETARY, product.information_type)
        self.assertIsNotNone(product.commercial_subscription)

    def test_set_proprietary_fails_expired_commerical_subscription(self):
        # Cannot set information type to proprietary with an expired
        # complimentary subscription.
        owner = self.factory.makePerson(name='pting')
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY,
            owner=owner,
        )
        self.useContext(person_logged_in(owner))

        # The Product now has a complimentary commercial subscription.
        new_expires_date = datetime.now(pytz.timezone('UTC')) - timedelta(1)
        naked_subscription = removeSecurityProxy(
            product.commercial_subscription)
        naked_subscription.date_expires = new_expires_date

        # We can make the product PUBLIC
        product.information_type = InformationType.PUBLIC
        self.assertEqual(InformationType.PUBLIC, product.information_type)

        # However we can't change it back to a Proprietary because our
        # commercial subscription has expired.
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with ExpectedException(
                CommercialSubscribersOnly,
                'A valid commercial subscription is required for private'
                ' Projects.'):
                product.information_type = info_type

    def test_product_information_init_proprietary_requires_commercial(self):
        # Cannot create a product with proprietary types without specifying
        # Other/Proprietary license.
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            with ExpectedException(
                CommercialSubscribersOnly,
                'A valid commercial subscription is required for private'
                ' Projects.'):
                self.createProduct(info_type)
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            product = self.createProduct(info_type, License.OTHER_PROPRIETARY)
            self.assertEqual(info_type, product.information_type)

    def test_no_answers_for_proprietary(self):
        # Enabling Answers is forbidden while information_type is proprietary.
        for info_type in PROPRIETARY_INFORMATION_TYPES:
            product = self.factory.makeProduct(information_type=info_type)
            with person_logged_in(removeSecurityProxy(product).owner):
                self.assertEqual(ServiceUsage.UNKNOWN, product.answers_usage)
                for usage in ServiceUsage.items:
                    if usage == ServiceUsage.LAUNCHPAD:
                        with ExpectedException(
                            ServiceUsageForbidden,
                            "Answers not allowed for non-public projects."):
                            product.answers_usage = ServiceUsage.LAUNCHPAD
                    else:
                        # all other values are permitted.
                        product.answers_usage = usage

    def test_answers_for_public(self):
        # Enabling answers is permitted while information_type is PUBLIC
        product = self.factory.makeProduct(
            information_type=InformationType.PUBLIC)
        self.assertEqual(ServiceUsage.UNKNOWN, product.answers_usage)
        with person_logged_in(product.owner):
            for usage in ServiceUsage.items:
                # all values are permitted.
                product.answers_usage = usage

    def test_no_proprietary_if_answers(self):
        # Information type cannot be set to proprietary while Answers are
        # enabled.
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        with person_logged_in(product.owner):
            product.answers_usage = ServiceUsage.LAUNCHPAD
            with ExpectedException(
                CannotChangeInformationType, 'Answers is enabled.'):
                product.information_type = InformationType.PROPRIETARY

    def test_no_proprietary_if_packaging(self):
        # information_type cannot be set to proprietary while any
        # productseries are packaged.
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        series = self.factory.makeProductSeries(product=product)
        self.factory.makePackagingLink(productseries=series)
        with person_logged_in(product.owner):
            with ExpectedException(
                CannotChangeInformationType, 'Some series are packaged.'):
                product.information_type = InformationType.PROPRIETARY

    expected_get_permissions = {
        CheckerPublic: set((
            'active', 'id', 'information_type', 'pillar_category', 'private',
            'userCanView',)),
        'launchpad.LimitedView': set((
            'bugtargetdisplayname', 'displayname', 'drivers',
            'enable_bug_expiration', 'getSpecification',
            'icon', 'logo', 'name', 'official_answers', 'official_anything',
            'official_blueprints', 'official_codehosting', 'official_malone',
            'owner', 'parent_subscription_target', 'project', 'title', )),
        'launchpad.View': set((
            '_getOfficialTagClause', 'visible_specifications',
            'valid_specifications', 'api_valid_specifications',
            'active_or_packaged_series', 'aliases', 'all_milestones',
            'allowsTranslationEdits', 'allowsTranslationSuggestions',
            'announce', 'answer_contacts', 'answers_usage', 'autoupdate',
            'blueprints_usage', 'branch_sharing_policy',
            'bug_reported_acknowledgement', 'bug_reporting_guidelines',
            'bug_sharing_policy', 'bug_subscriptions', 'bug_supervisor',
            'bug_tracking_usage', 'bugtargetname',
            'bugtracker', 'canUserAlterAnswerContact', 'codehosting_usage',
            'coming_sprints', 'commercial_subscription',
            'commercial_subscription_is_due', 'createBug',
            'createCustomLanguageCode', 'custom_language_codes',
            'date_next_suggest_packaging', 'datecreated', 'description',
            'development_focus', 'development_focusID',
            'direct_answer_contacts', 'distrosourcepackages',
            'downloadurl', 'driver',
            'enable_bugfiling_duplicate_search', 'findReferencedOOPS',
            'findSimilarFAQs', 'findSimilarQuestions', 'freshmeatproject',
            'getAllowedBugInformationTypes',
            'getAllowedSpecificationInformationTypes', 'getAnnouncement',
            'getAnnouncements', 'getAnswerContactsForLanguage',
            'getAnswerContactRecipients', 'getBranches',
            'getBugSummaryContextWhereClause', 'getBugTaskWeightFunction',
            'getCustomLanguageCode', 'getDefaultBugInformationType',
            'getDefaultSpecificationInformationType',
            'getEffectiveTranslationPermission', 'getExternalBugTracker',
            'getFAQ', 'getFirstEntryToImport', 'getLinkedBugWatches',
            'getMergeProposals', 'getMilestone', 'getMilestonesAndReleases',
            'getQuestion', 'getQuestionLanguages', 'getPackage', 'getRelease',
            'getSeries', 'getSubscription',
            'getSubscriptions', 'getSupportedLanguages', 'getTimeline',
            'getTopContributors', 'getTopContributorsGroupedByCategory',
            'getTranslationGroups', 'getTranslationImportQueueEntries',
            'getTranslators', 'getUsedBugTagsWithOpenCounts',
            'getVersionSortedSeries',
            'has_current_commercial_subscription',
            'has_custom_language_codes', 'has_milestones', 'homepage_content',
            'homepageurl', 'invitesTranslationEdits',
            'invitesTranslationSuggestions',
            'license_info', 'license_status', 'licenses', 'milestones',
            'mugshot', 'newCodeImport',
            'obsolete_translatable_series', 'official_bug_tags',
            'packagedInDistros', 'packagings',
            'past_sprints', 'personHasDriverRights', 'pillar',
            'primary_translatable', 'private_bugs',
            'programminglang', 'qualifies_for_free_hosting',
            'recipes', 'redeemSubscriptionVoucher', 'registrant', 'releases',
            'remote_product', 'removeCustomLanguageCode',
            'screenshotsurl',
            'searchFAQs', 'searchQuestions', 'searchTasks', 'security_contact',
            'series',
            'sharesTranslationsWithOtherSide', 'sourceforgeproject',
            'sourcepackages', 'specification_sharing_policy', 'specifications',
            'sprints', 'summary', 'target_type_display',
            'translatable_packages', 'translatable_series',
            'translation_focus', 'translationgroup', 'translationgroups',
            'translationpermission', 'translations_usage', 'ubuntu_packages',
            'userCanAlterBugSubscription', 'userCanAlterSubscription',
            'userCanEdit', 'userHasBugSubscriptions', 'uses_launchpad',
            'wikiurl')),
        'launchpad.AnyAllowedPerson': set((
            'addAnswerContact', 'addBugSubscription',
            'addBugSubscriptionFilter', 'addSubscription',
            'createQuestionFromBug', 'newQuestion', 'removeAnswerContact',
            'removeBugSubscription')),
        'launchpad.Append': set(('newFAQ', )),
        'launchpad.Driver': set(('newSeries', )),
        'launchpad.Edit': set((
            'addOfficialBugTag', 'removeOfficialBugTag',
            'setBranchSharingPolicy', 'setBugSharingPolicy',
            'setSpecificationSharingPolicy', 'checkInformationType')),
        'launchpad.Moderate': set((
            'is_permitted', 'license_approved', 'project_reviewed',
            'reviewer_whiteboard', 'setAliases')),
        }

    def test_get_permissions(self):
        product = self.factory.makeProduct()
        checker = getChecker(product)
        self.checkPermissions(
            self.expected_get_permissions, checker.get_permissions, 'get')

    def test_set_permissions(self):
        expected_set_permissions = {
            'launchpad.BugSupervisor': set((
                'bug_reported_acknowledgement', 'bug_reporting_guidelines',
                'bugtracker', 'enable_bug_expiration',
                'enable_bugfiling_duplicate_search', 'official_bug_tags',
                'official_malone', 'remote_product')),
            'launchpad.Edit': set((
                'answers_usage', 'blueprints_usage', 'bug_supervisor',
                'bug_tracking_usage', 'codehosting_usage',
                'commercial_subscription', 'description', 'development_focus',
                'displayname', 'downloadurl', 'driver', 'freshmeatproject',
                'homepage_content', 'homepageurl', 'icon', 'information_type',
                'license_info', 'licenses', 'logo', 'mugshot',
                'official_answers', 'official_blueprints',
                'official_codehosting', 'owner', 'private',
                'programminglang', 'project', 'redeemSubscriptionVoucher',
                'releaseroot', 'screenshotsurl', 'sourceforgeproject',
                'summary', 'title', 'uses_launchpad', 'wikiurl')),
            'launchpad.Moderate': set((
                'active', 'autoupdate', 'license_approved', 'name',
                'project_reviewed', 'registrant', 'reviewer_whiteboard')),
            'launchpad.TranslationsAdmin': set((
                'translation_focus', 'translationgroup',
                'translationpermission', 'translations_usage')),
            'launchpad.AnyAllowedPerson': set((
                'date_next_suggest_packaging', )),
            }
        product = self.factory.makeProduct()
        checker = getChecker(product)
        self.checkPermissions(
            expected_set_permissions, checker.set_permissions, 'set')

    def test_access_launchpad_View_public_product(self):
        # Everybody, including anonymous users, has access to
        # properties of public products that require the permission
        # launchpad.View
        product = self.factory.makeProduct()
        names = self.expected_get_permissions['launchpad.View']
        with person_logged_in(None):
            for attribute_name in names:
                getattr(product, attribute_name)
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                getattr(product, attribute_name)
        with person_logged_in(product.owner):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_access_launchpad_View_public_inactive_product(self):
        # Everybody, including anonymous users, has access to
        # properties of public but inactvie products that require
        # the permission launchpad.View.
        product = self.factory.makeProduct()
        removeSecurityProxy(product).active = False
        names = self.expected_get_permissions['launchpad.View']
        with person_logged_in(None):
            for attribute_name in names:
                getattr(product, attribute_name)
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                getattr(product, attribute_name)
        with person_logged_in(product.owner):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_access_launchpad_View_proprietary_product(self):
        # Only people with grants for a private product can access
        # attributes protected by the permission launchpad.View.
        product = self.createProduct(
            information_type=InformationType.PROPRIETARY,
            license=License.OTHER_PROPRIETARY)
        owner = removeSecurityProxy(product).owner
        names = self.expected_get_permissions['launchpad.View']
        with person_logged_in(None):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        with person_logged_in(owner):
            for attribute_name in names:
                getattr(product, attribute_name)
        # A user with a policy grant for the product can access attributes
        # of a private product.
        with person_logged_in(owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                product, ordinary_user, owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                getattr(product, attribute_name)
        # Access can be granted to a team too.
        other_user = self.factory.makePerson()
        team = self.factory.makeTeam(members=[other_user])
        with person_logged_in(owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                product, team, owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        with person_logged_in(other_user):
            for attribute_name in names:
                getattr(product, attribute_name)
        # Admins can access proprietary products.
        with celebrity_logged_in('admin'):
            for attribute_name in names:
                getattr(product, attribute_name)
        # Commercial admins have access to all products.
        with celebrity_logged_in('commercial_admin'):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_admin_launchpad_View_proprietary_product(self):
        # Admins and commercial admins can view proprietary products.
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY)
        names = self.expected_get_permissions['launchpad.View']
        with person_logged_in(self.factory.makeAdministrator()):
            for attribute_name in names:
                getattr(product, attribute_name)
        with person_logged_in(self.factory.makeCommercialAdmin()):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_access_LimitedView_public_product(self):
        # Everybody can access attributes of public products that
        # require the permission launchpad.LimitedView.
        product = self.factory.makeProduct()
        names = self.expected_get_permissions['launchpad.LimitedView']
        with person_logged_in(None):
            for attribute_name in names:
                getattr(product, attribute_name)
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_access_LimitedView_proprietary_product(self):
        # Anonymous users and ordinary logged in users cannot access
        # attributes of private products that require the permission
        # launchpad.LimitedView.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            information_type=InformationType.PROPRIETARY)
        names = self.expected_get_permissions['launchpad.LimitedView']
        with person_logged_in(None):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        user = self.factory.makePerson()
        with person_logged_in(user):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        # Users with a grant on an artifact related to the product
        # can access the attributes.
        with person_logged_in(owner):
            bug = self.factory.makeBug(
                target=product, information_type=InformationType.PROPRIETARY)
            getUtility(IService, 'sharing').ensureAccessGrants(
                [user], owner, bugs=[bug])
        with person_logged_in(user):
            for attribute_name in names:
                getattr(product, attribute_name)
        # Users with a policy grant for the product also have access.
        user2 = self.factory.makePerson()
        with person_logged_in(owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                product, user2, owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        with person_logged_in(user2):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_access_launchpad_AnyAllowedPerson_public_product(self):
        # Only logged in persons have access to properties of public products
        # that require the permission launchpad.AnyAllowedPerson.
        product = self.factory.makeProduct()
        names = self.expected_get_permissions['launchpad.AnyAllowedPerson']
        with person_logged_in(None):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                getattr(product, attribute_name)
        with person_logged_in(product.owner):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_access_launchpad_AnyAllowedPerson_proprietary_product(self):
        # Only people with grants for a private product can access
        # attributes protected by the permission launchpad.AnyAllowedPerson.
        product = self.createProduct(
            information_type=InformationType.PROPRIETARY,
            license=License.OTHER_PROPRIETARY)
        owner = removeSecurityProxy(product).owner
        names = self.expected_get_permissions['launchpad.AnyAllowedPerson']
        with person_logged_in(None):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                self.assertRaises(
                    Unauthorized, getattr, product, attribute_name)
        with person_logged_in(owner):
            for attribute_name in names:
                getattr(product, attribute_name)
        # A user with a policy grant for the product can access attributes
        # of a private product.
        with person_logged_in(owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                product, ordinary_user, owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        with person_logged_in(ordinary_user):
            for attribute_name in names:
                getattr(product, attribute_name)

    def test_set_launchpad_AnyAllowedPerson_public_product(self):
        # Only logged in users can set attributes protected by the
        # permission launchpad.AnyAllowedPerson.
        product = self.factory.makeProduct()
        with person_logged_in(None):
            self.assertRaises(
                Unauthorized, setattr, product, 'date_next_suggest_packaging',
                'foo')
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            setattr(product, 'date_next_suggest_packaging', 'foo')
        with person_logged_in(product.owner):
            setattr(product, 'date_next_suggest_packaging', 'foo')

    def test_set_launchpad_AnyAllowedPerson_proprietary_product(self):
        # Only people with grants for a private product can set
        # attributes protected by the permission launchpad.AnyAllowedPerson.
        product = self.createProduct(
            information_type=InformationType.PROPRIETARY,
            license=License.OTHER_PROPRIETARY)
        owner = removeSecurityProxy(product).owner
        with person_logged_in(None):
            self.assertRaises(
                Unauthorized, setattr, product, 'date_next_suggest_packaging',
                'foo')
        ordinary_user = self.factory.makePerson()
        with person_logged_in(ordinary_user):
            self.assertRaises(
                Unauthorized, setattr, product, 'date_next_suggest_packaging',
                'foo')
        with person_logged_in(owner):
            setattr(product, 'date_next_suggest_packaging', 'foo')
        # A user with a policy grant for the product can access attributes
        # of a private product.
        with person_logged_in(owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                product, ordinary_user, owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        with person_logged_in(ordinary_user):
            setattr(product, 'date_next_suggest_packaging', 'foo')

    def test_userCanView_caches_known_users(self):
        # userCanView() maintains a cache of users known to have the
        # permission to access a product.
        product = self.createProduct(
            information_type=InformationType.PROPRIETARY,
            license=License.OTHER_PROPRIETARY)
        owner = removeSecurityProxy(product).owner
        user = self.factory.makePerson()
        with person_logged_in(owner):
            getUtility(IService, 'sharing').sharePillarInformation(
                product, user, owner,
                {InformationType.PROPRIETARY: SharingPermission.ALL})
        with person_logged_in(user):
            with StormStatementRecorder() as recorder:
                # The first access to a property of the product from
                # a user requires a DB query.
                product.homepageurl
                queries_for_first_user_access = len(recorder.queries)
                # The second access does not require another query.
                product.description
                self.assertEqual(
                    queries_for_first_user_access, len(recorder.queries))

    def test_userCanView_works_with_IPersonRoles(self):
        # userCanView() maintains a cache of users known to have the
        # permission to access a product.
        product = self.createProduct(
            information_type=InformationType.PROPRIETARY,
            license=License.OTHER_PROPRIETARY)
        user = self.factory.makePerson()
        product.userCanView(user)
        product.userCanView(IPersonRoles(user))

    def test_information_type_prevents_pruning(self):
        # Access policies for Product.information_type are not pruned.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.EMBARGOED, owner=owner)
        with person_logged_in(owner):
            product.setBugSharingPolicy(BugSharingPolicy.PROPRIETARY)
            product.setSpecificationSharingPolicy(
                SpecificationSharingPolicy.PROPRIETARY)
            product.setBranchSharingPolicy(BranchSharingPolicy.PROPRIETARY)
        self.assertIsNot(None, getUtility(IAccessPolicySource).find(
            [(product, InformationType.EMBARGOED)]).one())


class TestProductBugInformationTypes(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeProductWithPolicy(self, bug_sharing_policy):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product=product)
        with person_logged_in(product.owner):
            product.setBugSharingPolicy(bug_sharing_policy)
        return product

    def test_no_policy(self):
        # New projects can only use the non-proprietary information
        # types.
        product = self.factory.makeProduct()
        self.assertContentEqual(
            FREE_INFORMATION_TYPES, product.getAllowedBugInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC, product.getDefaultBugInformationType())

    def test_sharing_policy_public_or_proprietary(self):
        # bug_sharing_policy can enable Proprietary.
        product = self.makeProductWithPolicy(
            BugSharingPolicy.PUBLIC_OR_PROPRIETARY)
        self.assertContentEqual(
            FREE_INFORMATION_TYPES + (InformationType.PROPRIETARY,),
            product.getAllowedBugInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC,
            product.getDefaultBugInformationType())

    def test_sharing_policy_proprietary_or_public(self):
        # bug_sharing_policy can enable and default to Proprietary.
        product = self.makeProductWithPolicy(
            BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        self.assertContentEqual(
            FREE_INFORMATION_TYPES + (InformationType.PROPRIETARY,),
            product.getAllowedBugInformationTypes())
        self.assertEqual(
            InformationType.PROPRIETARY,
            product.getDefaultBugInformationType())

    def test_sharing_policy_proprietary(self):
        # bug_sharing_policy can enable only Proprietary.
        product = self.makeProductWithPolicy(BugSharingPolicy.PROPRIETARY)
        self.assertContentEqual(
            [InformationType.PROPRIETARY],
            product.getAllowedBugInformationTypes())
        self.assertEqual(
            InformationType.PROPRIETARY,
            product.getDefaultBugInformationType())


class TestProductSpecificationPolicyAndInformationTypes(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeProductWithPolicy(self, specification_sharing_policy):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product=product)
        with person_logged_in(product.owner):
            product.setSpecificationSharingPolicy(
                specification_sharing_policy)
        return product

    def test_no_policy(self):
        # Projects that have not specified a policy can use the PUBLIC
        # information type.
        product = self.factory.makeProduct()
        self.assertContentEqual(
            [InformationType.PUBLIC],
            product.getAllowedSpecificationInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC,
            product.getDefaultSpecificationInformationType())

    def test_sharing_policy_public(self):
        # Projects with a purely public policy should use PUBLIC
        # information type.
        product = self.makeProductWithPolicy(
            SpecificationSharingPolicy.PUBLIC)
        self.assertContentEqual(
            [InformationType.PUBLIC],
            product.getAllowedSpecificationInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC,
            product.getDefaultSpecificationInformationType())

    def test_sharing_policy_public_or_proprietary(self):
        # specification_sharing_policy can enable Proprietary.
        product = self.makeProductWithPolicy(
            SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY)
        self.assertContentEqual(
            [InformationType.PUBLIC, InformationType.PROPRIETARY],
            product.getAllowedSpecificationInformationTypes())
        self.assertEqual(
            InformationType.PUBLIC,
            product.getDefaultSpecificationInformationType())

    def test_sharing_policy_proprietary_or_public(self):
        # specification_sharing_policy can enable and default to Proprietary.
        product = self.makeProductWithPolicy(
            SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC)
        self.assertContentEqual(
            [InformationType.PUBLIC, InformationType.PROPRIETARY],
            product.getAllowedSpecificationInformationTypes())
        self.assertEqual(
            InformationType.PROPRIETARY,
            product.getDefaultSpecificationInformationType())

    def test_sharing_policy_proprietary(self):
        # specification_sharing_policy can enable only Proprietary.
        product = self.makeProductWithPolicy(
            SpecificationSharingPolicy.PROPRIETARY)
        self.assertContentEqual(
            [InformationType.PROPRIETARY],
            product.getAllowedSpecificationInformationTypes())
        self.assertEqual(
            InformationType.PROPRIETARY,
            product.getDefaultSpecificationInformationType())

    def test_sharing_policy_embargoed_or_proprietary(self):
        # specification_sharing_policy can be embargoed and then proprietary.
        product = self.makeProductWithPolicy(
            SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY)
        self.assertContentEqual(
            [InformationType.PROPRIETARY, InformationType.EMBARGOED],
            product.getAllowedSpecificationInformationTypes())
        self.assertEqual(
            InformationType.EMBARGOED,
            product.getDefaultSpecificationInformationType())


class ProductPermissionTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_owner_can_edit(self):
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            self.assertTrue(check_permission('launchpad.Edit', product))

    def test_commercial_admin_cannot_edit_non_commercial(self):
        product = self.factory.makeProduct()
        with celebrity_logged_in('commercial_admin'):
            self.assertFalse(check_permission('launchpad.Edit', product))

    def test_commercial_admin_can_edit_commercial(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        with celebrity_logged_in('commercial_admin'):
            self.assertTrue(check_permission('launchpad.Edit', product))

    def test_owner_can_driver(self):
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            self.assertTrue(check_permission('launchpad.Driver', product))

    def test_driver_can_driver(self):
        product = self.factory.makeProduct()
        driver = self.factory.makePerson()
        with person_logged_in(product.owner):
            product.driver = driver
        with person_logged_in(driver):
            self.assertTrue(check_permission('launchpad.Driver', product))

    def test_commercial_admin_cannot_drive_non_commercial(self):
        product = self.factory.makeProduct()
        with celebrity_logged_in('commercial_admin'):
            self.assertFalse(check_permission('launchpad.Driver', product))

    def test_commercial_admin_can_drive_commercial(self):
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        with celebrity_logged_in('commercial_admin'):
            self.assertTrue(check_permission('launchpad.Driver', product))


class TestProductFiles(TestCase):
    """Tests for downloadable product files."""

    layer = LaunchpadFunctionalLayer

    def test_adddownloadfile_nonascii_filename(self):
        """Test uploading a file with a non-ascii char in the filename."""
        firefox_owner = setupBrowser(auth='Basic mark@example.com:test')
        filename = u'foo\xa5.txt'.encode('utf-8')
        firefox_owner.open(
            'http://launchpad.dev/firefox/1.0/1.0.0/+adddownloadfile')
        foo_file = StringIO('Foo installer package...')
        foo_signature = StringIO('Dummy GPG signature for the Foo installer')
        firefox_owner.getControl(name='field.filecontent').add_file(
            foo_file, 'text/plain', filename)
        firefox_owner.getControl(name='field.signature').add_file(
            foo_signature, 'text/plain', '%s.asc' % filename)
        firefox_owner.getControl('Description').value = "Foo installer"
        firefox_owner.getControl(name="field.contenttype").displayValue = \
           ["Installer file"]
        firefox_owner.getControl("Upload").click()
        self.assertEqual(
            get_feedback_messages(firefox_owner.contents),
            [html_escape(u"Your file 'foo\xa5.txt' has been uploaded.")])
        firefox_owner.open('http://launchpad.dev/firefox/+download')
        content = find_main_content(firefox_owner.contents)
        rows = content.findAll('tr')

        a_list = rows[-1].findAll('a')
        # 1st row
        a_element = a_list[0]
        self.assertEqual(
            a_element['href'],
            'http://launchpad.dev/firefox/1.0/1.0.0/+download/foo%C2%A5.txt')
        self.assertEqual(a_element.contents[0].strip(), u'foo\xa5.txt')
        # 2nd row
        a_element = a_list[1]
        self.assertEqual(
            a_element['href'],
            'http://launchpad.dev/firefox/1.0/1.0.0/+download/'
            'foo%C2%A5.txt/+md5')
        self.assertEqual(a_element.contents[0].strip(), u'md5')
        # 3rd row
        a_element = a_list[2]
        self.assertEqual(
            a_element['href'],
            'http://launchpad.dev/firefox/1.0/1.0.0/+download/'
            'foo%C2%A5.txt.asc')
        self.assertEqual(a_element.contents[0].strip(), u'sig')


class ProductAttributeCacheTestCase(TestCaseWithFactory):
    """Cached attributes must be cleared at the end of a transaction."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(ProductAttributeCacheTestCase, self).setUp()
        self.product = Product.selectOneBy(name='tomcat')

    def testLicensesCache(self):
        """License cache should be cleared automatically."""
        self.assertEqual(self.product.licenses,
                         (License.ACADEMIC, License.AFFERO))
        ProductLicense(product=self.product, license=License.PYTHON)
        # Cache doesn't see new value.
        self.assertEqual(self.product.licenses,
                         (License.ACADEMIC, License.AFFERO))
        self.product.licenses = (License.PERL, License.PHP)
        self.assertEqual(self.product.licenses,
                         (License.PERL, License.PHP))
        # Cache is cleared and it sees database changes that occur
        # before the cache is populated.
        transaction.abort()
        ProductLicense(product=self.product, license=License.MIT)
        self.assertEqual(self.product.licenses,
                         (License.ACADEMIC, License.AFFERO, License.MIT))

    def testCommercialSubscriptionCache(self):
        """commercial_subscription cache should not traverse transactions."""
        self.assertEqual(self.product.commercial_subscription, None)
        self.factory.makeCommercialSubscription(self.product)
        self.assertEqual(self.product.commercial_subscription, None)
        self.product.redeemSubscriptionVoucher(
            'hello', self.product.owner, self.product.owner, 1)
        self.assertEqual(
            'hello', self.product.commercial_subscription.sales_system_id)
        transaction.abort()
        # Cache is cleared.
        self.assertIs(None, self.product.commercial_subscription)

        # Cache is cleared again.
        transaction.abort()
        self.factory.makeCommercialSubscription(self.product)
        # Cache is cleared and it sees database changes that occur
        # before the cache is populated.
        self.assertEqual(
            'new', self.product.commercial_subscription.sales_system_id)


class ProductLicensingTestCase(TestCaseWithFactory):
    """Test the rules of licences and commercial subscriptions."""

    layer = DatabaseFunctionalLayer
    event_listener = None

    def setup_event_listener(self):
        self.events = []
        if self.event_listener is None:
            self.event_listener = TestEventListener(
                IProduct, IObjectModifiedEvent, self.on_event)
        else:
            self.event_listener._active = True
        self.addCleanup(self.event_listener.unregister)

    def on_event(self, thing, event):
        self.events.append(event)

    def test_getLicenses(self):
        # License are assigned a list, but return a tuple.
        product = self.factory.makeProduct(
            licenses=[License.GNU_GPL_V2, License.MIT])
        self.assertEqual((License.GNU_GPL_V2, License.MIT), product.licenses)

    def test_setLicense_handles_no_change(self):
        # The project_reviewed property is not reset, if the new licences
        # are identical to the current licences.
        product = self.factory.makeProduct(licenses=[License.MIT])
        with celebrity_logged_in('registry_experts'):
            product.project_reviewed = True
        self.setup_event_listener()
        with person_logged_in(product.owner):
            product.licenses = [License.MIT]
        with celebrity_logged_in('registry_experts'):
            self.assertIs(True, product.project_reviewed)
        self.assertEqual([], self.events)

    def test_setLicense(self):
        # The project_reviewed property is not reset, if the new licences
        # are identical to the current licences.
        product = self.factory.makeProduct()
        self.setup_event_listener()
        with person_logged_in(product.owner):
            product.licenses = [License.MIT]
        self.assertEqual((License.MIT, ), product.licenses)
        self.assertEqual(1, len(self.events))
        self.assertEqual(product, self.events[0].object)

    def test_setLicense_also_sets_reviewed(self):
        # The project_reviewed attribute it set to False if the licenses
        # change.
        product = self.factory.makeProduct(licenses=[License.MIT])
        with celebrity_logged_in('registry_experts'):
            product.project_reviewed = True
        with person_logged_in(product.owner):
            product.licenses = [License.GNU_GPL_V2]
        with celebrity_logged_in('registry_experts'):
            self.assertIs(False, product.project_reviewed)

    def test_license_info_also_sets_reviewed(self):
        # The project_reviewed attribute it set to False if license_info
        # changes.
        product = self.factory.makeProduct(
            licenses=[License.OTHER_OPEN_SOURCE])
        with celebrity_logged_in('registry_experts'):
            product.project_reviewed = True
        with person_logged_in(product.owner):
            product.license_info = 'zlib'
        with celebrity_logged_in('registry_experts'):
            self.assertIs(False, product.project_reviewed)

    def test_setLicense_without_empty_licenses_error(self):
        # A project must have at least one licence.
        product = self.factory.makeProduct(licenses=[License.MIT])
        with person_logged_in(product.owner):
            self.assertRaises(
                ValueError, setattr, product, 'licenses', [])

    def test_setLicense_without_non_licenses_error(self):
        # A project must have at least one licence.
        product = self.factory.makeProduct(licenses=[License.MIT])
        with person_logged_in(product.owner):
            self.assertRaises(
                ValueError, setattr, product, 'licenses', ['bogus'])

    def test_setLicense_non_proprietary(self):
        # Non-proprietary projects are not given a complimentary
        # commercial subscription.
        product = self.factory.makeProduct(licenses=[License.MIT])
        self.assertIsNone(product.commercial_subscription)

    def test_setLicense_proprietary_with_commercial_subscription(self):
        # Proprietary projects with existing commercial subscriptions are not
        # given a complimentary commercial subscription.
        product = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(product)
        with celebrity_logged_in('admin'):
            product.commercial_subscription.sales_system_id = 'testing'
            date_expires = product.commercial_subscription.date_expires
        with person_logged_in(product.owner):
            product.licenses = [License.OTHER_PROPRIETARY]
        with celebrity_logged_in('admin'):
            self.assertEqual(
                'testing', product.commercial_subscription.sales_system_id)
            self.assertEqual(
                date_expires, product.commercial_subscription.date_expires)

    def test_setLicense_proprietary_without_commercial_subscription(self):
        # Proprietary projects without a commercial subscriptions are
        # given a complimentary 30 day commercial subscription.
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            product.licenses = [License.OTHER_PROPRIETARY]
        with celebrity_logged_in('admin'):
            cs = product.commercial_subscription
            self.assertIsNotNone(cs)
            self.assertIn('complimentary-30-day', cs.sales_system_id)
            now = datetime.now(pytz.UTC)
            self.assertTrue(now >= cs.date_starts)
            future_30_days = now + timedelta(days=30)
            self.assertTrue(future_30_days >= cs.date_expires)
            self.assertIn(
                "Complimentary 30 day subscription. -- Launchpad",
                cs.whiteboard)
            lp_janitor = getUtility(ILaunchpadCelebrities).janitor
            self.assertEqual(lp_janitor, cs.registrant)
            self.assertEqual(lp_janitor, cs.purchaser)

    def test_new_proprietary_has_commercial_subscription(self):
        # New proprietary projects are given a complimentary 30 day
        # commercial subscription.
        owner = self.factory.makePerson()
        with person_logged_in(owner):
            product = getUtility(IProductSet).createProduct(
                owner, 'fnord', 'Fnord', 'Fnord', 'test 1', 'test 2',
                licenses=[License.OTHER_PROPRIETARY])
        with celebrity_logged_in('admin'):
            cs = product.commercial_subscription
            self.assertIsNotNone(cs)
            self.assertIn('complimentary-30-day', cs.sales_system_id)
            now = datetime.now(pytz.UTC)
            self.assertTrue(now >= cs.date_starts)
            future_30_days = now + timedelta(days=30)
            self.assertTrue(future_30_days >= cs.date_expires)
            self.assertIn(
                "Complimentary 30 day subscription. -- Launchpad",
                cs.whiteboard)
            lp_janitor = getUtility(ILaunchpadCelebrities).janitor
            self.assertEqual(lp_janitor, cs.registrant)
            self.assertEqual(lp_janitor, cs.purchaser)


class BaseSharingPolicyTests:
    """Common tests for product sharing policies."""

    layer = DatabaseFunctionalLayer

    def setSharingPolicy(self, policy, user):
        raise NotImplementedError

    def getSharingPolicy(self):
        raise NotImplementedError

    def setUp(self):
        super(BaseSharingPolicyTests, self).setUp()
        self.product = self.factory.makeProduct()
        self.commercial_admin = self.factory.makeCommercialAdmin()

    def test_owner_can_set_policy(self):
        # Project maintainers can set sharing policies.
        self.setSharingPolicy(self.public_policy, self.product.owner)
        self.assertEqual(self.public_policy, self.getSharingPolicy())

    def test_commercial_admin_can_set_policy(self):
        # Commercial admins can set sharing policies for commercial projects.
        self.factory.makeCommercialSubscription(product=self.product)
        self.setSharingPolicy(self.public_policy, self.commercial_admin)
        self.assertEqual(self.public_policy, self.getSharingPolicy())

    def test_random_cannot_set_policy(self):
        # An unrelated user can't set sharing policies.
        person = self.factory.makePerson()
        self.assertRaises(
            Unauthorized, self.setSharingPolicy, self.public_policy, person)

    def test_anonymous_cannot_set_policy(self):
        # An anonymous user can't set sharing policies.
        self.assertRaises(
            Unauthorized, self.setSharingPolicy, self.public_policy, None)

    def test_proprietary_forbidden_without_commercial_sub(self):
        # No policy that allows Proprietary can be configured without a
        # commercial subscription.
        self.setSharingPolicy(self.public_policy, self.product.owner)
        self.assertEqual(self.public_policy, self.getSharingPolicy())
        for policy in self.commercial_policies:
            self.assertRaises(
                CommercialSubscribersOnly,
                self.setSharingPolicy, policy, self.product.owner)

    def test_proprietary_allowed_with_commercial_sub(self):
        # All policies are valid when there's a current commercial
        # subscription.
        self.factory.makeCommercialSubscription(product=self.product)
        for policy in self.enum.items:
            self.setSharingPolicy(policy, self.commercial_admin)
            self.assertEqual(policy, self.getSharingPolicy())

    def test_setting_proprietary_creates_access_policy(self):
        # Setting a policy that allows Proprietary creates a
        # corresponding access policy and shares it with the the
        # maintainer.
        self.factory.makeCommercialSubscription(product=self.product)
        self.assertEqual(
            [InformationType.PRIVATESECURITY, InformationType.USERDATA],
            [policy.type for policy in
             getUtility(IAccessPolicySource).findByPillar([self.product])])
        self.setSharingPolicy(
            self.commercial_policies[0], self.commercial_admin)
        self.assertEqual(
            [InformationType.PRIVATESECURITY, InformationType.USERDATA,
             InformationType.PROPRIETARY],
            [policy.type for policy in
             getUtility(IAccessPolicySource).findByPillar([self.product])])
        self.assertTrue(
            getUtility(IService, 'sharing').checkPillarAccess(
                [self.product], InformationType.PROPRIETARY,
                self.product.owner))

    def test_unused_policies_are_pruned(self):
        # When a sharing policy is changed, the allowed information types may
        # become more restricted. If this case, any existing access polices
        # for the now defunct information type(s) should be removed so long as
        # there are no corresponding policy artifacts.

        # We create a product with and ensure there's an APA.
        ap_source = getUtility(IAccessPolicySource)
        product = self.factory.makeProduct()
        [ap] = ap_source.find([(product, InformationType.PRIVATESECURITY)])
        self.factory.makeAccessPolicyArtifact(policy=ap)

        def getAccessPolicyTypes(pillar):
            return [
                ap.type
                for ap in ap_source.findByPillar([pillar])]

        # Now change the sharing policies to PROPRIETARY
        self.factory.makeCommercialSubscription(product=product)
        with person_logged_in(product.owner):
            product.setBugSharingPolicy(BugSharingPolicy.PROPRIETARY)
            # Just bug sharing policy has been changed so all previous policy
            # types are still valid.
            self.assertContentEqual(
                [InformationType.PRIVATESECURITY, InformationType.USERDATA,
                 InformationType.PROPRIETARY],
                getAccessPolicyTypes(product))

            product.setBranchSharingPolicy(BranchSharingPolicy.PROPRIETARY)
            # Proprietary is permitted by the sharing policy, and there's a
            # Private Security artifact. But Private isn't in use or allowed
            # by a sharing policy, so it's now gone.
            self.assertContentEqual(
                [InformationType.PRIVATESECURITY, InformationType.PROPRIETARY],
                getAccessPolicyTypes(product))

    def test_proprietary_products_forbid_public_policies(self):
        # A proprietary project forbids any sharing policy that would permit
        # public artifacts.
        owner = self.product.owner
        with person_logged_in(owner):
            self.product.licenses = [License.OTHER_PROPRIETARY]
            self.product.information_type = InformationType.PROPRIETARY
        policies_permitting_public = [self.public_policy]
        policies_permitting_public.extend(
            policy for policy in self.commercial_policies if
            InformationType.PUBLIC in self.allowed_types[policy])
        for policy in policies_permitting_public:
            with ExpectedException(
                ProprietaryProduct, "The project is Proprietary."):
                self.setSharingPolicy(policy, owner)
        with person_logged_in(owner):
            self.product.information_type = InformationType.EMBARGOED
        for policy in policies_permitting_public:
            with ExpectedException(
                ProprietaryProduct, "The project is Embargoed."):
                self.setSharingPolicy(policy, owner)


class ProductBugSharingPolicyTestCase(BaseSharingPolicyTests,
                                      TestCaseWithFactory):
    """Test Product.bug_sharing_policy."""

    layer = DatabaseFunctionalLayer

    enum = BugSharingPolicy
    public_policy = BugSharingPolicy.PUBLIC
    commercial_policies = (
        BugSharingPolicy.PUBLIC_OR_PROPRIETARY,
        BugSharingPolicy.PROPRIETARY_OR_PUBLIC,
        BugSharingPolicy.PROPRIETARY,
        )
    allowed_types = BUG_POLICY_ALLOWED_TYPES

    def setSharingPolicy(self, policy, user):
        with person_logged_in(user):
            result = self.product.setBugSharingPolicy(policy)
        return result

    def getSharingPolicy(self):
        return self.product.bug_sharing_policy


class ProductBranchSharingPolicyTestCase(BaseSharingPolicyTests,
                                         TestCaseWithFactory):
    """Test Product.branch_sharing_policy."""

    layer = DatabaseFunctionalLayer

    enum = BranchSharingPolicy
    public_policy = BranchSharingPolicy.PUBLIC
    commercial_policies = (
        BranchSharingPolicy.PUBLIC_OR_PROPRIETARY,
        BranchSharingPolicy.PROPRIETARY_OR_PUBLIC,
        BranchSharingPolicy.PROPRIETARY,
        BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY,
        )
    allowed_types = BRANCH_POLICY_ALLOWED_TYPES

    def setSharingPolicy(self, policy, user):
        with person_logged_in(user):
            result = self.product.setBranchSharingPolicy(policy)
        return result

    def getSharingPolicy(self):
        return self.product.branch_sharing_policy

    def test_setting_embargoed_creates_access_policy(self):
        # Setting a policy that allows Embargoed creates a
        # corresponding access policy and shares it with the the
        # maintainer.
        self.factory.makeCommercialSubscription(product=self.product)
        self.assertEqual(
            [InformationType.PRIVATESECURITY, InformationType.USERDATA],
            [policy.type for policy in
             getUtility(IAccessPolicySource).findByPillar([self.product])])
        self.setSharingPolicy(
            self.enum.EMBARGOED_OR_PROPRIETARY,
            self.commercial_admin)
        self.assertEqual(
            [InformationType.PRIVATESECURITY, InformationType.USERDATA,
             InformationType.PROPRIETARY, InformationType.EMBARGOED],
            [policy.type for policy in
             getUtility(IAccessPolicySource).findByPillar([self.product])])
        self.assertTrue(
            getUtility(IService, 'sharing').checkPillarAccess(
                [self.product], InformationType.PROPRIETARY,
                self.product.owner))
        self.assertTrue(
            getUtility(IService, 'sharing').checkPillarAccess(
                [self.product], InformationType.EMBARGOED,
                self.product.owner))


class ProductSpecificationSharingPolicyTestCase(
    ProductBranchSharingPolicyTestCase):
    """Test Product.specification_sharing_policy."""

    layer = DatabaseFunctionalLayer

    enum = SpecificationSharingPolicy
    public_policy = SpecificationSharingPolicy.PUBLIC
    commercial_policies = (
        SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY,
        SpecificationSharingPolicy.PROPRIETARY_OR_PUBLIC,
        SpecificationSharingPolicy.PROPRIETARY,
        SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY,
        )
    allowed_types = SPECIFICATION_POLICY_ALLOWED_TYPES

    def setSharingPolicy(self, policy, user):
        with person_logged_in(user):
            result = self.product.setSpecificationSharingPolicy(policy)
        return result

    def getSharingPolicy(self):
        return self.product.specification_sharing_policy


class ProductSnapshotTestCase(TestCaseWithFactory):
    """Test product snapshots.

    Some attributes of a product should not be included in snapshots,
    typically because they are either too costly to fetch unless there's
    a real need, or because they get too big and trigger a shortlist
    overflow error.

    To stop an attribute from being snapshotted, wrap its declaration in
    the interface in `doNotSnapshot`.
    """

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(ProductSnapshotTestCase, self).setUp()
        self.product = self.factory.makeProduct(name="shamwow")

    def test_excluded_from_snapshot(self):
        omitted = [
            'series',
            'recipes',
            'releases',
            ]
        self.assertThat(self.product, DoesNotSnapshot(omitted, IProduct))


class TestProductTranslations(TestCaseWithFactory):
    """A TestCase for accessing product translations-related attributes."""

    layer = DatabaseFunctionalLayer

    def test_rosetta_expert(self):
        # Ensure rosetta-experts can set Product attributes
        # related to translations.
        product = self.factory.makeProduct()
        new_series = self.factory.makeProductSeries(product=product)
        group = self.factory.makeTranslationGroup()
        with celebrity_logged_in('rosetta_experts'):
            product.translations_usage = ServiceUsage.LAUNCHPAD
            product.translation_focus = new_series
            product.translationgroup = group
            product.translationpermission = TranslationPermission.CLOSED


def list_result(product, filter=None, user=None):
    result = product.specifications(
        user, SpecificationSort.DATE, filter=filter)
    return list(result)


class TestSpecifications(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSpecifications, self).setUp()
        self.date_created = datetime.now(pytz.utc)

    def makeSpec(self, product=None, date_created=0, title=None,
                 status=NewSpecificationDefinitionStatus.NEW,
                 name=None, priority=None, information_type=None):
        blueprint = self.factory.makeSpecification(
            title=title, status=status, name=name, priority=priority,
            information_type=information_type, product=product,
            )
        removeSecurityProxy(blueprint).datecreated = (
            self.date_created + timedelta(date_created))
        return blueprint

    def test_specifications_quantity(self):
        # Ensure the quantity controls the maximum number of entries.
        product = self.factory.makeProduct()
        for count in range(10):
            self.factory.makeSpecification(product=product)
        self.assertEqual(10, product.specifications(None).count())
        result = product.specifications(None, quantity=None).count()
        self.assertEqual(10, result)
        self.assertEqual(8, product.specifications(None, quantity=8).count())
        self.assertEqual(10, product.specifications(None, quantity=11).count())

    def test_date_sort(self):
        # Sort on date_created.
        product = self.factory.makeProduct()
        blueprint1 = self.makeSpec(product, date_created=0)
        blueprint2 = self.makeSpec(product, date_created=-1)
        blueprint3 = self.makeSpec(product, date_created=1)
        result = list_result(product)
        self.assertEqual([blueprint3, blueprint1, blueprint2], result)

    def test_date_sort_id(self):
        # date-sorting when no date varies uses object id.
        product = self.factory.makeProduct()
        blueprint1 = self.makeSpec(product)
        blueprint2 = self.makeSpec(product)
        blueprint3 = self.makeSpec(product)
        result = list_result(product)
        self.assertEqual([blueprint1, blueprint2, blueprint3], result)

    def test_priority_sort(self):
        # Sorting by priority works and is the default.
        # When priority is supplied, status is ignored.
        blueprint1 = self.makeSpec(priority=SpecificationPriority.UNDEFINED,
                                   status=SpecificationDefinitionStatus.NEW)
        product = blueprint1.product
        blueprint2 = self.makeSpec(
            product, priority=SpecificationPriority.NOTFORUS,
            status=SpecificationDefinitionStatus.APPROVED)
        blueprint3 = self.makeSpec(
            product, priority=SpecificationPriority.LOW,
            status=SpecificationDefinitionStatus.NEW)
        result = product.specifications(None)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))
        result = product.specifications(None, sort=SpecificationSort.PRIORITY)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))

    def test_priority_sort_fallback_status(self):
        # Sorting by priority falls back to defintion_status.
        # When status is supplied, name is ignored.
        blueprint1 = self.makeSpec(
            status=SpecificationDefinitionStatus.NEW, name='a')
        product = blueprint1.product
        blueprint2 = self.makeSpec(
            product, status=SpecificationDefinitionStatus.APPROVED, name='c')
        blueprint3 = self.makeSpec(
            product, status=SpecificationDefinitionStatus.DISCUSSION, name='b')
        result = product.specifications(None)
        self.assertEqual([blueprint2, blueprint3, blueprint1], list(result))
        result = product.specifications(None, sort=SpecificationSort.PRIORITY)
        self.assertEqual([blueprint2, blueprint3, blueprint1], list(result))

    def test_priority_sort_fallback_name(self):
        # Sorting by priority falls back to name.
        blueprint1 = self.makeSpec(name='b')
        product = blueprint1.product
        blueprint2 = self.makeSpec(product, name='c')
        blueprint3 = self.makeSpec(product, name='a')
        result = product.specifications(None)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))
        result = product.specifications(None, sort=SpecificationSort.PRIORITY)
        self.assertEqual([blueprint3, blueprint1, blueprint2], list(result))

    def test_informational(self):
        # INFORMATIONAL causes only informational specs to be shown.
        enum = SpecificationImplementationStatus
        informational = self.factory.makeSpecification(
            implementation_status=enum.INFORMATIONAL)
        product = informational.product
        plain = self.factory.makeSpecification(product=product)
        result = product.specifications(None)
        self.assertIn(informational, result)
        self.assertIn(plain, result)
        result = product.specifications(
            None, filter=[SpecificationFilter.INFORMATIONAL])
        self.assertIn(informational, result)
        self.assertNotIn(plain, result)

    def test_completeness(self):
        # If COMPLETE is specified, completed specs are listed.  If INCOMPLETE
        # is specified or neither is specified, only incomplete specs are
        # listed.
        enum = SpecificationImplementationStatus
        implemented = self.factory.makeSpecification(
            implementation_status=enum.IMPLEMENTED)
        product = implemented.product
        non_implemented = self.factory.makeSpecification(product=product)
        result = product.specifications(
            None, filter=[SpecificationFilter.COMPLETE])
        self.assertIn(implemented, result)
        self.assertNotIn(non_implemented, result)

        result = product.specifications(
            None, filter=[SpecificationFilter.INCOMPLETE])
        self.assertNotIn(implemented, result)
        self.assertIn(non_implemented, result)
        result = product.specifications(
            None)
        self.assertNotIn(implemented, result)
        self.assertIn(non_implemented, result)

    def test_all(self):
        # ALL causes both complete and incomplete to be listed.
        enum = SpecificationImplementationStatus
        implemented = self.factory.makeSpecification(
            implementation_status=enum.IMPLEMENTED)
        product = implemented.product
        non_implemented = self.factory.makeSpecification(product=product)
        result = product.specifications(None, filter=[SpecificationFilter.ALL])
        self.assertContentEqual([implemented, non_implemented], result)

    def test_valid(self):
        # VALID adjusts COMPLETE to exclude OBSOLETE and SUPERSEDED specs.
        # (INCOMPLETE already excludes OBSOLETE and SUPERSEDED.)
        i_enum = SpecificationImplementationStatus
        d_enum = SpecificationDefinitionStatus
        implemented = self.factory.makeSpecification(
            implementation_status=i_enum.IMPLEMENTED)
        product = implemented.product
        self.factory.makeSpecification(product=product,
                                       status=d_enum.SUPERSEDED)
        self.factory.makeSpecification(product=product, status=d_enum.OBSOLETE)
        filter = [SpecificationFilter.VALID, SpecificationFilter.COMPLETE]
        results = product.specifications(None, filter=filter)
        self.assertContentEqual([implemented], results)

    def test_text_search(self):
        # Text searches work.
        blueprint1 = self.makeSpec(title='abc')
        product = blueprint1.product
        blueprint2 = self.makeSpec(product, title='def')
        result = list_result(product, [u'abc'])
        self.assertEqual([blueprint1], result)
        result = list_result(product, [u'def'])
        self.assertEqual([blueprint2], result)

    def test_proprietary_not_listed(self):
        # Proprietary blueprints are not listed for random users
        blueprint1 = self.makeSpec(
            information_type=InformationType.PROPRIETARY)
        self.assertEqual([], list_result(blueprint1.product))

    def test_proprietary_listed_for_artifact_grant(self):
        # Proprietary blueprints are listed for users with an artifact grant.
        blueprint1 = self.makeSpec(
            information_type=InformationType.PROPRIETARY)
        grant = self.factory.makeAccessArtifactGrant(
            concrete_artifact=blueprint1)
        self.assertEqual(
            [blueprint1],
            list_result(blueprint1.product, user=grant.grantee))

    def test_proprietary_listed_for_policy_grant(self):
        # Proprietary blueprints are listed for users with a policy grant.
        blueprint1 = self.makeSpec(
            information_type=InformationType.PROPRIETARY)
        policy_source = getUtility(IAccessPolicySource)
        (policy,) = policy_source.find(
            [(blueprint1.product, InformationType.PROPRIETARY)])
        grant = self.factory.makeAccessPolicyGrant(policy)
        self.assertEqual(
            [blueprint1],
            list_result(blueprint1.product, user=grant.grantee))


class TestWebService(WebServiceTestCase):

    def test_translations_usage(self):
        """The translations_usage field should be writable."""
        product = self.factory.makeProduct()
        transaction.commit()
        ws_product = self.wsObject(product, product.owner)
        ws_product.translations_usage = ServiceUsage.EXTERNAL.title
        ws_product.lp_save()

    def test_translationpermission(self):
        """The translationpermission field should be writable."""
        product = self.factory.makeProduct()
        transaction.commit()
        ws_product = self.wsObject(product, product.owner)
        ws_product.translationpermission = TranslationPermission.CLOSED.title
        ws_product.lp_save()

    def test_translationgroup(self):
        """The translationgroup field should be writable."""
        product = self.factory.makeProduct()
        group = self.factory.makeTranslationGroup()
        transaction.commit()
        ws_product = self.wsObject(product, product.owner)
        ws_group = self.wsObject(group)
        ws_product.translationgroup = ws_group
        ws_product.lp_save()

    def test_oops_references_matching_product(self):
        # The product layer provides the context restriction, so we need to
        # check we can access context filtered references - e.g. on question.
        oopsid = "OOPS-abcdef1234"
        question = self.factory.makeQuestion(title="Crash with %s" % oopsid)
        product = question.product
        transaction.commit()
        ws_product = self.wsObject(product, product.owner)
        now = datetime.now(tz=pytz.utc)
        day = timedelta(days=1)
        self.failUnlessEqual(
            [oopsid],
            ws_product.findReferencedOOPS(start_date=now - day, end_date=now))
        self.failUnlessEqual(
            [],
            ws_product.findReferencedOOPS(
                start_date=now + day, end_date=now + day))

    def test_oops_references_different_product(self):
        # The product layer provides the context restriction, so we need to
        # check the filter is tight enough - other contexts should not work.
        oopsid = "OOPS-abcdef1234"
        self.factory.makeQuestion(title="Crash with %s" % oopsid)
        product = self.factory.makeProduct()
        transaction.commit()
        ws_product = self.wsObject(product, product.owner)
        now = datetime.now(tz=pytz.utc)
        day = timedelta(days=1)
        self.failUnlessEqual(
            [],
            ws_product.findReferencedOOPS(start_date=now - day, end_date=now))


class TestProductSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeAllInformationTypes(self):
        proprietary = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY)
        embargoed = self.factory.makeProduct(
            information_type=InformationType.EMBARGOED)
        public = self.factory.makeProduct(
            information_type=InformationType.PUBLIC)
        return proprietary, embargoed, public

    @staticmethod
    def filterFind(user):
        clause = ProductSet.getProductPrivacyFilter(user)
        return IStore(Product).find(Product, clause)

    def test_users_private_products(self):
        # Ignore any public products the user may own.
        owner = self.factory.makePerson()
        self.factory.makeProduct(
            information_type=InformationType.PUBLIC,
            owner=owner)
        proprietary = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY,
            owner=owner)
        embargoed = self.factory.makeProduct(
            information_type=InformationType.EMBARGOED,
            owner=owner)
        result = ProductSet.get_users_private_products(owner)
        self.assertIn(proprietary, result)
        self.assertIn(embargoed, result)

    def test_get_all_active_omits_proprietary(self):
        # Ignore proprietary products for anonymous users
        proprietary = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY)
        embargoed = self.factory.makeProduct(
            information_type=InformationType.EMBARGOED)
        result = ProductSet.get_all_active(None)
        self.assertNotIn(proprietary, result)
        self.assertNotIn(embargoed, result)

    def test_search_respects_privacy(self):
        # Proprietary products are filtered from the results for people who
        # cannot see them.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        self.assertIn(product, ProductSet.search(None))
        with person_logged_in(owner):
            product.information_type = InformationType.PROPRIETARY
        self.assertNotIn(product, ProductSet.search(None))
        self.assertIn(product, ProductSet.search(owner))

    def test_getProductPrivacyFilterAnonymous(self):
        # Ignore proprietary products for anonymous users
        proprietary, embargoed, public = self.makeAllInformationTypes()
        result = self.filterFind(None)
        self.assertIn(public, result)
        self.assertNotIn(embargoed, result)
        self.assertNotIn(proprietary, result)

    def test_getProductPrivacyFilter_excludes_random_users(self):
        # Exclude proprietary products for anonymous users
        random = self.factory.makePerson()
        proprietary, embargoed, public = self.makeAllInformationTypes()
        result = self.filterFind(random)
        self.assertIn(public, result)
        self.assertNotIn(embargoed, result)
        self.assertNotIn(proprietary, result)

    def grant(self, pillar, information_type, grantee):
        policy_source = getUtility(IAccessPolicySource)
        (policy,) = policy_source.find(
            [(pillar, information_type)])
        self.factory.makeAccessPolicyGrant(policy, grantee)

    def test_getProductPrivacyFilter_respects_grants(self):
        # Include proprietary products for users with right grants.
        grantee = self.factory.makePerson()
        proprietary, embargoed, public = self.makeAllInformationTypes()
        self.grant(embargoed, InformationType.EMBARGOED, grantee)
        self.grant(proprietary, InformationType.PROPRIETARY, grantee)
        result = self.filterFind(grantee)
        self.assertIn(public, result)
        self.assertIn(embargoed, result)
        self.assertIn(proprietary, result)

    def test_getProductPrivacyFilter_ignores_wrong_product(self):
        # Exclude proprietary products if grant is on wrong product.
        grantee = self.factory.makePerson()
        proprietary, embargoed, public = self.makeAllInformationTypes()
        self.factory.makeAccessPolicyGrant(grantee=grantee)
        result = self.filterFind(grantee)
        self.assertIn(public, result)
        self.assertNotIn(embargoed, result)
        self.assertNotIn(proprietary, result)

    def test_getProductPrivacyFilter_ignores_wrong_info_type(self):
        # Exclude proprietary products if grant is on wrong information type.
        grantee = self.factory.makePerson()
        proprietary, embargoed, public = self.makeAllInformationTypes()
        self.grant(embargoed, InformationType.PROPRIETARY, grantee)
        self.factory.makeAccessPolicy(proprietary, InformationType.EMBARGOED)
        self.grant(proprietary, InformationType.EMBARGOED, grantee)
        result = self.filterFind(grantee)
        self.assertIn(public, result)
        self.assertNotIn(embargoed, result)
        self.assertNotIn(proprietary, result)

    def test_getProductPrivacyFilter_respects_team_grants(self):
        # Include proprietary products for users in teams with right grants.
        grantee = self.factory.makeTeam()
        proprietary, embargoed, public = self.makeAllInformationTypes()
        self.grant(embargoed, InformationType.EMBARGOED, grantee)
        self.grant(proprietary, InformationType.PROPRIETARY, grantee)
        result = self.filterFind(grantee.teamowner)
        self.assertIn(public, result)
        self.assertIn(embargoed, result)
        self.assertIn(proprietary, result)

    def test_getProductPrivacyFilter_includes_admins(self):
        # Launchpad admins can see everything.
        proprietary, embargoed, public = self.makeAllInformationTypes()
        result = self.filterFind(self.factory.makeAdministrator())
        self.assertIn(public, result)
        self.assertIn(embargoed, result)
        self.assertIn(proprietary, result)

    def test_getProductPrivacyFilter_includes_commercial_admins(self):
        # Commercial admins can see everything.
        proprietary, embargoed, public = self.makeAllInformationTypes()
        result = self.filterFind(self.factory.makeCommercialAdmin())
        self.assertIn(public, result)
        self.assertIn(embargoed, result)
        self.assertIn(proprietary, result)


class TestProductSetWebService(WebServiceTestCase):

    def test_latest_honours_privacy(self):
        # Latest lists objects that the user can see, even if proprietary, and
        # skips those the user can't see.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY, owner=owner)
        with person_logged_in(owner):
            name = product.name
        productset = self.wsObject(ProductSet(), owner)
        self.assertIn(name, [p.name for p in productset.latest()])
        productset = self.wsObject(ProductSet(), self.factory.makePerson())
        self.assertNotIn(name, [p.name for p in productset.latest()])

    def test_search_honours_privacy(self):
        # search lists objects that the user can see, even if proprietary, and
        # skips those the user can't see.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            information_type=InformationType.PROPRIETARY, owner=owner)
        with person_logged_in(owner):
            name = product.name
        productset = self.wsObject(ProductSet(), owner)
        self.assertIn(name, [p.name for p in productset.search()])
        productset = self.wsObject(ProductSet(), self.factory.makePerson())
        self.assertNotIn(name, [p.name for p in productset.search()])
