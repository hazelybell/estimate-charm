# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import re

from BeautifulSoup import BeautifulSoup
from lazr.restful.fields import Reference
from zope.formlib.interfaces import (
    IBrowserWidget,
    IInputWidget,
    WidgetInputError,
    )
from zope.interface import (
    implements,
    Interface,
    )

from lp.app.validators import LaunchpadValidationError
from lp.code.browser.widgets.branchtarget import BranchTargetWidget
from lp.code.model.branchtarget import (
    PersonBranchTarget,
    ProductBranchTarget,
    )
from lp.registry.vocabularies import ProductVocabulary
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class IThing(Interface):
    target = Reference(schema=Interface)


class Thing:
    implements(IThing)
    target = None


class LaunchpadTargetWidgetTestCase(TestCaseWithFactory):
    """Test the BranchTargetWidget class."""

    layer = DatabaseFunctionalLayer

    @property
    def form(self):
        return {
        'field.target': 'product',
        'field.target.product': 'pting',
        }

    def setUp(self):
        super(LaunchpadTargetWidgetTestCase, self).setUp()
        self.product = self.factory.makeProduct('pting')
        field = Reference(
            __name__='target', schema=Interface, title=u'target')
        field = field.bind(Thing())
        request = LaunchpadTestRequest()
        self.widget = BranchTargetWidget(field, request)

    def test_implements(self):
        self.assertTrue(verifyObject(IBrowserWidget, self.widget))
        self.assertTrue(verifyObject(IInputWidget, self.widget))

    def test_template(self):
        # The render template is setup.
        self.assertTrue(
            self.widget.template.filename.endswith('branch-target.pt'),
            'Template was not setup.')

    def test_default_option(self):
        # This product field is the default option.
        self.assertEqual('product', self.widget.default_option)

    def test_hasInput_false(self):
        # hasInput is false when the widget's name is not in the form data.
        self.widget.request = LaunchpadTestRequest(form={})
        self.assertEqual('field.target', self.widget.name)
        self.assertFalse(self.widget.hasInput())

    def test_hasInput_true(self):
        # hasInput is true is the widget's name in the form data.
        self.widget.request = LaunchpadTestRequest(form=self.form)
        self.assertEqual('field.target', self.widget.name)
        self.assertTrue(self.widget.hasInput())

    def test_setUpSubWidgets_first_call(self):
        # The subwidgets are setup and a flag is set.
        self.widget.setUpSubWidgets()
        self.assertTrue(self.widget._widgets_set_up)
        self.assertIsInstance(
            self.widget.product_widget.context.vocabulary,
            ProductVocabulary)

    def test_setUpSubWidgets_second_call(self):
        # The setUpSubWidgets method exits early if a flag is set to
        # indicate that the widgets were setup.
        self.widget._widgets_set_up = True
        self.widget.setUpSubWidgets()
        self.assertIs(None, getattr(self.widget, 'product_widget', None))

    def test_setUpOptions_default_product_checked(self):
        # The radio button options are composed of the setup widgets with
        # the product widget set as the default.
        self.widget.setUpSubWidgets()
        self.widget.setUpOptions()
        self.assertEqual(
            "selectWidget('field.target.option.product', event)",
            self.widget.product_widget.onKeyPress)
        self.assertEqual(
            '<input class="radioType" checked="checked" '
            'id="field.target.option.product" name="field.target" '
            'type="radio" value="product" />',
            self.widget.options['product'])
        self.assertEqual(
            '<input class="radioType" '
            'id="field.target.option.personal" name="field.target" '
            'type="radio" value="personal" />',
            self.widget.options['personal'])

    def test_setUpOptions_personal_checked(self):
        # The personal radio button is selected when the form is submitted
        # when the target field's value is 'personal'.
        form = {
            'field.target': 'personal',
            }
        self.widget.request = LaunchpadTestRequest(form=form)
        self.widget.setUpSubWidgets()
        self.widget.setUpOptions()
        self.assertEqual(
            '<input class="radioType" checked="checked" '
            'id="field.target.option.personal" name="field.target" '
            'type="radio" value="personal" />',
            self.widget.options['personal'])
        self.assertEqual(
            '<input class="radioType" '
            'id="field.target.option.product" name="field.target" '
            'type="radio" value="product" />',
            self.widget.options['product'])

    def test_setUpOptions_product_checked(self):
        # The product radio button is selected when the form is submitted
        # when the target field's value is 'product'.
        form = {
            'field.target': 'product',
            }
        self.widget.request = LaunchpadTestRequest(form=form)
        self.widget.setUpSubWidgets()
        self.widget.setUpOptions()
        self.assertEqual(
            '<input class="radioType" '
            'id="field.target.option.personal" name="field.target" '
            'type="radio" value="personal" />',
            self.widget.options['personal'])
        self.assertEqual(
            '<input class="radioType" checked="checked" '
            'id="field.target.option.product" name="field.target" '
            'type="radio" value="product" />',
            self.widget.options['product'])

    def test_hasValidInput_true(self):
        # The field input is valid when all submitted parts are valid.
        self.widget.request = LaunchpadTestRequest(form=self.form)
        self.assertTrue(self.widget.hasValidInput())

    def test_hasValidInput_false(self):
        # The field input is invalid if any of the submitted parts are invalid.
        form = self.form
        form['field.target.product'] = 'non-existent'
        self.widget.request = LaunchpadTestRequest(form=form)
        self.assertFalse(self.widget.hasValidInput())

    def test_getInputValue_personal(self):
        # The field value is the '+junk' when the personal radio button is
        # selected.
        form = self.form
        form['field.target'] = 'personal'
        self.widget.request = LaunchpadTestRequest(form=form)
        self.assertEqual('+junk', self.widget.getInputValue())

    def test_getInputValue_product(self):
        # The field value is the product when the project radio button is
        # selected and the project sub field is valid.
        form = self.form
        form['field.target'] = 'product'
        self.widget.request = LaunchpadTestRequest(form=form)
        self.assertEqual(self.product, self.widget.getInputValue())

    def test_getInputValue_product_missing(self):
        # An error is raised when the product field is missing.
        form = self.form
        form['field.target'] = 'product'
        del form['field.target.product']
        self.widget.request = LaunchpadTestRequest(form=form)
        message = 'Please enter a project name'
        e = self.assertRaises(WidgetInputError, self.widget.getInputValue)
        self.assertEqual(LaunchpadValidationError(message), e.errors)
        self.assertEqual(message, self.widget.error())

    def test_getInputValue_product_invalid(self):
        # An error is raised when the product is not valid.
        form = self.form
        form['field.target'] = 'product'
        form['field.target.product'] = 'non-existent'
        self.widget.request = LaunchpadTestRequest(form=form)
        message = (
            "There is no project named 'non-existent' registered in "
            "Launchpad")
        e = self.assertRaises(WidgetInputError, self.widget.getInputValue)
        self.assertEqual(LaunchpadValidationError(message), e.errors)
        self.assertEqual(html_escape(message), self.widget.error())

    def test_setRenderedValue_product(self):
        # Passing a product branch target will set the widget's render state to
        # 'product'.
        self.widget.setUpSubWidgets()
        target = ProductBranchTarget(self.product)
        self.widget.setRenderedValue(target)
        self.assertEqual('product', self.widget.default_option)
        self.assertEqual(
            self.product, self.widget.product_widget._getCurrentValue())

    def test_setRenderedValue_personal(self):
        # Passing a person branch target will set the widget's render state to
        # 'personal'.
        self.widget.setUpSubWidgets()
        target = PersonBranchTarget(self.factory.makePerson())
        self.widget.setRenderedValue(target)
        self.assertEqual('personal', self.widget.default_option)

    def test_call(self):
        # The __call__ method setups the widgets and the options.
        markup = self.widget()
        self.assertIsNot(None, self.widget.product_widget)
        self.assertTrue('personal' in self.widget.options)
        expected_ids = [
            'field.target.option.personal',
            'field.target.option.product',
            'field.target.product',
            ]
        soup = BeautifulSoup(markup)
        fields = soup.findAll(['input', 'select'], {'id': re.compile('.*')})
        ids = [field['id'] for field in fields]
        self.assertContentEqual(expected_ids, ids)
