# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the user requested oops using ++oops++ traversal."""

__metaclass__ = type


from lazr.restful.utils import get_current_browser_request

from lp.services.webapp.errorlog import (
    LAZR_OOPS_USER_REQUESTED_KEY,
    maybe_record_user_requested_oops,
    OopsNamespace,
    )
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    TestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestUserRequestedOops(TestCase):
    """Test the functions related to user requested oopses."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        login(ANONYMOUS)

    def tearDown(self):
        logout()
        TestCase.tearDown(self)

    def test_none_requested(self):
        # If an oops was not requested, then maybe_record_user_requested_oops
        # does not record an oops.
        request = get_current_browser_request()
        maybe_record_user_requested_oops()
        self.assertIs(None, request.oopsid)

    def test_annotation_key(self):
        # The request for an oops is stored in the request annotations.
        # If a user request oops is recorded, the oops id is stored in
        # the request.
        request = get_current_browser_request()
        request.annotations[LAZR_OOPS_USER_REQUESTED_KEY] = True
        self.assertIs(None, request.oopsid)
        maybe_record_user_requested_oops()
        self.assertIsNot(None, request.oopsid)

    def test_multiple_calls(self):
        # Asking to record the OOPS twice just returns the same ID.
        request = get_current_browser_request()
        request.annotations[LAZR_OOPS_USER_REQUESTED_KEY] = True
        maybe_record_user_requested_oops()
        orig_oops_id = request.oopsid
        maybe_record_user_requested_oops()
        self.assertEqual(orig_oops_id, request.oopsid)

    def test_existing_oops_stops_user_requested(self):
        # If there is already an existing oops id in the request, then the
        # user requested oops is ignored.
        request = get_current_browser_request()
        request.oopsid = "EXISTING"
        request.annotations[LAZR_OOPS_USER_REQUESTED_KEY] = True
        maybe_record_user_requested_oops()
        self.assertEqual("EXISTING", request.oopsid)

    def test_OopsNamespace_traverse(self):
        # The traverse method of the OopsNamespace sets the request
        # annotation, and returns the context that it was created with.
        request = get_current_browser_request()
        self.assertIs(
            None, request.annotations.get(LAZR_OOPS_USER_REQUESTED_KEY))
        context = object()
        namespace = OopsNamespace(context, request)
        result = namespace.traverse("name", None)
        self.assertIs(context, result)
        self.assertTrue(request.annotations.get(LAZR_OOPS_USER_REQUESTED_KEY))
