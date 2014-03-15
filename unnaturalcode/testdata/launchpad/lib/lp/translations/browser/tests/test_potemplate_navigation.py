# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test `POTemplateNavigation`."""

__metaclass__ = type

from lp.app.errors import NotFoundError
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.browser.potemplate import POTemplateNavigation
from lp.translations.model.pofile import DummyPOFile


class TestPOTemplateNavigation(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def _makeNavigation(self, potemplate, method='GET'):
        """Create a `POTemplateNavigation` for `potemplate`."""
        request = LaunchpadTestRequest()
        request.method = method
        return POTemplateNavigation(potemplate, request)

    def test_traverse_to_existing_pofile(self):
        pofile = self.factory.makePOFile('nl')
        nav = self._makeNavigation(pofile.potemplate)
        destination = nav.traverse('nl')
        self.assertEqual(pofile, destination)

    def test_traverse_to_dummy_pofile(self):
        nav = self._makeNavigation(self.factory.makePOTemplate())
        destination = nav.traverse('de')
        self.assertIsInstance(destination, DummyPOFile)
        self.assertEqual('de', destination.language.code)

    def test_traverse_nonexistent_language(self):
        nav = self._makeNavigation(self.factory.makePOTemplate())
        self.assertRaises(NotFoundError, nav.traverse, 'bzyzzyx_GRQ@UTF-13')

    def test_unsupported_method(self):
        pofile = self.factory.makePOFile('sr')
        nav = self._makeNavigation(pofile.potemplate, method='PUT')
        self.assertRaises(AssertionError, nav.traverse, 'sr')
