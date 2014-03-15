# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for registry errors."""


__metaclass__ = type


from httplib import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    UNAUTHORIZED,
    )

from lp.registry.errors import (
    CannotTransitionToCountryMirror,
    CommercialSubscribersOnly,
    DeleteSubscriptionError,
    DistroSeriesDifferenceError,
    InclusiveTeamLinkageError,
    JoinNotAllowed,
    NameAlreadyTaken,
    PPACreationError,
    PrivatePersonLinkageError,
    TeamMembershipPolicyError,
    TeamMembershipTransitionError,
    UserCannotChangeMembershipSilently,
    UserCannotSubscribePerson,
    )
from lp.registry.interfaces.person import ImmutableVisibilityError
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.views import create_webservice_error_view


class TestWebServiceErrors(TestCase):
    """ Test that errors are correctly mapped to HTTP status codes."""

    layer = FunctionalLayer

    def test_InclusiveTeamLinkageError_forbidden(self):
        error_view = create_webservice_error_view(InclusiveTeamLinkageError())
        self.assertEqual(FORBIDDEN, error_view.status)

    def test_PersonLinkageError_forbidden(self):
        error_view = create_webservice_error_view(PrivatePersonLinkageError())
        self.assertEqual(FORBIDDEN, error_view.status)

    def test_PPACreationError_bad_request(self):
        error_view = create_webservice_error_view(PPACreationError())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_JoinNotAllowed_bad_request(self):
        error_view = create_webservice_error_view(JoinNotAllowed())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_TeamMembershipPolicyError_bad_request(self):
        error_view = create_webservice_error_view(
            TeamMembershipPolicyError())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_TeamMembershipTransitionError_bad_request(self):
        error_view = create_webservice_error_view(
            TeamMembershipTransitionError())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_DistroSeriesDifferenceError_bad_request(self):
        error_view = create_webservice_error_view(
            DistroSeriesDifferenceError())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_DeleteSubscriptionError_bad_request(self):
        error_view = create_webservice_error_view(DeleteSubscriptionError())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_UserCannotSubscribePerson_authorised(self):
        error_view = create_webservice_error_view(UserCannotSubscribePerson())
        self.assertEqual(UNAUTHORIZED, error_view.status)

    def test_CannotTransitionToCountryMirror_bad_request(self):
        error_view = create_webservice_error_view(
            CannotTransitionToCountryMirror())
        self.assertEqual(BAD_REQUEST, error_view.status)

    def test_UserCannotChangeMembershipSilently_authorised(self):
        error_view = create_webservice_error_view(
            UserCannotChangeMembershipSilently())
        self.assertEqual(UNAUTHORIZED, error_view.status)

    def test_NameAlreadyTaken_bad_request(self):
        error_view = create_webservice_error_view(NameAlreadyTaken())
        self.assertEqual(CONFLICT, error_view.status)

    def test_CommercialSubscribersOnly_forbidden(self):
        error_view = create_webservice_error_view(CommercialSubscribersOnly())
        self.assertEqual(FORBIDDEN, error_view.status)

    def test_ImmutableVisibilityError_forbidden(self):
        error_view = create_webservice_error_view(
            ImmutableVisibilityError())
        self.assertEqual(FORBIDDEN, error_view.status)
