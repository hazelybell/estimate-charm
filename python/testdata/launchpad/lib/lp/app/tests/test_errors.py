# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from httplib import (
    BAD_REQUEST,
    UNAUTHORIZED,
    )

from lp.app.errors import (
    SubscriptionPrivacyViolation,
    UserCannotUnsubscribePerson,
    )
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.views import create_webservice_error_view


class TestWebServiceErrors(TestCase):
    """ Test that errors are correctly mapped to HTTP status codes."""

    layer = FunctionalLayer

    def test_UserCannotUnsubscribePerson_unauthorized(self):
        error_view = create_webservice_error_view(
            UserCannotUnsubscribePerson())
        self.assertEqual(UNAUTHORIZED, error_view.status)

    def test_SubscriptionPrivacyViolation_bad_request(self):
        error_view = create_webservice_error_view(
            SubscriptionPrivacyViolation())
        self.assertEqual(BAD_REQUEST, error_view.status)
