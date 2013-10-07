# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Module doc."""

__metaclass__ = type


from lp.services.webapp.escaping import html_escape
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.browser.potemplate import (
    POTemplateAdminView,
    POTemplateEditView,
    )


class TestPOTemplateEditViewValidation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def _makeData(self, potemplate, **kwargs):
        """Create form data for the given template with some changed values.

        The attributes are only those considered by the validate method.
        """
        attributes = [
            'distroseries', 'sourcepackagename', 'productseries',
            'name', 'translation_domain']
        data = dict(
            [(name, getattr(potemplate, name)) for name in attributes])
        data.update(**kwargs)
        return data

    def test_field_names_productseries(self):
        # A product series template has one set of field names that include
        # the template name.
        potemplate = self.factory.makePOTemplate()
        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        self.assertContentEqual(
            ['name', 'translation_domain', 'description', 'priority',
             'path', 'iscurrent', 'owner'],
            view.field_names)

    def test_field_names_sourcepackage(self):
        # A sourcepackage template has two more fields compared to the
        # product series templates.
        sourcepackage = self.factory.makeSourcePackage()
        potemplate = self.factory.makePOTemplate(
            distroseries=sourcepackage.distroseries,
            sourcepackagename=sourcepackage.sourcepackagename)
        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        self.assertContentEqual(
            ['name', 'translation_domain', 'description', 'priority',
             'path', 'iscurrent', 'sourcepackagename', 'languagepack'],
            view.field_names)

    def test_detects_invalid_names(self):
        # A template name must be satisfying the valid_name constraint.
        invalid_name = 'name!'
        potemplate = self.factory.makePOTemplate()
        data = self._makeData(potemplate, name=invalid_name)
        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        view.validate(data)
        self.assertEqual(
            [html_escape(
                u'Template name can only start with lowercase letters a-z '
                u'or digits 0-9, and other than those characters, can only '
                u'contain "-", "+" and "." characters.')],
            view.errors)

    def test_detects_name_clash_on_name_change(self):
        # A template name may not already be used.
        existing_name = self.factory.getUniqueString()
        existing_potemplate = self.factory.makePOTemplate(name=existing_name)
        series = existing_potemplate.productseries
        potemplate = self.factory.makePOTemplate(productseries=series)

        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        data = self._makeData(potemplate, name=existing_name)
        view.validate(data)
        self.assertEqual([u'Name is already in use.'], view.errors)

    def test_detects_domain_clash_on_domain_change(self):
        # A translation domain may not already be used.
        existing_domain = self.factory.getUniqueString()
        existing_potemplate = self.factory.makePOTemplate(
            translation_domain=existing_domain)
        series = existing_potemplate.productseries
        potemplate = self.factory.makePOTemplate(productseries=series)

        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        data = self._makeData(potemplate, translation_domain=existing_domain)
        view.validate(data)
        self.assertEqual([u'Domain is already in use.'], view.errors)

    def test_detects_name_clash_on_sourcepackage_change(self):
        # Detect changing to a source package that already has a template of
        # the same name.
        sourcepackage = self.factory.makeSourcePackage()
        existing_potemplate = self.factory.makePOTemplate(
            sourcepackage=sourcepackage)
        potemplate = self.factory.makePOTemplate(
            distroseries=sourcepackage.distroseries,
            name=existing_potemplate.name)

        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        data = self._makeData(
            potemplate, sourcepackagename=sourcepackage.sourcepackagename)
        view.validate(data)
        self.assertEqual(
            [u'Source package already has a template with that same name.'],
            view.errors)

    def test_detects_domain_clash_on_sourcepackage_change(self):
        # Detect changing to a source package that already has a template with
        # the same translation domain.
        sourcepackage = self.factory.makeSourcePackage()
        existing_potemplate = self.factory.makePOTemplate(
            sourcepackage=sourcepackage)
        potemplate = self.factory.makePOTemplate(
            distroseries=sourcepackage.distroseries,
            translation_domain=existing_potemplate.translation_domain)

        view = POTemplateEditView(potemplate, LaunchpadTestRequest())
        data = self._makeData(
            potemplate, sourcepackagename=sourcepackage.sourcepackagename)
        view.validate(data)
        self.assertEqual(
            [u'Source package already has a template with that same domain.'],
            view.errors)


class TestPOTemplateAdminViewValidation(TestPOTemplateEditViewValidation):

    def test_detects_name_clash_on_productseries_change(self):
        # Detect changing to a productseries that already has a template of
        # the same name.
        template_name = self.factory.getUniqueString()
        existing_potemplate = self.factory.makePOTemplate(name=template_name)
        new_series = existing_potemplate.productseries
        potemplate = self.factory.makePOTemplate(name=template_name)

        view = POTemplateAdminView(potemplate, LaunchpadTestRequest())
        data = self._makeData(potemplate, productseries=new_series)
        view.validate(data)
        self.assertEqual(
            [u'Series already has a template with that same name.'],
            view.errors)

    def test_detects_domain_clash_on_productseries_change(self):
        # Detect changing to a productseries that already has a template with
        # the same translation domain.
        translation_domain = self.factory.getUniqueString()
        existing_potemplate = self.factory.makePOTemplate(
            translation_domain=translation_domain)
        new_series = existing_potemplate.productseries
        potemplate = self.factory.makePOTemplate(
            translation_domain=translation_domain)

        view = POTemplateAdminView(potemplate, LaunchpadTestRequest())
        data = self._makeData(potemplate, productseries=new_series)
        view.validate(data)
        self.assertEqual(
            [u'Series already has a template with that same domain.'],
            view.errors)

    def test_detects_no_sourcepackage_or_productseries(self):
        # Detect if no source package or productseries was selected.
        potemplate = self.factory.makePOTemplate()

        view = POTemplateAdminView(potemplate, LaunchpadTestRequest())
        data = self._makeData(
            potemplate,
            distroseries=None, sourcepackagename=None, productseries=None)
        view.validate(data)
        self.assertEqual(
            [u'Choose either a distribution release series or a project '
             u'release series.'], view.errors)

    def test_detects_sourcepackage_and_productseries(self):
        # Detect if no source package or productseries was selected.
        potemplate = self.factory.makePOTemplate()
        sourcepackage = self.factory.makeSourcePackage()

        view = POTemplateAdminView(potemplate, LaunchpadTestRequest())
        data = self._makeData(
            potemplate,
            distroseries=sourcepackage.distroseries,
            sourcepackagename=sourcepackage.sourcepackagename,
            productseries=potemplate.productseries)
        view.validate(data)
        self.assertEqual(
            [u'Choose a distribution release series or a project '
             u'release series, but not both.'], view.errors)
