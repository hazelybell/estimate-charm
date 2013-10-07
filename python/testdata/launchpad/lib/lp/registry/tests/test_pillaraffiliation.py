# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for adapters."""

__metaclass__ = type

from storm.store import Store
from testtools.matchers import Equals
from zope.component import getUtility

from lp.registry.model.pillaraffiliation import IHasAffiliation
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount


class TestPillarAffiliation(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_distro_badge_icon(self):
        # A distro's icon is used for the badge if present.
        person = self.factory.makePerson()
        icon = self.factory.makeLibraryFileAlias(
            filename='smurf.png', content_type='image/png')
        distro = self.factory.makeDistribution(
            owner=person, name='pting', icon=icon)
        [badges] = IHasAffiliation(distro).getAffiliationBadges([person])
        self.assertEqual((icon.getURL(), "Pting", "maintainer"), badges[0])

    def _check_affiliated_with_distro(self, person, distro, role):
        [badges] = IHasAffiliation(distro).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/distribution-badge", "Pting", role), badges[0])

    def test_distro_owner_affiliation(self):
        # A person who owns a distro is affiliated.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=person, name='pting')
        self._check_affiliated_with_distro(person, distro, 'maintainer')

    def test_distro_driver_affiliation(self):
        # A person who is a distro driver is affiliated.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(driver=person, name='pting')
        self._check_affiliated_with_distro(person, distro, 'driver')

    def test_distro_team_driver_affiliation(self):
        # A person who is a member of the distro driver team is affiliated.
        person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        distro = self.factory.makeDistribution(driver=team, name='pting')
        self._check_affiliated_with_distro(person, distro, 'driver')

    def test_no_distro_bug_supervisor_affiliation(self):
        # A person who is the bug supervisor for a distro is not affiliated
        # for simple distro affiliation checks.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(bug_supervisor=person)
        self.assertEqual(
            [], IHasAffiliation(distro).getAffiliationBadges([person])[0])

    def test_product_badge_icon(self):
        # A product's icon is used for the badge if present.
        person = self.factory.makePerson()
        icon = self.factory.makeLibraryFileAlias(
            filename='smurf.png', content_type='image/png')
        product = self.factory.makeProduct(
            owner=person, name='pting', icon=icon)
        [badges] = IHasAffiliation(product).getAffiliationBadges([person])
        self.assertEqual((icon.getURL(), "Pting", "maintainer"), badges[0])

    def test_pillar_badge_icon(self):
        # A pillar's icon is used for the badge if the context has no icon.
        person = self.factory.makePerson()
        icon = self.factory.makeLibraryFileAlias(
            filename='smurf.png', content_type='image/png')
        product = self.factory.makeProduct(
            owner=person, name='pting', icon=icon)
        bugtask = self.factory.makeBugTask(target=product)
        [badges] = IHasAffiliation(bugtask).getAffiliationBadges([person])
        self.assertEqual((icon.getURL(), "Pting", "maintainer"), badges[0])

    def _check_affiliated_with_product(self, person, product, role):
        [badges] = IHasAffiliation(product).getAffiliationBadges([person])
        self.assertEqual(("/@@/product-badge", "Pting", role), badges[0])

    def test_product_driver_affiliation(self):
        # A person who is the driver for a product is affiliated.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(driver=person, name='pting')
        self._check_affiliated_with_product(person, product, 'driver')

    def test_product_team_driver_affiliation(self):
        # A person who is a member of the product driver team is affiliated.
        person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        product = self.factory.makeProduct(driver=team, name='pting')
        self._check_affiliated_with_product(person, product, 'driver')

    def test_product_group_driver_affiliation(self):
        # A person who is the driver for a product's group is affiliated.
        person = self.factory.makePerson()
        project = self.factory.makeProject(driver=person)
        product = self.factory.makeProduct(project=project, name='pting')
        self._check_affiliated_with_product(person, product, 'driver')

    def test_no_product_bug_supervisor_affiliation(self):
        # A person who is the bug supervisor for a product is is not
        # affiliated for simple product affiliation checks.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(bug_supervisor=person)
        self.assertEqual(
            [], IHasAffiliation(product).getAffiliationBadges([person])[0])

    def test_product_owner_affiliation(self):
        # A person who owns a product is affiliated.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(owner=person, name='pting')
        self._check_affiliated_with_product(person, product, 'maintainer')

    def test_distro_affiliation_multiple_people(self):
        # A collection of people associated with a distro are affiliated.
        people = [self.factory.makePerson() for x in range(3)]
        distro = self.factory.makeDistribution(owner=people[0],
                                               driver=people[1],
                                               name='pting')
        person_badges = IHasAffiliation(distro).getAffiliationBadges(people)
        self.assertEqual(
            [("/@@/distribution-badge", "Pting", "maintainer")],
            person_badges[0])
        self.assertEqual(
            [("/@@/distribution-badge", "Pting", "driver")], person_badges[1])
        self.assertEqual([], person_badges[2])

    def test_product_affiliation_query_count(self):
        # Only 2 queries are expected, selects from:
        # - Product, Person
        person = self.factory.makePerson()
        product = self.factory.makeProduct(owner=person, name='pting')
        Store.of(product).invalidate()
        with StormStatementRecorder() as recorder:
            IHasAffiliation(product).getAffiliationBadges([person])
        self.assertThat(recorder, HasQueryCount(Equals(4)))

    def test_distro_affiliation_query_count(self):
        # Only 2 business queries are expected, selects from:
        # - Distribution, Person
        # plus an additional query to create a PublisherConfig record.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=person, name='pting')
        Store.of(distro).invalidate()
        with StormStatementRecorder() as recorder:
            IHasAffiliation(distro).getAffiliationBadges([person])
        self.assertThat(recorder, HasQueryCount(Equals(3)))


class _TestBugTaskorBranchMixin:

    def test_distro_bug_supervisor_affiliation(self):
        # A person who is the bug supervisor for a distro is affiliated.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(
            bug_supervisor=person, name='pting')
        self._check_affiliated_with_distro(person, distro, 'bug supervisor')

    def test_product_bug_supervisor_affiliation(self):
        # A person who is the bug supervisor for a distro is affiliated.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(
            bug_supervisor=person, name='pting')
        self._check_affiliated_with_product(person, product, 'bug supervisor')


class TestBugTaskPillarAffiliation(_TestBugTaskorBranchMixin,
                                   TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_correct_pillars_are_used(self):
        bugtask = self.factory.makeBugTask()
        adapter = IHasAffiliation(bugtask)
        pillars = [bugtask.pillar for bugtask in bugtask.bug.bugtasks]
        self.assertEqual(pillars, adapter.getPillars())

    def _check_affiliated_with_distro(self, person, target, role):
        bugtask = self.factory.makeBugTask(target=target)
        [badges] = IHasAffiliation(bugtask).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/distribution-badge", "Pting", role), badges[0])

    def _check_affiliated_with_product(self, person, target, role):
        bugtask = self.factory.makeBugTask(target=target)
        [badges] = IHasAffiliation(bugtask).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/product-badge", "Pting", role), badges[0])

    def test_affiliated_with_multiple_bugtasks(self):
        # When a bugtask belongs to a bug which has other bugtasks, all such
        # bugtasks are checked for affiliation.
        person = self.factory.makePerson()
        bug = self.factory.makeBug()
        expected_affiliations = []
        for x in range(3):
            bug_supervisor = None
            if x == 0:
                bug_supervisor = person
            product = self.factory.makeProduct(
                owner=person, bug_supervisor=bug_supervisor)
            self.factory.makeBugTask(bug=bug, target=product)
            expected_affiliations.append(
                ("/@@/product-badge", product.displayname, "maintainer"))
            expected_affiliations.append(
                ("/@@/product-badge", product.displayname, "driver"))
            if x == 0:
                expected_affiliations.append(
                    ("/@@/product-badge",
                     product.displayname, "bug supervisor"))
        [badges] = IHasAffiliation(
            bug.default_bugtask).getAffiliationBadges([person])
        self.assertContentEqual(expected_affiliations, badges)


class TestBranchPillarAffiliation(_TestBugTaskorBranchMixin,
                                  TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_correct_pillars_are_used(self):
        branch = self.factory.makeBranch()
        adapter = IHasAffiliation(branch)
        self.assertEqual([branch.product], adapter.getPillars())

    def test_personal_branches_have_no_pillars(self):
        branch = self.factory.makeBranch(product=None)
        adapter = IHasAffiliation(branch)
        self.assertEqual([], adapter.getPillars())

    def test_getBranch(self):
        # The branch is the context.
        branch = self.factory.makeBranch()
        adapter = IHasAffiliation(branch)
        self.assertEqual(branch, adapter.getBranch())

    def test_branch_trusted_reviewer_affiliation(self):
        # A person who is the branch's trusted reviewer is affiliated.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(name='pting')
        self._check_affiliated_with_product(
            person, product, 'trusted reviewer')

    def _check_affiliated_with_distro(self, person, target, role):
        distroseries = self.factory.makeDistroSeries(distribution=target)
        sp = self.factory.makeSourcePackage(distroseries=distroseries)
        branch = self.factory.makeBranch(sourcepackage=sp)
        [badges] = IHasAffiliation(branch).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/distribution-badge", "Pting", role), badges[0])

    def _check_affiliated_with_product(self, person, target, role):
        branch = self.factory.makeBranch(product=target)
        with person_logged_in(branch.owner):
            branch.reviewer = person
        [badges] = IHasAffiliation(branch).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/product-badge", "Pting", role), badges[0])


class CodeReviewVotePillarAffiliationTestCase(TestBranchPillarAffiliation):

    layer = DatabaseFunctionalLayer

    def makeCodeReviewVote(self, branch):
        merge_proposal = self.factory.makeBranchMergeProposal(
            target_branch=branch)
        reviewer = self.factory.makePerson()
        with person_logged_in(merge_proposal.registrant):
            vote = merge_proposal.nominateReviewer(
                reviewer, merge_proposal.registrant)
        return vote

    def test_correct_pillars_are_used(self):
        branch = self.factory.makeBranch()
        vote = self.makeCodeReviewVote(branch)
        adapter = IHasAffiliation(vote)
        self.assertEqual([branch.product], adapter.getPillars())

    def test_getBranch(self):
        # The code review vote's target branch is the branch.
        branch = self.factory.makeBranch()
        vote = self.makeCodeReviewVote(branch)
        adapter = IHasAffiliation(vote)
        self.assertEqual(branch, adapter.getBranch())

    def _check_affiliated_with_distro(self, person, target, role):
        distroseries = self.factory.makeDistroSeries(distribution=target)
        sp = self.factory.makeSourcePackage(distroseries=distroseries)
        branch = self.factory.makeBranch(sourcepackage=sp)
        vote = self.makeCodeReviewVote(branch)
        [badges] = IHasAffiliation(vote).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/distribution-badge", "Pting", role), badges[0])

    def _check_affiliated_with_product(self, person, target, role):
        branch = self.factory.makeBranch(product=target)
        with person_logged_in(branch.owner):
            branch.reviewer = person
        vote = self.makeCodeReviewVote(branch)
        [badges] = IHasAffiliation(vote).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/product-badge", "Pting", role), badges[0])


class TestDistroSeriesPillarAffiliation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_correct_pillars_are_used(self):
        series = self.factory.makeDistroSeries()
        adapter = IHasAffiliation(series)
        self.assertEqual([series.distribution], adapter.getPillars())

    def test_driver_affiliation(self):
        # A person who is the driver for a distroseries is affiliated.
        # Here, the affiliation is with the distribution of the series.
        owner = self.factory.makePerson()
        driver = self.factory.makePerson()
        distribution = self.factory.makeDistribution(
            owner=owner, driver=driver, name='pting')
        distroseries = self.factory.makeDistroSeries(
            registrant=driver, distribution=distribution)
        [badges] = IHasAffiliation(
            distroseries).getAffiliationBadges([driver])
        self.assertEqual(
            ("/@@/distribution-badge", "Pting", "driver"), badges[0])

    def test_distro_driver_affiliation(self):
        # A person who is the driver for a distroseries' distro is affiliated.
        # Here, the affiliation is with the distribution of the series.
        owner = self.factory.makePerson()
        driver = self.factory.makePerson()
        distribution = self.factory.makeDistribution(
            owner=owner, driver=driver, name='pting')
        distroseries = self.factory.makeDistroSeries(
            registrant=owner, distribution=distribution)
        [badges] = IHasAffiliation(
            distroseries).getAffiliationBadges([driver])
        self.assertEqual(
            ("/@@/distribution-badge", "Pting", "driver"), badges[0])


class TestProductSeriesPillarAffiliation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_correct_pillars_are_used(self):
        series = self.factory.makeProductSeries()
        adapter = IHasAffiliation(series)
        self.assertEqual([series.product], adapter.getPillars())

    def test_driver_affiliation(self):
        # A person who is the driver for a productseries is affiliated.
        # Here, the affiliation is with the product.
        owner = self.factory.makePerson()
        driver = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, driver=driver, name='pting')
        productseries = self.factory.makeProductSeries(
            owner=driver, product=product)
        [badges] = (
            IHasAffiliation(productseries).getAffiliationBadges([driver]))
        self.assertEqual(
            ("/@@/product-badge", "Pting", "driver"), badges[0])

    def test_product_driver_affiliation(self):
        # A person who is the driver for a productseries' product is
        # affiliated. Here, the affiliation is with the product.
        owner = self.factory.makePerson()
        driver = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, driver=driver, name='pting')
        productseries = self.factory.makeProductSeries(
            owner=owner, product=product)
        [badges] = (
            IHasAffiliation(productseries).getAffiliationBadges([driver]))
        self.assertEqual(
            ("/@@/product-badge", "Pting", "driver"), badges[0])

    def test_product_group_driver_affiliation(self):
        # A person who is the driver for a productseries' product's group is
        # affiliated. Here, the affiliation is with the product.
        owner = self.factory.makePerson()
        driver = self.factory.makePerson()
        project = self.factory.makeProject(driver=driver)
        product = self.factory.makeProduct(
            owner=owner, project=project, name='pting')
        productseries = self.factory.makeProductSeries(
            owner=owner, product=product)
        [badges] = (
            IHasAffiliation(productseries).getAffiliationBadges([driver]))
        self.assertEqual(
            ("/@@/product-badge", "Pting", "driver"), badges[0])


class TestQuestionPillarAffiliation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_correct_pillars_are_used_for_product(self):
        product = self.factory.makeProduct()
        question = self.factory.makeQuestion(target=product)
        adapter = IHasAffiliation(question)
        self.assertEqual([question.product], adapter.getPillars())

    def test_correct_pillars_are_used_for_distribution(self):
        distribution = self.factory.makeDistribution()
        question = self.factory.makeQuestion(target=distribution)
        adapter = IHasAffiliation(question)
        self.assertEqual([question.distribution], adapter.getPillars())

    def test_correct_pillars_are_used_for_distro_sourcepackage(self):
        distribution = self.factory.makeDistribution()
        distro_sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=distribution)
        owner = self.factory.makePerson()
        question = self.factory.makeQuestion(
            target=distro_sourcepackage, owner=owner)
        adapter = IHasAffiliation(question)
        self.assertEqual([distribution], adapter.getPillars())

    def test_answer_contact_affiliation_for_distro(self):
        # A person is affiliated if they are an answer contact for a distro
        # target.
        answer_contact = self.factory.makePerson()
        english = getUtility(ILanguageSet)['en']
        answer_contact.addLanguage(english)
        distro = self.factory.makeDistribution(owner=answer_contact)
        with person_logged_in(answer_contact):
            distro.addAnswerContact(answer_contact, answer_contact)
        question = self.factory.makeQuestion(target=distro)
        [badges] = (
            IHasAffiliation(question).getAffiliationBadges([answer_contact]))
        self.assertEqual(
            ("/@@/distribution-badge", distro.displayname,
             "maintainer"), badges[0])
        self.assertEqual(
            ("/@@/distribution-badge", distro.displayname,
             "driver"), badges[1])
        self.assertEqual(
            ("/@@/distribution-badge", distro.displayname,
             "answer contact"), badges[2])

    def test_answer_contact_affiliation_for_distro_sourcepackage(self):
        # A person is affiliated if they are an answer contact for a dsp
        # target.
        answer_contact = self.factory.makePerson()
        english = getUtility(ILanguageSet)['en']
        answer_contact.addLanguage(english)
        distribution = self.factory.makeDistribution(owner=answer_contact)
        distro_sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=distribution)
        with person_logged_in(answer_contact):
            distro_sourcepackage.addAnswerContact(
                answer_contact, answer_contact)
        question = self.factory.makeQuestion(
            target=distro_sourcepackage, owner=answer_contact)
        [badges] = (
            IHasAffiliation(question).getAffiliationBadges([answer_contact]))
        self.assertEqual(
            ("/@@/distribution-badge", distribution.displayname,
             "maintainer"), badges[0])
        self.assertEqual(
            ("/@@/distribution-badge", distribution.displayname,
             "driver"), badges[1])
        self.assertEqual(
            ("/@@/distribution-badge", distro_sourcepackage.displayname,
             "answer contact"), badges[2])

    def test_answer_contact_affiliation_for_distro_sourcepackage_distro(self):
        # A person is affiliated if they are an answer contact for a dsp
        # target's distro.
        answer_contact = self.factory.makePerson()
        english = getUtility(ILanguageSet)['en']
        answer_contact.addLanguage(english)
        distribution = self.factory.makeDistribution(owner=answer_contact)
        distro_sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=distribution)
        with person_logged_in(answer_contact):
            distribution.addAnswerContact(answer_contact, answer_contact)
        question = self.factory.makeQuestion(
            target=distro_sourcepackage, owner=answer_contact)
        [badges] = (
            IHasAffiliation(question).getAffiliationBadges([answer_contact]))
        self.assertEqual(
            ("/@@/distribution-badge", distribution.displayname,
             "maintainer"), badges[0])
        self.assertEqual(
            ("/@@/distribution-badge", distribution.displayname,
             "driver"), badges[1])
        self.assertEqual(
            ("/@@/distribution-badge", distribution.displayname,
             "answer contact"), badges[2])

    def test_answer_contact_affiliation_for_product(self):
        # A person is affiliated if they are an answer contact for a product
        # target.
        answer_contact = self.factory.makePerson()
        english = getUtility(ILanguageSet)['en']
        answer_contact.addLanguage(english)
        product = self.factory.makeProduct()
        with person_logged_in(answer_contact):
            product.addAnswerContact(answer_contact, answer_contact)
        question = self.factory.makeQuestion(target=product)
        [badges] = (
            IHasAffiliation(question).getAffiliationBadges([answer_contact]))
        self.assertEqual(
            ("/@@/product-badge", product.displayname, "answer contact"),
            badges[0])

    def test_product_affiliation(self):
        # A person is affiliated if they are affiliated with the product.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(owner=person)
        question = self.factory.makeQuestion(target=product)
        [badges] = IHasAffiliation(question).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/product-badge", product.displayname, "maintainer"),
            badges[0])

    def test_distribution_affiliation(self):
        # A person is affiliated if they are affiliated with the distribution.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=person)
        question = self.factory.makeQuestion(target=distro)
        [badges] = IHasAffiliation(question).getAffiliationBadges([person])
        self.assertEqual(
            ("/@@/distribution-badge", distro.displayname, "maintainer"),
            badges[0])


class TestSpecificationPillarAffiliation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_correct_pillars_are_used_for_product(self):
        product = self.factory.makeProduct()
        specification = self.factory.makeSpecification(product=product)
        adapter = IHasAffiliation(specification)
        self.assertEqual([specification.product], adapter.getPillars())

    def test_correct_pillars_are_used_for_distribution(self):
        distro = self.factory.makeDistribution()
        specification = self.factory.makeSpecification(distribution=distro)
        adapter = IHasAffiliation(specification)
        self.assertEqual([specification.distribution], adapter.getPillars())

    def test_product_affiliation(self):
        # A person is affiliated if they are affiliated with the pillar.
        person = self.factory.makePerson()
        product = self.factory.makeProduct(owner=person)
        specification = self.factory.makeSpecification(product=product)
        [badges] = (
            IHasAffiliation(specification).getAffiliationBadges([person]))
        self.assertEqual(
            ("/@@/product-badge", product.displayname, "maintainer"),
            badges[0])

    def test_distribution_affiliation(self):
        # A person is affiliated if they are affiliated with the distribution.
        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=person)
        specification = self.factory.makeSpecification(distribution=distro)
        [badges] = (
            IHasAffiliation(specification).getAffiliationBadges([person]))
        self.assertEqual(
            ("/@@/distribution-badge", distro.displayname, "maintainer"),
            badges[0])
