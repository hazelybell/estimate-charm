# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.interface.verify import verifyObject

from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.interfaces.hastranslationtemplates import (
    IHasTranslationTemplates,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )


class HasTranslationTemplatesTestMixin:
    """Test behaviour of objects with translation templates."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a product with two series and a shared POTemplate
        # in different series ('devel' and 'stable').
        super(HasTranslationTemplatesTestMixin, self).setUp()

    def createTranslationTemplate(self, name=None, priority=0):
        """Attaches a template to appropriate container."""
        raise NotImplementedError(
            'This must be provided by an executable test.')

    def createTranslationFile(self, name=None, priority=0):
        """Attaches a pofile to appropriate container."""
        raise NotImplementedError(
            'This must be provided by an executable test.')

    def createPackaging(self):
        """Creates a packaging link for the container."""
        raise NotImplementedError(
            'This must be provided by an executable test.')

    def createSharingTranslationTemplate(self):
        """Attaches a template to the sharing partner of the container."""
        raise NotImplementedError(
            'This must be provided by an executable test.')

    def test_implements_interface(self):
        # Make sure container implements IHasTranslationTemplates.
        verifyObject(IHasTranslationTemplates, self.container)

    def test_getCurrentTranslationTemplates(self):
        # With no current templates, we get an empty result set.
        results = self.container.getCurrentTranslationTemplates()
        current_templates = list(results)
        self.assertEquals([], current_templates)
        self.assertFalse(bool(results.any()))

        # With one of the templates marked as current, it is returned.
        template1 = self.createTranslationTemplate("one", priority=1)
        current_templates = list(
            self.container.getCurrentTranslationTemplates())
        self.assertEquals([template1], current_templates)

        # With two current templates, they are sorted by priority,
        # with higher numbers representing higher priority.
        template2 = self.createTranslationTemplate("two", priority=2)
        current_templates = list(
            self.container.getCurrentTranslationTemplates())
        self.assertEquals([template2, template1], current_templates)

        # Adding an obsolete template changes nothing.
        template3 = self.createTranslationTemplate("obsolete")
        template3.iscurrent = False
        current_templates = list(
            self.container.getCurrentTranslationTemplates())
        self.assertEquals([template2, template1], current_templates)

    def test_getCurrentTranslationTemplates_ids(self):
        # Returning just IDs works fine as well.
        template1 = self.createTranslationTemplate("one", priority=1)
        template2 = self.createTranslationTemplate("two", priority=2)
        current_templates_ids = list(
            self.container.getCurrentTranslationTemplates(just_ids=True))
        self.assertEquals(
            [template2.id, template1.id],
            current_templates_ids)

    def test_getCurrentTranslationFiles_empty(self):
        # With no current templates, we get an empty result set.
        current_translations = list(
            self.container.getCurrentTranslationFiles())
        self.assertEquals([], current_translations)

        # Even with one of the templates marked as current, nothing is
        # returned before POFile is added.
        template1 = self.createTranslationTemplate("one")
        current_translations = list(
            self.container.getCurrentTranslationFiles())
        self.assertEquals([], current_translations)

        # If template is not current, nothing is returned even if
        # there are POFiles attached to it.
        template1.iscurrent = False
        self.factory.makePOFile('sr', potemplate=template1)
        current_translations = list(
            self.container.getCurrentTranslationFiles())
        self.assertEquals([], current_translations)

    def test_getCurrentTranslationFiles_current(self):
        # If POFiles are attached to a current template, they are returned.
        template1 = self.createTranslationTemplate("one")
        pofile_sr = self.factory.makePOFile('sr', potemplate=template1)
        pofile_es = self.factory.makePOFile('es', potemplate=template1)
        # They are returned unordered, so we'll use a set over them
        # to make tests stable.
        current_translations = set(
            self.container.getCurrentTranslationFiles())
        self.assertEquals(
            set([pofile_sr, pofile_es]),
            current_translations)

        # All files, no matter what template they are in, are returned.
        template2 = self.createTranslationTemplate("two")
        pofile2_sr = self.factory.makePOFile('sr', potemplate=template2)
        current_translations = set(
            self.container.getCurrentTranslationFiles())
        self.assertEquals(
            set([pofile_sr, pofile_es, pofile2_sr]),
            current_translations)

        # If template is marked as obsolete, attached POFiles are
        # not returned anymore.
        template2.iscurrent = False
        current_translations = set(
            self.container.getCurrentTranslationFiles())
        self.assertEquals(
            set([pofile_sr, pofile_es]),
            current_translations)

    def test_getCurrentTranslationFiles_ids(self):
        # We can also fetch only IDs.
        template1 = self.createTranslationTemplate("one")
        pofile_sr = self.factory.makePOFile('sr', potemplate=template1)
        pofile_es = self.factory.makePOFile('es', potemplate=template1)
        current_translations_ids = set(
            self.container.getCurrentTranslationFiles(just_ids=True))
        self.assertEquals(
            set([pofile_sr.id, pofile_es.id]),
            current_translations_ids)

    def test_has_current_translation_templates__no_template(self):
        # A series without templates has no current templates.
        self.assertFalse(self.container.has_current_translation_templates)

    def test_has_current_translation_templates__current_template(self):
        # A series with a current template has current templates.
        self.createTranslationTemplate()
        self.assertTrue(self.container.has_current_translation_templates)

    def test_has_current_translation_templates__noncurrent_template(self):
        # A series with only non-current templates has no current
        # templates.
        template = self.createTranslationTemplate()
        template.iscurrent = False
        self.assertFalse(self.container.has_current_translation_templates)

    def test_has_current_translation_templates__two_templates(self):
        # A series with current and non-current templates has current
        # templates.
        template = self.createTranslationTemplate()
        template.iscurrent = False
        self.createTranslationTemplate()
        self.assertTrue(self.container.has_current_translation_templates)

    def test_has_obsolete_translation_templates__no_templates(self):
        # A series without templates has no obsolete templates.
        self.assertFalse(self.container.has_obsolete_translation_templates)

    def test_has_obsolete_translation_templates__current_template(self):
        # A series with a current template has no obsolete templates either.
        self.createTranslationTemplate()
        self.assertFalse(self.container.has_obsolete_translation_templates)

    def test_has_obsolete_translation_templates__noncurrent_template(self):
        # A series with only non-current templates has obsolete templates.
        template = self.createTranslationTemplate()
        template.iscurrent = False
        self.assertTrue(self.container.has_obsolete_translation_templates)

    def test_has_obsolete_translation_templates__two_templates(self):
        # A series with current and non-current templates has obsolete
        # templates.
        template = self.createTranslationTemplate()
        template.iscurrent = False
        self.createTranslationTemplate()
        self.assertTrue(self.container.has_obsolete_translation_templates)

    def test_has_sharing_translation_templates__no_link(self):
        # Without a packaging link, no sharing templates are found.
        self.assertFalse(self.container.has_sharing_translation_templates)

    def test_has_sharing_translation_templates__no_templates(self):
        # Without templates on the other side, no sharing templates are found.
        self.createPackaging()
        self.assertFalse(self.container.has_sharing_translation_templates)

    def test_has_sharing_translation_templates__templates(self):
        # Without templates on the other side, no sharing templates are found.
        self.createPackaging()
        self.createSharingTranslationTemplate()
        self.assertTrue(self.container.has_sharing_translation_templates)

    def test_has_translation_files(self):
        # has_translations_files should only return true if the object has
        # pofiles.
        self.assertFalse(self.container.has_translation_files)
        self.createTranslationFile("one")
        self.assertTrue(self.container.has_translation_files)

    def test_getTranslationTemplateByName(self):
        template_name = self.factory.getUniqueString()
        # A series without templates does not find the template.
        self.assertEqual(
            None, self.container.getTranslationTemplateByName(template_name))

        # A template with a different name is not found.
        self.createTranslationTemplate(self.factory.getUniqueString())
        self.assertEqual(
            None, self.container.getTranslationTemplateByName(template_name))

        # Only the template with the correct name is returned.
        template = self.createTranslationTemplate(template_name)
        self.assertEqual(
            template,
            self.container.getTranslationTemplateByName(template_name))

    def test_getTranslationTemplateFormats(self):
        # Check that translation_template_formats works properly.

        # With no templates, empty list is returned.
        all_formats = self.container.getTranslationTemplateFormats()
        self.assertEquals([], all_formats)

        # With one template, that template's format is returned.
        template1 = self.createTranslationTemplate("one")
        template1.source_file_format = TranslationFileFormat.PO
        all_formats = self.container.getTranslationTemplateFormats()
        self.assertEquals(
            [TranslationFileFormat.PO],
            all_formats)

        # With multiple templates of the same format, that
        # format is still returned only once.
        template2 = self.createTranslationTemplate("two")
        template2.source_file_format = TranslationFileFormat.PO
        all_formats = self.container.getTranslationTemplateFormats()
        self.assertEquals(
            [TranslationFileFormat.PO],
            all_formats)

        # With another template of a different format,
        # we get that format in a returned list.
        template3 = self.createTranslationTemplate("three")
        template3.source_file_format = TranslationFileFormat.XPI
        all_formats = self.container.getTranslationTemplateFormats()

        # Items are sorted by the format values, PO==1 < XPI==3.
        self.assertEquals(
            [TranslationFileFormat.PO, TranslationFileFormat.XPI],
            all_formats)


class TestProductSeriesHasTranslationTemplates(
    HasTranslationTemplatesTestMixin, TestCaseWithFactory):
    """Test implementation of IHasTranslationTemplates on ProductSeries."""

    def createTranslationTemplate(self, name=None, priority=0):
        potemplate = self.factory.makePOTemplate(
            name=name, productseries=self.container)
        potemplate.priority = priority
        return potemplate

    def createTranslationFile(self, name, priority=0):
        potemplate = self.createTranslationTemplate(name, priority)
        pofile = self.factory.makePOFile(
            language_code='es',
            potemplate=potemplate)
        return pofile

    def createPackaging(self):
        self.packaging = self.factory.makePackagingLink(
            productseries=self.container, in_ubuntu=True)
        return self.packaging

    def createSharingTranslationTemplate(self):
        return self.factory.makePOTemplate(
            sourcepackage=self.packaging.sourcepackage)

    def setUp(self):
        super(TestProductSeriesHasTranslationTemplates, self).setUp()
        self.container = self.factory.makeProductSeries()


class TestSourcePackageHasTranslationTemplates(
    HasTranslationTemplatesTestMixin, TestCaseWithFactory):
    """Test implementation of IHasTranslationTemplates on ProductSeries."""

    def createTranslationTemplate(self, name=None, priority=0):
        potemplate = self.factory.makePOTemplate(
            name=name, distroseries=self.container.distroseries,
            sourcepackagename=self.container.sourcepackagename)
        potemplate.priority = priority
        return potemplate

    def createTranslationFile(self, name, priority=0):
        potemplate = self.createTranslationTemplate(name, priority)
        pofile = self.factory.makePOFile(
            language_code='es',
            potemplate=potemplate)
        return pofile

    def createPackaging(self):
        self.packaging = self.factory.makePackagingLink(
            sourcepackage=self.container)
        return self.packaging

    def createSharingTranslationTemplate(self):
        return self.factory.makePOTemplate(
            productseries=self.packaging.productseries)

    def setUp(self):
        super(TestSourcePackageHasTranslationTemplates, self).setUp()
        self.container = self.factory.makeSourcePackage()


class TestDistroSeriesHasTranslationTemplates(
    HasTranslationTemplatesTestMixin, TestCaseWithFactory):
    """Test implementation of IHasTranslationTemplates on ProductSeries."""

    def createTranslationTemplate(self, name=None, priority=0):
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.container)
        potemplate = self.factory.makePOTemplate(
            name=name, distroseries=self.container,
            sourcepackagename=sourcepackage.sourcepackagename)
        potemplate.priority = priority
        return potemplate

    def createTranslationFile(self, name, priority=0):
        potemplate = self.createTranslationTemplate(name, priority)
        pofile = self.factory.makePOFile(
            language_code='es',
            potemplate=potemplate)
        return pofile

    def createPackaging(self):
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.container)
        self.packaging = self.factory.makePackagingLink(
            sourcepackage=sourcepackage)
        return self.packaging

    def createSharingTranslationTemplate(self):
        return self.factory.makePOTemplate(
            productseries=self.packaging.productseries)

    def setUp(self):
        super(TestDistroSeriesHasTranslationTemplates, self).setUp()
        self.container = self.factory.makeDistroSeries()

    def test_has_sharing_translation_templates__templates(self):
        # This attribute is always False for DistroSeries
        self.createPackaging()
        self.createSharingTranslationTemplate()
        self.assertFalse(self.container.has_sharing_translation_templates)
