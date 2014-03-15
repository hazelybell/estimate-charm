# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from soupmatchers import (
    HTMLContains,
    Tag,
    )
from testtools.matchers import Not

from lp.app.enums import InformationType
from lp.testing import BrowserTestCase
from lp.testing.layers import DatabaseFunctionalLayer


class TestProductSeries(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    @staticmethod
    def hasAutoImport(value):
        tag = Tag('importall', 'input',
                  attrs={'name': 'field.translations_autoimport_mode',
                         'value': value})
        return HTMLContains(tag)

    def test_private_disables_imports(self):
        # Proprietary products disable import options.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, information_type=InformationType.PROPRIETARY)
        series = self.factory.makeProductSeries(product=product)
        browser = self.getViewBrowser(series, '+translations-settings',
                                      user=owner, rootsite='translations')
        self.assertThat(browser.contents,
                        Not(self.hasAutoImport('IMPORT_TRANSLATIONS')))
        self.assertThat(browser.contents,
                        Not(self.hasAutoImport('IMPORT_TEMPLATES')))
