# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View tests for ProductRelease pages."""

__metaclass__ = type


from lp.app.enums import InformationType
from lp.services.webapp.escaping import html_escape
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class ProductReleaseAddDownloadFileViewTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def makeForm(self, file_name):
        upload = self.factory.makeFakeFileUpload(filename=file_name)
        form = {
            'field.description': 'App 0.1 tarball',
            'field.contenttype': 'CODETARBALL',
            'field.filecontent': upload,
            'field.actions.add': 'Upload',
            }
        return form

    def test_add_file(self):
        release = self.factory.makeProductRelease()
        maintainer = release.milestone.product.owner
        form = self.makeForm('pting.tar.gz')
        with person_logged_in(maintainer):
            view = create_initialized_view(
                release, '+adddownloadfile', form=form)
        self.assertEqual([], view.errors)
        notifications = [
            nm.message for nm in view.request.response.notifications]
        self.assertEqual(
            [html_escape("Your file 'pting.tar.gz' has been uploaded.")],
            notifications)

    def test_add_file_duplicate(self):
        release = self.factory.makeProductRelease()
        maintainer = release.milestone.product.owner
        release_file = self.factory.makeProductReleaseFile(release=release)
        file_name = release_file.libraryfile.filename
        form = self.makeForm(file_name)
        with person_logged_in(maintainer):
            view = create_initialized_view(
                release, '+adddownloadfile', form=form)
        self.assertEqual(
            [html_escape("The file '%s' is already uploaded." % file_name)],
            view.errors)

    def test_refuses_proprietary_products(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner, information_type=InformationType.PROPRIETARY)
        with person_logged_in(owner):
            release = self.factory.makeProductRelease(product=product)
            form = self.makeForm('something.tar.gz')
            view = create_initialized_view(
                release, '+adddownloadfile', form=form)
        self.assertEqual(
            ['Only public projects can have download files.'], view.errors)
