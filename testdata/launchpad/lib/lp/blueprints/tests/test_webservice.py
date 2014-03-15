# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Webservice unit tests related to Launchpad blueprints."""

__metaclass__ = type

import transaction
from zope.security.management import endInteraction
from zope.security.proxy import removeSecurityProxy

from lp.blueprints.enums import SpecificationDefinitionStatus
from lp.services.webapp.interaction import ANONYMOUS
from lp.testing import (
    launchpadlib_for,
    person_logged_in,
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.layers import (
    AppServerLayer,
    DatabaseFunctionalLayer,
    )
from lp.testing.pages import (
    LaunchpadWebServiceCaller,
    webservice_for_person,
    )


class SpecificationWebserviceTestCase(TestCaseWithFactory):

    def getLaunchpadlib(self):
        user = self.factory.makePerson()
        return launchpadlib_for("testing", user, version='devel')

    def getSpecOnWebservice(self, spec_object):
        launchpadlib = self.getLaunchpadlib()
        # Ensure that there is an interaction so that the security
        # checks for spec_object work.
        with person_logged_in(ANONYMOUS):
            url = '/%s/+spec/%s' % (spec_object.target.name, spec_object.name)
        result = launchpadlib.load(url)
        return result

    def getPillarOnWebservice(self, pillar_obj):
        pillar_name = pillar_obj.name
        launchpadlib = self.getLaunchpadlib()
        return launchpadlib.load(pillar_name)


class SpecificationAttributeWebserviceTests(SpecificationWebserviceTestCase):
    """Test accessing specification attributes over the webservice."""
    layer = AppServerLayer

    def test_representation_is_empty_on_1_dot_0(self):
        # ISpecification is exposed on the 1.0 version so that they can be
        # linked against branches, but none of its fields is exposed on that
        # version as we expect it to undergo significant refactorings before
        # it's ready for prime time.
        spec = self.factory.makeSpecification()
        user = self.factory.makePerson()
        url = '/%s/+spec/%s' % (spec.product.name, spec.name)
        webservice = webservice_for_person(user)
        response = webservice.get(url)
        expected_keys = [u'self_link', u'http_etag', u'resource_type_link',
                         u'web_link', u'information_type']
        self.assertEqual(response.status, 200)
        self.assertContentEqual(expected_keys, response.jsonBody().keys())

    def test_representation_contains_name(self):
        spec = self.factory.makeSpecification()
        spec_name = spec.name
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_name, spec_webservice.name)

    def test_representation_contains_target(self):
        spec = self.factory.makeSpecification(
            product=self.factory.makeProduct())
        spec_target_name = spec.target.name
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_target_name, spec_webservice.target.name)

    def test_representation_contains_title(self):
        spec = self.factory.makeSpecification(title='Foo')
        spec_title = spec.title
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_title, spec_webservice.title)

    def test_representation_contains_specification_url(self):
        spec = self.factory.makeSpecification(specurl='http://example.com')
        spec_specurl = spec.specurl
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_specurl, spec_webservice.specification_url)

    def test_representation_contains_summary(self):
        spec = self.factory.makeSpecification(summary='Foo')
        spec_summary = spec.summary
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_summary, spec_webservice.summary)

    def test_representation_contains_implementation_status(self):
        spec = self.factory.makeSpecification()
        spec_implementation_status = spec.implementation_status
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(
            spec_implementation_status.title,
            spec_webservice.implementation_status)

    def test_representation_contains_definition_status(self):
        spec = self.factory.makeSpecification()
        spec_definition_status = spec.definition_status
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(
            spec_definition_status.title, spec_webservice.definition_status)

    def test_representation_contains_assignee(self):
        # Hard-code the person's name or else we'd need to set up a zope
        # interaction as IPerson.name is protected.
        spec = self.factory.makeSpecification(
            assignee=self.factory.makePerson(name='test-person'))
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual('test-person', spec_webservice.assignee.name)

    def test_representation_contains_drafter(self):
        spec = self.factory.makeSpecification(
            drafter=self.factory.makePerson(name='test-person'))
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual('test-person', spec_webservice.drafter.name)

    def test_representation_contains_approver(self):
        spec = self.factory.makeSpecification(
            approver=self.factory.makePerson(name='test-person'))
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual('test-person', spec_webservice.approver.name)

    def test_representation_contains_owner(self):
        spec = self.factory.makeSpecification(
            owner=self.factory.makePerson(name='test-person'))
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual('test-person', spec_webservice.owner.name)

    def test_representation_contains_priority(self):
        spec = self.factory.makeSpecification()
        spec_priority = spec.priority
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_priority.title, spec_webservice.priority)

    def test_representation_contains_date_created(self):
        spec = self.factory.makeSpecification()
        spec_datecreated = spec.datecreated
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_datecreated, spec_webservice.date_created)

    def test_representation_contains_whiteboard(self):
        spec = self.factory.makeSpecification(whiteboard='Test')
        spec_whiteboard = spec.whiteboard
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(spec_whiteboard, spec_webservice.whiteboard)

    def test_representation_contains_workitems(self):
        work_item = self.factory.makeSpecificationWorkItem()
        spec_webservice = self.getSpecOnWebservice(work_item.specification)
        self.assertEqual(work_item.specification.workitems_text,
                         spec_webservice.workitems_text)

    def test_representation_contains_milestone(self):
        product = self.factory.makeProduct()
        productseries = self.factory.makeProductSeries(product=product)
        milestone = self.factory.makeMilestone(
            name="1.0", product=product, productseries=productseries)
        spec_object = self.factory.makeSpecification(
            product=product, goal=productseries, milestone=milestone)
        spec = self.getSpecOnWebservice(spec_object)
        self.assertEqual("1.0", spec.milestone.name)

    def test_representation_contains_dependencies(self):
        spec = self.factory.makeSpecification()
        spec2 = self.factory.makeSpecification()
        spec2_name = spec2.name
        spec.createDependency(spec2)
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(1, spec_webservice.dependencies.total_size)
        self.assertEqual(spec2_name, spec_webservice.dependencies[0].name)

    def test_representation_contains_linked_branches(self):
        spec = self.factory.makeSpecification()
        branch = self.factory.makeBranch()
        person = self.factory.makePerson()
        spec.linkBranch(branch, person)
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(1, spec_webservice.linked_branches.total_size)

    def test_representation_contains_bug_links(self):
        spec = self.factory.makeSpecification()
        bug = self.factory.makeBug()
        person = self.factory.makePerson()
        with person_logged_in(person):
            spec.linkBug(bug)
        spec_webservice = self.getSpecOnWebservice(spec)
        self.assertEqual(1, spec_webservice.bugs.total_size)
        self.assertEqual(bug.id, spec_webservice.bugs[0].id)


class SpecificationTargetTests(SpecificationWebserviceTestCase):
    """Tests for accessing specifications via their targets."""
    layer = AppServerLayer

    def test_get_specification_on_product(self):
        product = self.factory.makeProduct(name="fooix")
        self.factory.makeSpecification(
            product=product, name="some-spec")
        product_on_webservice = self.getPillarOnWebservice(product)
        spec = product_on_webservice.getSpecification(name="some-spec")
        self.assertEqual("some-spec", spec.name)
        self.assertEqual("fooix", spec.target.name)

    def test_get_specification_on_distribution(self):
        distribution = self.factory.makeDistribution(name="foobuntu")
        self.factory.makeSpecification(
            distribution=distribution, name="some-spec")
        distro_on_webservice = self.getPillarOnWebservice(distribution)
        spec = distro_on_webservice.getSpecification(name="some-spec")
        self.assertEqual("some-spec", spec.name)
        self.assertEqual("foobuntu", spec.target.name)

    def test_get_specification_on_productseries(self):
        product = self.factory.makeProduct(name="fooix")
        productseries = self.factory.makeProductSeries(
            product=product, name="fooix-dev")
        self.factory.makeSpecification(
            product=product, name="some-spec", goal=productseries)
        product_on_webservice = self.getPillarOnWebservice(product)
        productseries_on_webservice = product_on_webservice.getSeries(
            name="fooix-dev")
        spec = productseries_on_webservice.getSpecification(name="some-spec")
        self.assertEqual("some-spec", spec.name)
        self.assertEqual("fooix", spec.target.name)

    def test_get_specification_on_distroseries(self):
        distribution = self.factory.makeDistribution(name="foobuntu")
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution, name="maudlin")
        self.factory.makeSpecification(
            distribution=distribution, name="some-spec",
            goal=distroseries)
        distro_on_webservice = self.getPillarOnWebservice(distribution)
        distroseries_on_webservice = distro_on_webservice.getSeries(
            name_or_version="maudlin")
        spec = distroseries_on_webservice.getSpecification(name="some-spec")
        self.assertEqual("some-spec", spec.name)
        self.assertEqual("foobuntu", spec.target.name)

    def test_get_specification_not_found(self):
        product = self.factory.makeProduct()
        product_on_webservice = self.getPillarOnWebservice(product)
        spec = product_on_webservice.getSpecification(name="nonexistant")
        self.assertEqual(None, spec)


class IHasSpecificationsTests(SpecificationWebserviceTestCase):
    """Tests for accessing IHasSpecifications methods over the webservice."""
    layer = DatabaseFunctionalLayer

    def assertNamesOfSpecificationsAre(self, expected_names, specifications):
        names = [s.name for s in specifications]
        self.assertContentEqual(expected_names, names)

    def test_anonymous_access_to_collection(self):
        product = self.factory.makeProduct()
        self.factory.makeSpecification(product=product, name="spec1")
        self.factory.makeSpecification(product=product, name="spec2")
        # Need to endInteraction() because launchpadlib_for_anonymous() will
        # setup a new one.
        endInteraction()
        lplib = launchpadlib_for('lplib-test', person=None, version='devel')
        ws_product = ws_object(lplib, removeSecurityProxy(product))
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], ws_product.all_specifications)

    def test_product_all_specifications(self):
        product = self.factory.makeProduct()
        self.factory.makeSpecification(product=product, name="spec1")
        self.factory.makeSpecification(product=product, name="spec2")
        product_on_webservice = self.getPillarOnWebservice(product)
        self.assertNamesOfSpecificationsAre(
            ["spec1", "spec2"], product_on_webservice.all_specifications)

    def test_distribution_valid_specifications(self):
        distribution = self.factory.makeDistribution()
        self.factory.makeSpecification(
            distribution=distribution, name="spec1")
        self.factory.makeSpecification(
            distribution=distribution, name="spec2",
            status=SpecificationDefinitionStatus.OBSOLETE)
        distro_on_webservice = self.getPillarOnWebservice(distribution)
        self.assertNamesOfSpecificationsAre(
            ["spec1"], distro_on_webservice.valid_specifications)


class TestSpecificationSubscription(SpecificationWebserviceTestCase):

    layer = AppServerLayer

    def test_subscribe(self):
        # Test subscribe() API.
        with person_logged_in(ANONYMOUS):
            db_spec = self.factory.makeSpecification()
            db_person = self.factory.makePerson()
            launchpad = self.factory.makeLaunchpadService()

        spec = ws_object(launchpad, db_spec)
        person = ws_object(launchpad, db_person)
        spec.subscribe(person=person, essential=True)
        transaction.commit()

        # Check the results.
        sub = db_spec.subscription(db_person)
        self.assertIsNot(None, sub)
        self.assertTrue(sub.essential)

    def test_unsubscribe(self):
        # Test unsubscribe() API.
        with person_logged_in(ANONYMOUS):
            db_spec = self.factory.makeBlueprint()
            db_person = self.factory.makePerson()
            db_spec.subscribe(person=db_person)
            launchpad = self.factory.makeLaunchpadService(person=db_person)

        spec = ws_object(launchpad, db_spec)
        person = ws_object(launchpad, db_person)
        spec.unsubscribe(person=person)
        transaction.commit()

        # Check the results.
        self.assertFalse(db_spec.isSubscribed(db_person))

    def test_canBeUnsubscribedByUser(self):
        # Test canBeUnsubscribedByUser() API.
        webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything',
            domain='api.launchpad.dev:8085')

        with person_logged_in(ANONYMOUS):
            db_spec = self.factory.makeSpecification()
            db_person = self.factory.makePerson()
            launchpad = self.factory.makeLaunchpadService()

            spec = ws_object(launchpad, db_spec)
            person = ws_object(launchpad, db_person)
            subscription = spec.subscribe(person=person, essential=True)
            transaction.commit()

        result = webservice.named_get(
            subscription['self_link'], 'canBeUnsubscribedByUser').jsonBody()
        self.assertTrue(result)


class TestSpecificationBugLinks(SpecificationWebserviceTestCase):

    layer = AppServerLayer

    def test_bug_linking(self):
        # Set up a spec, person, and bug.
        with person_logged_in(ANONYMOUS):
            db_spec = self.factory.makeSpecification()
            db_person = self.factory.makePerson()
            db_bug = self.factory.makeBug()
            launchpad = self.factory.makeLaunchpadService()

        # Link the bug to the spec via the web service.
        with person_logged_in(db_person):
            spec = ws_object(launchpad, db_spec)
            bug = ws_object(launchpad, db_bug)
            # There are no bugs associated with the spec/blueprint yet.
            self.assertEqual(0, spec.bugs.total_size)
            spec.linkBug(bug=bug)
            transaction.commit()

        # The spec now has one bug associated with it and that bug is the one
        # we linked.
        self.assertEqual(1, spec.bugs.total_size)
        self.assertEqual(bug.id, spec.bugs[0].id)

    def test_bug_unlinking(self):
        # Set up a spec, person, and bug, then link the bug to the spec.
        with person_logged_in(ANONYMOUS):
            db_spec = self.factory.makeBlueprint()
            db_person = self.factory.makePerson()
            db_bug = self.factory.makeBug()
            launchpad = self.factory.makeLaunchpadService(person=db_person)

        spec = ws_object(launchpad, db_spec)
        bug = ws_object(launchpad, db_bug)
        spec.linkBug(bug=bug)

        # There is only one bug linked at the moment.
        self.assertEqual(1, spec.bugs.total_size)

        spec.unlinkBug(bug=bug)
        transaction.commit()

        # Now that we've unlinked the bug, there are no linked bugs at all.
        self.assertEqual(0, spec.bugs.total_size)


class TestSpecificationGoalHandling(SpecificationWebserviceTestCase):

    layer = AppServerLayer

    def setUp(self):
        super(TestSpecificationGoalHandling, self).setUp()
        self.driver = self.factory.makePerson()
        self.proposer = self.factory.makePerson()
        self.product = self.factory.makeProduct(driver=self.driver)
        self.series = self.factory.makeProductSeries(product=self.product)

    def test_goal_propose_and_accept(self):
        # Webservice clients can propose and accept spec series goals.
        db_spec = self.factory.makeBlueprint(product=self.product,
                                             owner=self.proposer)
        # Propose for series goal
        with person_logged_in(self.proposer):
            launchpad = self.factory.makeLaunchpadService(person=self.proposer)
            spec = ws_object(launchpad, db_spec)
            series = ws_object(launchpad, self.series)
            spec.proposeGoal(goal=series)
            transaction.commit()
            self.assertEqual(db_spec.goal, self.series)
            self.assertFalse(spec.has_accepted_goal)

        # Accept series goal
        with person_logged_in(self.driver):
            launchpad = self.factory.makeLaunchpadService(person=self.driver)
            spec = ws_object(launchpad, db_spec)
            spec.acceptGoal()
            transaction.commit()
            self.assertTrue(spec.has_accepted_goal)

    def test_goal_propose_decline_and_clear(self):
        # Webservice clients can decline and clear spec series goals.
        db_spec = self.factory.makeBlueprint(product=self.product,
                                             owner=self.proposer)
        # Propose for series goal
        with person_logged_in(self.proposer):
            launchpad = self.factory.makeLaunchpadService(person=self.proposer)
            spec = ws_object(launchpad, db_spec)
            series = ws_object(launchpad, self.series)
            spec.proposeGoal(goal=series)
            transaction.commit()
            self.assertEqual(db_spec.goal, self.series)
            self.assertFalse(spec.has_accepted_goal)

        with person_logged_in(self.driver):
            # Decline series goal
            launchpad = self.factory.makeLaunchpadService(person=self.driver)
            spec = ws_object(launchpad, db_spec)
            spec.declineGoal()
            transaction.commit()
            self.assertFalse(spec.has_accepted_goal)
            self.assertEqual(db_spec.goal, self.series)

            # Clear series goal as a driver
            spec.proposeGoal(goal=None)
            transaction.commit()
            self.assertIsNone(db_spec.goal)
