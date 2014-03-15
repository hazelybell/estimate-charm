# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test views that manage commercial subscriptions."""

__metaclass__ = type

from lp.services.salesforce.interfaces import ISalesforceVoucherProxy
from lp.services.salesforce.tests.proxy import TestSalesforceVoucherProxy
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    FakeAdapterMixin,
    login_celebrity,
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tags_by_class,
    )
from lp.testing.views import create_initialized_view


class PersonVouchersViewTestCase(FakeAdapterMixin, TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def makeVouchers(self, user, number, voucher_proxy=None):
        if voucher_proxy is None:
            voucher_proxy = TestSalesforceVoucherProxy()
        self.registerUtility(voucher_proxy, ISalesforceVoucherProxy)
        vouchers = []
        for n in xrange(number):
            vouchers.append(voucher_proxy.grantVoucher(user, user, user, 12))
        return vouchers

    def test_init_without_vouchers_or_projects(self):
        # The view provides common view properties, but the form is disabled.
        user = self.factory.makePerson()
        self.factory.makeProduct(owner=user)
        self.makeVouchers(user, 0)
        user_url = canonical_url(user)
        with person_logged_in(user):
            view = create_initialized_view(user, '+vouchers')
        self.assertEqual('Commercial subscription vouchers', view.page_title)
        self.assertEqual(user_url, view.cancel_url)
        self.assertIs(None, view.next_url)
        self.assertEqual(0, len(view.redeemable_vouchers))

    def assertFields(self, view):
        self.assertEqual(1, len(view.redeemable_vouchers))
        self.assertEqual(
            ['project', 'voucher'], [f.__name__ for f in view.form_fields])

    def test_init_with_vouchers_and_projects(self):
        # The fields are setup when the user hase both vouchers and projects.
        user = self.factory.makePerson()
        login_person(user)
        self.makeVouchers(user, 1)
        self.factory.makeProduct(owner=user)
        view = create_initialized_view(user, '+vouchers')
        self.assertFields(view)

    def test_init_with_commercial_admin_with_vouchers(self):
        # The fields are setup if the commercial admin has vouchers.
        commercial_admin = login_celebrity('commercial_admin')
        self.makeVouchers(commercial_admin, 1)
        view = create_initialized_view(commercial_admin, '+vouchers')
        self.assertFields(view)

    def test_with_commercial_admin_for_user_with_vouchers_and_projects(self):
        # A commercial admin can see another user's vouchers.
        user = self.factory.makePerson()
        login_person(user)
        self.makeVouchers(user, 1)
        self.factory.makeProduct(owner=user)
        login_celebrity('commercial_admin')
        view = create_initialized_view(user, '+vouchers')
        self.assertFields(view)

    def assertRedeem(self, view, project, remaining=0):
        self.assertEqual([], view.errors)
        self.assertIsNot(None, project.commercial_subscription)
        self.assertEqual(remaining, len(view.redeemable_vouchers))
        self.assertEqual(
            remaining, len(view.form_fields['voucher'].field.vocabulary))
        self.assertEqual(
            remaining, len(view.widgets['voucher'].vocabulary))

    def makeForm(self, project, voucher_id):
        return {
            'field.project': project.name,
            'field.voucher': voucher_id,
            'field.actions.redeem': 'Redeem',
            }

    def test_redeem_with_commercial_admin_for_user(self):
        # A commercial admin can redeem a voucher for a user.
        project = self.factory.makeProduct()
        user = project.owner
        [voucher_id] = self.makeVouchers(user, 1)
        form = self.makeForm(project, voucher_id)
        login_celebrity('commercial_admin')
        view = create_initialized_view(user, '+vouchers', form=form)
        self.assertRedeem(view, project)

    def test_redeem_with_commercial_admin(self):
        # The fields are setup if the commercial admin has vouchers.
        commercial_admin = login_celebrity('commercial_admin')
        [voucher_id] = self.makeVouchers(commercial_admin, 1)
        project = self.factory.makeProduct()
        form = self.makeForm(project, voucher_id)
        view = create_initialized_view(
            commercial_admin, '+vouchers', form=form)
        self.assertRedeem(view, project)

    def test_redeem_twice_with_commercial_admin(self):
        # The fields are setup if the commercial admin has vouchers.
        commercial_admin = login_celebrity('commercial_admin')
        voucher_proxy = TestSalesforceVoucherProxy()
        voucher_id_1, voucher_id_2 = self.makeVouchers(
            commercial_admin, 2, voucher_proxy)
        project_1 = self.factory.makeProduct()
        project_2 = self.factory.makeProduct()
        form = self.makeForm(project_1, voucher_id_1)
        view = create_initialized_view(
            commercial_admin, '+vouchers', form=form)
        self.assertRedeem(view, project_1, remaining=1)
        # A job will notify Salesforce of the voucher redemption but here we
        # will do it manually.
        voucher_proxy.redeemVoucher(
            voucher_id_1, commercial_admin, project_1)

        form = self.makeForm(project_2, voucher_id_2)
        view = create_initialized_view(
            commercial_admin, '+vouchers', form=form)
        self.assertRedeem(view, project_2)

    def test_pending_vouchers_excluded(self):
        # Vouchers pending redemption in Salesforce are not included in choice.
        commercial_admin = login_celebrity('commercial_admin')
        voucher_id_1, voucher_id_2 = self.makeVouchers(commercial_admin, 2)
        project_1 = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(
            project_1, False, 'pending-' + voucher_id_1)
        view = create_initialized_view(commercial_admin, '+vouchers')
        vouchers = list(view.widgets['voucher'].vocabulary)
        # Only voucher2 in vocab since voucher1 is pending redemption.
        self.assertEqual(1, len(vouchers))
        self.assertEqual(voucher_id_2, vouchers[0].token)

    def test_redeem_twice_causes_error(self):
        # If a voucher is redeemed twice, the second attempt is rejected.
        commercial_admin = login_celebrity('commercial_admin')
        voucher_id_1, voucher_id_2 = self.makeVouchers(commercial_admin, 2)
        project_1 = self.factory.makeProduct(name='p1')
        project_2 = self.factory.makeProduct(name='p2')
        url = canonical_url(commercial_admin, view_name='+vouchers')
        browser = self.getUserBrowser(url, commercial_admin)
        # A second browser opens the +vouchers page before the first browser
        # attempts to redeem the voucher.
        browser2 = self.getUserBrowser(url, commercial_admin)
        browser.getControl(
            'Select the project you wish to subscribe').value = 'p1'
        browser.getControl(
            'Select a voucher').getControl(voucher_id_1).selected = True
        browser.getControl('Redeem').click()
        with person_logged_in(commercial_admin):
            self.assertIsNotNone(project_1.commercial_subscription)

        browser2.getControl(
            'Select the project you wish to subscribe').value = 'p2'
        browser2.getControl(
            'Select a voucher').getControl(voucher_id_1).selected = True
        browser2.getControl('Redeem').click()
        with person_logged_in(commercial_admin):
            self.assertIsNone(project_2.commercial_subscription)
        error_messages = find_tags_by_class(browser2.contents, 'message')
        self.assertEqual(extract_text(error_messages[1]), 'Invalid value')
