# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.component import getUtility

from lp.answers.browser.question import (
    QuestionEditMenu,
    QuestionExtrasMenu,
    )
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.menu import check_menu_links


class TestQuestionMenus(TestCaseWithFactory):
    """Test specification menus links."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.person = self.factory.makePerson()
        login_person(self.person)
        self.question = self.factory.makeQuestion()

    def test_QuestionEditMenu(self):
        menu = QuestionEditMenu(self.question)
        self.assertTrue(check_menu_links(menu))

    def test_QuestionExtrasMenu(self):
        menu = QuestionExtrasMenu(self.question)
        self.assertTrue(check_menu_links(menu))

    def test_link_linkfaq(self):
        # A question without a linked FAQ has an 'add' icon.
        menu = QuestionExtrasMenu(self.question)
        link = menu.linkfaq()
        self.assertEqual('add', link.icon)
        # A question with a linked FAQ has an 'edit' icon.
        self.person.addLanguage(getUtility(ILanguageSet)['en'])
        target = self.question.target
        target.addAnswerContact(self.person, self.person)
        faq = self.factory.makeFAQ(target=target)
        self.question.linkFAQ(self.person, faq, 'message')
        link = menu.linkfaq()
        self.assertEqual('edit', link.icon)
