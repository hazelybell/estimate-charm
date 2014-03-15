# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View tests for TranslationGroup."""

__metaclass__ = type

import transaction
from zope.component import getUtility

from lp.services.webapp.servers import LaunchpadTestRequest
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    BrowserTestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.translations.browser.translationgroup import TranslationGroupView


class TestTranslationGroupView(TestCaseWithFactory):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationGroupView, self).setUp()

    def _makeView(self, group, name=None):
        """Create a view for self.group."""
        view = TranslationGroupView(group, LaunchpadTestRequest())
        view.initialize()
        return view

    def test_translator_list_empty(self):
        view = self._makeView(self.factory.makeTranslationGroup())
        self.assertEqual([], view.translator_list)

    def test_translator_list(self):
        # translator_list composes dicts using _makeTranslatorDict.
        group = self.factory.makeTranslationGroup()
        tr_translator = self.factory.makeTranslator('tr', group)
        transaction.commit()
        view = self._makeView(group)
        translator_dict = view._makeTranslatorDict(
            tr_translator, tr_translator.language, tr_translator.translator)
        self.assertEqual([translator_dict], list(view.translator_list))

    def test_makeTranslatorDict(self):
        # _makeTranslatorDict describes a Translator entry to the UI.
        group = self.factory.makeTranslationGroup()
        xhosa = self.factory.makeTranslator('xh', group)
        xhosa.style_guide_url = 'http://xh.example.com/'
        view = self._makeView(group)
        output = view._makeTranslatorDict(
            xhosa, xhosa.language, xhosa.translator)

        self.assertEqual(xhosa.translator, output['person'])
        self.assertEqual('xh', output['code'])
        self.assertEqual(
            getUtility(ILanguageSet).getLanguageByCode('xh'),
            output['language'])
        self.assertEqual(xhosa.datecreated, output['datecreated'])
        self.assertEqual(xhosa.style_guide_url, output['style_guide_url'])
        self.assertEqual(xhosa, output['context'])


class TestTranslationGroupViewPermissions(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def _assertLinksFound(self, contents, links_found):
        for link in ['+edit', '+appoint']:
            if links_found:
                self.assertTrue(link in contents)
            else:
                self.assertFalse(link in contents)

    def test_links_anon(self):
        group = self.factory.makeTranslationGroup()
        browser = self.getViewBrowser(group, "+index", no_login=True)
        self._assertLinksFound(browser.contents, False)

    def test_links_unauthorized(self):
        group = self.factory.makeTranslationGroup()
        browser = self.getViewBrowser(group, "+index")
        self._assertLinksFound(browser.contents, False)

    def test_links_authorized(self):
        group = self.factory.makeTranslationGroup()
        browser = self.getViewBrowser(group, "+index", user=group.owner)
        self._assertLinksFound(browser.contents, True)
