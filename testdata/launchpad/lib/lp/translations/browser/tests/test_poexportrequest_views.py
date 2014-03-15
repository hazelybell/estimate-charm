# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.security.proxy import removeSecurityProxy

from lp.services.database.interfaces import IStore
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.translations.browser.pofile import POExportView
from lp.translations.browser.potemplate import POTemplateExportView
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.model.poexportrequest import POExportRequest


def get_poexportrequests(include_format=False):
    """Get (template, pofile, [format]) tuples of all pending export requests.

    :param include_format: Include the content of the format column in the
        tuple.
    """
    requests = IStore(POExportRequest).find(POExportRequest)
    if include_format:
        return [
            (request.potemplate, request.pofile, request.format)
            for request in requests]
    else:
        return [
            (request.potemplate, request.pofile)
            for request in requests]


class TestPOTEmplateExportView(TestCaseWithFactory):
    """Test POTEmplateExportView."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPOTEmplateExportView, self).setUp()
        self.potemplate = self.factory.makePOTemplate()
        # All exports can be requested by an unprivileged user.
        self.translator = self.factory.makePerson()

    def _createView(self, form):
        login_person(self.translator)
        request = LaunchpadTestRequest(method='POST', form=form)
        view = POTemplateExportView(self.potemplate, request)
        view.initialize()
        return view

    def test_request_all_only_template(self):
        # Selecting 'all' will place the template into the request queue.
        self._createView({'what': 'all', 'format': 'PO'})

        self.assertContentEqual(
            [(self.potemplate, None)], get_poexportrequests())

    def test_request_all_add_pofile(self):
        # Selecting 'all' will also place any pofiles for the template into
        # the request queue.
        pofile = self.factory.makePOFile(potemplate=self.potemplate)
        self._createView({'what': 'all', 'format': 'PO'})

        self.assertContentEqual(
            [(self.potemplate, None), (self.potemplate, pofile)],
            get_poexportrequests())

    def test_request_some_potemplate(self):
        # Using 'some' allows to select only the template.
        pofile = self.factory.makePOFile(potemplate=self.potemplate)
        self._createView({'what': 'some', 'potemplate': True, 'format': 'PO'})

        self.assertContentEqual(
            [(self.potemplate, None)], get_poexportrequests())

    def test_request_some_pofile(self):
        # Using 'some' allows to select only a pofile.
        pofile = self.factory.makePOFile(potemplate=self.potemplate)
        self._createView({
            'what': 'some',
            pofile.language.code: True,
            'format': 'PO'})

    def test_request_some_various(self):
        # Using 'some' allows to select various files.
        pofile1 = self.factory.makePOFile(potemplate=self.potemplate)
        pofile2 = self.factory.makePOFile(potemplate=self.potemplate)
        self._createView({
            'what': 'some',
            'potemplate': True,
            pofile2.language.code: True,
            'format': 'PO'})

        self.assertContentEqual(
            [(self.potemplate, None), (self.potemplate, pofile2)],
            get_poexportrequests())

    def test_request_format_po(self):
        # It is possible to request the PO format.
        self._createView({'what': 'all', 'format': 'PO'})

        self.assertContentEqual(
            [(self.potemplate, None, TranslationFileFormat.PO)],
            get_poexportrequests(include_format=True))

    def test_request_format_mo(self):
        # It is possible to request the MO format.
        self._createView({'what': 'all', 'format': 'MO'})

        self.assertContentEqual(
            [(self.potemplate, None, TranslationFileFormat.MO)],
            get_poexportrequests(include_format=True))


class TestPOExportView(TestCaseWithFactory):
    """Test POExportView."""

    layer = DatabaseFunctionalLayer

    def _createView(self, pofile, form=None):
        # All exports can be requested by an unprivileged user.
        login_person(self.factory.makePerson())
        if form is None:
            request = LaunchpadTestRequest()
        else:
            request = LaunchpadTestRequest(method='POST', form=form)
        view = POExportView(pofile, request)
        view.initialize()
        return view

    def test_request_format_po(self):
        # It is possible to request an export in the PO format.
        pofile = self.factory.makePOFile()
        self._createView(pofile, {'format': 'PO'})

        self.assertContentEqual(
            [(pofile.potemplate, pofile, TranslationFileFormat.PO)],
            get_poexportrequests(include_format=True))

    def test_request_format_mo(self):
        # It is possible to request an export in the MO format.
        pofile = self.factory.makePOFile()
        self._createView(pofile, {'format': 'MO'})

        self.assertContentEqual(
            [(pofile.potemplate, pofile, TranslationFileFormat.MO)],
            get_poexportrequests(include_format=True))

    def _makeUbuntuTemplateAndPOFile(self, upstream_pofile=None):
        """Create a sharing template in Ubuntu with a POFile to go with it."""
        if upstream_pofile is None:
            upstream_pofile = self.factory.makePOFile()
        upstream_potemplate = upstream_pofile.potemplate
        upstream_series = upstream_potemplate.productseries
        template_name = upstream_potemplate.name
        language = upstream_pofile.language

        packaging = self.factory.makePackagingLink(
            productseries=upstream_series, in_ubuntu=True)
        naked_distribution = removeSecurityProxy(
            packaging.distroseries.distribution)
        naked_distribution.translation_focus = packaging.distroseries

        potemplate = self.factory.makePOTemplate(
            sourcepackage=packaging.sourcepackage, name=template_name)

        # The sharing POFile is created automatically when the template is
        # created because self.pofile already exists.
        return (potemplate, potemplate.getPOFileByLang(language.code))

    def test_request_partial_po_upstream(self):
        # Partial po exports are requested by an extra check box.
        # For an upstream project, the export is requested on the
        # corresponding (same language, sharing template) on the Ubuntu side.
        ubuntu_potemplate, ubuntu_pofile = self._makeUbuntuTemplateAndPOFile()

        self._createView(
            ubuntu_pofile, {'format': 'PO', 'pochanged': 'POCHANGED'})

        expected = (
            ubuntu_potemplate,
            ubuntu_pofile,
            TranslationFileFormat.POCHANGED,
            )
        self.assertContentEqual(
            [expected], get_poexportrequests(include_format=True))

    def test_request_partial_po_ubuntu(self):
        # Partial po exports are requested by an extra check box.
        # For an Ubuntu package, the export is requested on the file itself.
        upstream_pofile = self.factory.makePOFile()
        ubuntu_potemplate, ubuntu_pofile = self._makeUbuntuTemplateAndPOFile(
            upstream_pofile)

        self._createView(
            upstream_pofile, {'format': 'PO', 'pochanged': 'POCHANGED'})

        self.assertContentEqual(
            [(ubuntu_potemplate, ubuntu_pofile,
                TranslationFileFormat.POCHANGED)],
            get_poexportrequests(include_format=True))

    def test_request_partial_po_no_link(self):
        # Partial po exports are requested by an extra check box.
        # Without a packaging link, no request is created.
        pofile = self.factory.makePOFile()
        self._createView(pofile, {'format': 'PO', 'pochanged': 'POCHANGED'})

        self.assertContentEqual([], get_poexportrequests())

    def test_request_partial_mo(self):
        # With the MO format, the partial export check box is ignored.
        pofile = self.factory.makePOFile()
        self._createView(pofile, {'format': 'MO', 'pochanged': 'POCHANGED'})

        self.assertContentEqual(
            [(pofile.potemplate, pofile, TranslationFileFormat.MO)],
            get_poexportrequests(include_format=True))

    def test_pochanged_option_available_ubuntu(self):
        # The option for partial exports is always available on a source
        # package.
        ubuntu_potemplate, ubuntu_pofile = self._makeUbuntuTemplateAndPOFile()
        view = self._createView(ubuntu_pofile)

        self.assertTrue(view.has_pochanged_option)

    def test_pochanged_option_available_ubuntu_no_upstream(self):
        # The option for partial exports is always available on a source
        # package, even if there is no upstream pofile.
        ubuntu_pofile = self.factory.makePOFile(side=TranslationSide.UBUNTU)
        view = self._createView(ubuntu_pofile)

        self.assertTrue(view.has_pochanged_option)

    def test_pochanged_option_available_upstream(self):
        # The option for partial exports is only available upstream if a
        # POFile can be found in Ubuntu.
        upstream_pofile = self.factory.makePOFile()
        self._makeUbuntuTemplateAndPOFile(upstream_pofile)
        view = self._createView(upstream_pofile)

        self.assertTrue(view.has_pochanged_option)

    def test_pochanged_option_not_available_upstream(self):
        # The option for partial exports is not available upstream if no
        # POFile can be found in Ubuntu.
        pofile = self.factory.makePOFile()
        view = self._createView(pofile)

        self.assertFalse(view.has_pochanged_option)
