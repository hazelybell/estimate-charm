# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the search result PageMatch class."""

__metaclass__ = type

from lp.services.googlesearch import PageMatch
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestPageMatchURLHandling(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_rewrite_url_handles_invalid_data(self):
        # Given a bad url, pagematch can get a valid one.
        bad_url = ("http://launchpad.dev/+search?"
                   "field.text=WUSB54GC+ karmic&"
                   "field.actions.search=Search")
        p = PageMatch('Bad,', bad_url, 'Bad data')
        expected = ("http://launchpad.dev/+search?"
                   "field.text=WUSB54GC++karmic&"
                   "field.actions.search=Search")
        self.assertEqual(expected, p.url)

    def test_rewrite_url_handles_invalid_data_partial_escaped(self):
        # Given a url with partial escaped values, pagematch does not error.
        partial_encoded_url = (
           "http://launchpad.dev/+search?"
           "field.text=WUSB54GC+%2Bkarmic&"
           "field.actions.search=Search")
        p = PageMatch('Weird.', partial_encoded_url, 'Weird data')
        expected = (
            "http://launchpad.dev/+search?"
            "field.text=WUSB54GC+%2Bkarmic&"
            "field.actions.search=Search")
        self.assertEqual(expected, p.url)
