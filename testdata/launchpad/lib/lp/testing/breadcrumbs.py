# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.webapp.publisher import canonical_url
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.publication import test_traverse
from lp.testing.views import create_initialized_view


class BaseBreadcrumbTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def assertBreadcrumbs(self, expected, obj, view_name=None, rootsite=None):
        """Assert that the breadcrumbs for obj match the expected values.

        :param expected: A list of tuples containing (text, url) pairs.
        """
        crumbs = self.getBreadcrumbsForObject(obj, view_name, rootsite)
        self.assertEqual(
            expected,
            [(crumb.text, crumb.url) for crumb in crumbs])

    def assertBreadcrumbTexts(self, expected, obj, view_name=None,
                              rootsite=None):
        """The text of the breadcrumbs for obj match the expected values."""
        crumbs = self.getBreadcrumbsForObject(obj, view_name, rootsite)
        self.assertEqual(expected, [crumb.text for crumb in crumbs])

    def assertBreadcrumbUrls(self, expected, obj, view_name=None,
                             rootsite=None):
        """The urls of the breadcrumbs for obj match the expected values."""
        crumbs = self.getBreadcrumbsForObject(obj, view_name, rootsite)
        self.assertEqual(expected, [crumb.url for crumb in crumbs])

    def getBreadcrumbsForObject(self, obj, view_name=None, rootsite=None):
        """Get the breadcrumbs for the specified object.

        Traverse to the canonical_url of the object, and use the request from
        that to feed into the initialized hierarchy view so we get the
        traversed objects.
        """
        url = canonical_url(obj, view_name=view_name, rootsite=rootsite)
        return self.getBreadcrumbsForUrl(url)

    def getBreadcrumbsForUrl(self, url):
        obj, view, request = test_traverse(url)
        view = create_initialized_view(obj, '+hierarchy', request=request)
        return view.items
