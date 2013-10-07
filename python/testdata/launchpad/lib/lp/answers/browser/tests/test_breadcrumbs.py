# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.services.webapp.publisher import canonical_url
from lp.testing import login_person
from lp.testing.breadcrumbs import BaseBreadcrumbTestCase


class TestQuestionTargetProjectAndPersonBreadcrumbOnAnswersVHost(
        BaseBreadcrumbTestCase):
    """Test Breadcrumbs for IQuestionTarget, IProjectGroup and IPerson on the
    answers vhost.

    Any page below them on the answers vhost will get an extra breadcrumb for
    their homepage on the answers vhost, right after the breadcrumb for their
    mainsite homepage.
    """

    def setUp(self):
        super(TestQuestionTargetProjectAndPersonBreadcrumbOnAnswersVHost,
              self).setUp()
        self.person = self.factory.makePerson()
        self.person_questions_url = canonical_url(
            self.person, rootsite='answers')
        self.product = self.factory.makeProduct()
        self.product_questions_url = canonical_url(
            self.product, rootsite='answers')
        self.project = self.factory.makeProject()
        self.project_questions_url = canonical_url(
            self.project, rootsite='answers')

    def test_product(self):
        crumbs = self.getBreadcrumbsForObject(
            self.product, rootsite='answers')
        last_crumb = crumbs[-1]
        self.assertEquals(last_crumb.url, self.product_questions_url)
        self.assertEquals(last_crumb.text, 'Questions')

    def test_project(self):
        crumbs = self.getBreadcrumbsForObject(
            self.project, rootsite='answers')
        last_crumb = crumbs[-1]
        self.assertEquals(last_crumb.url, self.project_questions_url)
        self.assertEquals(last_crumb.text, 'Questions')

    def test_person(self):
        crumbs = self.getBreadcrumbsForObject(self.person, rootsite='answers')
        last_crumb = crumbs[-1]
        self.assertEquals(last_crumb.url, self.person_questions_url)
        self.assertEquals(last_crumb.text, 'Questions')


class TestAnswersBreadcrumb(BaseBreadcrumbTestCase):
    """Test Breadcrumbs for answer module objects."""

    def setUp(self):
        super(TestAnswersBreadcrumb, self).setUp()
        self.product = self.factory.makeProduct(name="mellon")
        login_person(self.product.owner)

    def test_question(self):
        self.question = self.factory.makeQuestion(
            target=self.product, title='Seeds are hard to chew')
        self.question_url = canonical_url(self.question, rootsite='answers')
        crumbs = self.getBreadcrumbsForObject(self.question)
        last_crumb = crumbs[-1]
        self.assertEquals(last_crumb.text, 'Question #%d' % self.question.id)

    def test_faq(self):
        self.faq = self.factory.makeFAQ(target=self.product, title='Seedless')
        self.faq_url = canonical_url(self.faq, rootsite='answers')
        crumbs = self.getBreadcrumbsForObject(self.faq)
        last_crumb = crumbs[-1]
        self.assertEquals(last_crumb.text, 'FAQ #%d' % self.faq.id)
