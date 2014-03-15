# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.app.enums import InformationType
from lp.app.errors import UserCannotUnsubscribePerson
from lp.app.interfaces.services import IService
from lp.registry.enums import (
    SharingPermission,
    SpecificationSharingPolicy,
    )
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestSpecificationSubscription(TestCaseWithFactory):
    """ Test whether a user can unsubscribe someone

    As user can't unsubscribe just anyone from a spec. To check whether
    someone can be unusubscribed, the canBeUnsubscribedByUser() method on
    the SpecificationSubscription object is used.
    """

    layer = DatabaseFunctionalLayer

    def _make_subscription(self, proprietary_subscription=False):
        subscriber = self.factory.makePerson()
        subscribed_by = self.factory.makePerson()
        policy = SpecificationSharingPolicy.PUBLIC_OR_PROPRIETARY
        product_owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            specification_sharing_policy=policy, owner=product_owner)
        if proprietary_subscription:
            info_type = InformationType.PROPRIETARY
            with person_logged_in(product_owner):
                permissions = {
                    InformationType.PROPRIETARY: SharingPermission.ALL,
                    }
                getUtility(IService, 'sharing').sharePillarInformation(
                    product, subscribed_by, product_owner, permissions)
        else:
            info_type = InformationType.PUBLIC
        if proprietary_subscription:
            # If the spec is proprietary, subscribed_by must have the
            # permission launchpad.Edit on the spec in order to
            # subscribe someone. This permission requires to have a
            # special role for the specificaiton, like the assignee.
            assignee = subscribed_by
        else:
            assignee = None
        spec = self.factory.makeSpecification(
            product=product, information_type=info_type, assignee=assignee)
        with person_logged_in(subscribed_by):
            subscription = spec.subscribe(subscriber, subscribed_by)
        return spec, subscriber, subscribed_by, subscription

    def test_can_unsubscribe_self(self):
        # The user can of course unsubscribe himself, even if someone else
        # subscribed him.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        self.assertTrue(subscription.canBeUnsubscribedByUser(subscriber))

    # XXX Abel Deuring 2012-11-21, bug=1081677
    # The two tests below show a weird inconsisteny: Sometimes
    # subscribed_by can unsubscribe, sometimes not.
    def test_subscriber_cannot_unsubscribe_user_from_public_spec(self):
        # For public specifications, the one who subscribed the
        # subscriber doesn't have permission to unsubscribe him.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        self.assertFalse(subscription.canBeUnsubscribedByUser(subscribed_by))

    def test_subscriber_can_unsubscribe_user_from_private_spec(self):
        # For private specifications, the one who subscribed the
        # subscriber has permission to unsubscribe him.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription(True)
        self.assertTrue(subscription.canBeUnsubscribedByUser(subscribed_by))

    def test_anonymous_cannot_unsubscribe(self):
        # The anonymous user (represented by None) can't unsubscribe anyone.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        self.assertFalse(subscription.canBeUnsubscribedByUser(None))

    def test_can_unsubscribe_team(self):
        # A user can unsubscribe a team he's a member of.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        team = self.factory.makeTeam()
        member = self.factory.makePerson()
        with person_logged_in(member):
            member.join(team)
            subscription = spec.subscribe(team, subscribed_by)
        self.assertTrue(subscription.canBeUnsubscribedByUser(member))

        non_member = self.factory.makePerson()
        self.assertFalse(subscription.canBeUnsubscribedByUser(non_member))

    def test_cannot_unsubscribe_team(self):
        # A user cannot unsubscribe a team he's a not member of.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        team = self.factory.makeTeam()
        member = self.factory.makePerson()
        with person_logged_in(member):
            member.join(team)
            subscription = spec.subscribe(team, subscribed_by)
        non_member = self.factory.makePerson()
        self.assertFalse(subscription.canBeUnsubscribedByUser(non_member))

    def test_unallowed_unsubscribe_raises(self):
        # A spec's unsubscribe method uses canBeUnsubscribedByUser to check
        # that the unsubscribing user has the appropriate permissions.
        # unsubscribe will raise an exception if the user does not have
        # permission.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        person = self.factory.makePerson()
        self.assertRaises(
            UserCannotUnsubscribePerson, spec.unsubscribe, subscriber, person)

    def test_spec_owner_can_unsubscribe(self):
        # The owner of a specification can unsubscribe any subscriber.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        self.assertTrue(subscription.canBeUnsubscribedByUser(spec.owner))

    def test_admin_can_unsubscribe(self):
        # LP admins can unsubscribe any subscriber.
        (spec, subscriber,
            subscribed_by, subscription) = self._make_subscription()
        admin = self.factory.makeAdministrator()
        self.assertTrue(subscription.canBeUnsubscribedByUser(admin))
