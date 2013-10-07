# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.blueprints.browser.specification import (
    SpecificationActionMenu,
    SpecificationContextMenu,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.menu import check_menu_links


class TestSpecificationMenus(TestCaseWithFactory):
    """Test specification menus links."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.specification = self.factory.makeSpecification()

    def test_SpecificationContextMenu(self):
        menu = SpecificationContextMenu(self.specification)
        self.assertTrue(check_menu_links(menu))

    def test_SpecificationActionMenu(self):
        menu = SpecificationActionMenu(self.specification)
        self.assertTrue(check_menu_links(menu))
