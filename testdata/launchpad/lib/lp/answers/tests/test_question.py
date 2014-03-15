# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestQuestionSearch(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_projectgroup_with_inactive_products_not_in_results(self):
        group = self.factory.makeProject()
        product = self.factory.makeProduct(project=group)
        inactive = self.factory.makeProduct(project=group)
        question = self.factory.makeQuestion(target=product)
        self.factory.makeQuestion(target=inactive)
        removeSecurityProxy(inactive).active = False
        self.assertContentEqual([question], group.searchQuestions())
