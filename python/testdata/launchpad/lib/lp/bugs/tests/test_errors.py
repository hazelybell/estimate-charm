# Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bugs errors."""


__metaclass__ = type


from httplib import EXPECTATION_FAILED

from lp.bugs.errors import InvalidDuplicateValue
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer
from lp.testing.views import create_webservice_error_view


class TestWebServiceErrors(TestCase):
    """ Test that errors are correctly mapped to HTTP status codes."""

    layer = FunctionalLayer

    def test_InvalidDuplicateValue_expectation_failed(self):
        error_view = create_webservice_error_view(
            InvalidDuplicateValue("Dup"))
        self.assertEqual(EXPECTATION_FAILED, error_view.status)
