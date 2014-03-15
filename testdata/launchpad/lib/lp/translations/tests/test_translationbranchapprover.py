# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translation File Auto Approver tests."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.name import valid_name
from lp.services.librarianserver.testing.fake import FakeLibrarian
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.model.approver import TranslationBranchApprover


class TestTranslationBranchApprover(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestTranslationBranchApprover, self).setUp()
        self.useFixture(FakeLibrarian())
        self.queue = getUtility(ITranslationImportQueue)
        self.series = self.factory.makeProductSeries()

    def _upload_file(self, upload_path):
        # Put a template or translation file in the import queue.
        return self.queue.addOrUpdateEntry(upload_path,
            self.factory.getUniqueString(), True, self.series.owner,
            productseries=self.series)

    def _createTemplate(self, path, domain, productseries=None):
        # Create a template in the database
        if productseries is None:
            productseries = self.series
        return self.factory.makePOTemplate(
            productseries=productseries,
            name=domain.replace('_', '-'),
            translation_domain=domain,
            path=path)

    def _createApprover(self, file_or_files):
        if not isinstance(file_or_files, (tuple, list)):
            paths = (file_or_files,)
        else:
            paths = file_or_files
        return TranslationBranchApprover(paths, productseries=self.series)

    def test_new_template_approved(self):
        # The approver puts new entries in the Approved state.
        template_path = self.factory.getUniqueString() + u'.pot'
        entry = self._upload_file(template_path)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entry.status)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)

    def test_new_template_without_domain_in_path_uses_project_name(self):
        # When a template upload for a project has a generic path, it
        # can still be approved.  The template will have a name and
        # domain based on the project's name.
        template_path = u'messages.pot'
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)
        self.assertEqual(self.series.product.name, entry.potemplate.name)
        self.assertEqual(
            self.series.product.name, entry.potemplate.translation_domain)

    def test_new_package_template_without_domain_is_not_approved(self):
        # If an upload for a package has no information that a template
        # name or domain could be based on, it is not approved.
        # Template domains for packages must generally be unique for the
        # entire distribution, but in practice it's too variable to
        # figure out here.
        package = self.factory.makeSourcePackage()
        package_kwargs = {
            'distroseries': package.distroseries,
            'sourcepackagename': package.sourcepackagename,
        }
        entry = self.queue.addOrUpdateEntry(
            'messages.pot', self.factory.getUniqueString(), True,
            self.factory.makePerson(), **package_kwargs)

        TranslationBranchApprover(entry.path, **package_kwargs).approve(entry)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entry.status)

    def test_new_template_not_a_template(self):
        # Only template files will be approved currently.
        path = u'eo.po'
        entry = self._upload_file(path)
        self._createApprover(path).approve(entry)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entry.status)

    def test_new_template_domain(self):
        # The approver gets the translation domain for the entry from the
        # file path if possible.
        translation_domain = self.factory.getUniqueString()
        template_path = translation_domain + u'.pot'
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(
            translation_domain, entry.potemplate.translation_domain)

    def test_new_template_domain_with_xpi(self):
        # For xpi files, template files are always called "en-US.xpi" so
        # the approver won't use that string for a domain.  It'll fall
        # back to the next possibility, which is the directory.
        translation_domain = self.factory.getUniqueString()
        template_path = translation_domain + '/en-US.xpi'
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(
            translation_domain, entry.potemplate.translation_domain)

    def test_template_name(self):
        # The name is derived from the file name and must be a valid name.
        translation_domain = (u'Invalid-Name_with illegal#Characters')
        template_path = translation_domain + u'.pot'
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertTrue(valid_name(entry.potemplate.name))
        self.assertEqual(u'invalid-name-withillegalcharacters',
                         entry.potemplate.name)

    def test_replace_existing_approved(self):
        # Template files that replace existing entries are approved.
        translation_domain = self.factory.getUniqueString()
        template_path = translation_domain + u'.pot'
        self._createTemplate(template_path, translation_domain)
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)

    def test_replace_existing_potemplate(self):
        # When replacing an existing template, the queue entry is linked
        # to that existing entry.
        translation_domain = self.factory.getUniqueString()
        template_path = translation_domain + u'.pot'
        potemplate = self._createTemplate(template_path, translation_domain)
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(potemplate, entry.potemplate)

    def test_ignore_existing_inactive_potemplate(self):
        # When replacing an existing inactive template, the entry is not
        # approved and no template is created for it.
        translation_domain = self.factory.getUniqueString()
        template_path = translation_domain + u'.pot'
        potemplate = self._createTemplate(template_path, translation_domain)
        potemplate.setActive(False)
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entry.status)
        self.assertEqual(None, entry.potemplate)

    def test_replace_existing_any_path(self):
        # If just one template file is found in the tree and just one
        # POTemplate is in the database, the upload is always approved.
        existing_domain = self.factory.getUniqueString()
        existing_path = existing_domain + u'.pot'
        potemplate = self._createTemplate(existing_path, existing_domain)
        template_path = self.factory.getUniqueString() + u'.pot'
        entry = self._upload_file(template_path)
        self._createApprover(template_path).approve(entry)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)
        self.assertEqual(potemplate, entry.potemplate)

    def test_replace_existing_generic_path_approved(self):
        # If an upload file has a generic path that does not yield a
        # translation domain, it is still approved if an entry with the
        # same file name exists.
        translation_domain = self.factory.getUniqueString()
        generic_path = u'po/messages.pot'
        self._createTemplate(generic_path, translation_domain)
        entry = self._upload_file(generic_path)
        self._createApprover(generic_path).approve(entry)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)

    def test_does_not_replace_domain_if_path_contains_no_useful_name(self):
        # For an upload to a package (where there's no fallback to a
        # product name), if the path contains no meaningful domain name
        # but matches that of an existing template, even though the
        # entry gets approved for import into that template, the
        # existing template's domain name stays as it was.
        generic_path = u'po/messages.pot'

        package = self.factory.makeSourcePackage()
        package_kwargs = {
            'distroseries': package.distroseries,
            'sourcepackagename': package.sourcepackagename,
        }
        template = self.factory.makePOTemplate(**package_kwargs)
        original_domain = template.translation_domain
        entry = self.queue.addOrUpdateEntry(
            generic_path, self.factory.getUniqueString(), True,
            template.owner, potemplate=template, **package_kwargs)

        approver = TranslationBranchApprover(generic_path, **package_kwargs)
        approver.approve(entry)
        self.assertEqual(original_domain, template.translation_domain)

    def test_add_template(self):
        # When adding a template to an existing one it is approved if the
        # approver is told about both template files in the tree.
        existing_domain = self.factory.getUniqueString()
        existing_path = u"%s/%s.pot" % (existing_domain, existing_domain)
        self._createTemplate(existing_path, existing_domain)
        new_domain = self.factory.getUniqueString()
        new_path = u"%s/%s.pot" % (new_domain, new_domain)
        entry = self._upload_file(new_path)
        self._createApprover((existing_path, new_path)).approve(entry)
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)
        self.assertEqual(new_domain, entry.potemplate.translation_domain)

    def test_upload_multiple_new_templates(self):
        # Multiple new templates can be added using the same
        # TranslationBranchApprover instance.
        pot_path1 = self.factory.getUniqueString() + ".pot"
        pot_path2 = self.factory.getUniqueString() + ".pot"
        entry1 = self._upload_file(pot_path1)
        entry2 = self._upload_file(pot_path2)
        approver = self._createApprover((pot_path1, pot_path2))
        approver.approve(entry1)
        self.assertEqual(RosettaImportStatus.APPROVED, entry1.status)
        approver.approve(entry2)
        self.assertEqual(RosettaImportStatus.APPROVED, entry2.status)

    def test_duplicate_template_name(self):
        # If two templates in the branch indicate the same translation
        # domain, they are in conflict and will not be approved.
        pot_path1 = "po/foo_domain.pot"
        pot_path2 = "foo_domain/messages.pot"
        entry1 = self._upload_file(pot_path1)
        entry2 = self._upload_file(pot_path2)
        approver = self._createApprover((pot_path1, pot_path2))
        approver.approve(entry1)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entry1.status)
        approver.approve(entry2)
        self.assertEqual(RosettaImportStatus.NEEDS_REVIEW, entry2.status)

    def test_approve_only_if_needs_review(self):
        # If an entry is not in NEEDS_REVIEW state, it must not be approved.
        pot_path = self.factory.getUniqueString() + ".pot"
        entry = self._upload_file(pot_path)
        entry.potemplate = self.factory.makePOTemplate()
        not_approve_status = (
            RosettaImportStatus.IMPORTED,
            RosettaImportStatus.DELETED,
            RosettaImportStatus.FAILED,
            RosettaImportStatus.BLOCKED,
            )
        for status in not_approve_status:
            entry.setStatus(
                status, getUtility(ILaunchpadCelebrities).rosetta_experts)
            self._createApprover(pot_path).approve(entry)
            self.assertEqual(status, entry.status)

    def test_approveNewSharingTemplate(self):
        # When the approver creates a new template, the new template
        # gets copies of any existing POFiles for templates that it will
        # share translations with.
        domain = self.factory.getUniqueString()
        pot_path = domain + ".pot"
        trunk = self.series.product.getSeries('trunk')
        trunk_template = self._createTemplate(
            pot_path, domain=domain, productseries=trunk)
        dutch_pofile = self.factory.makePOFile(
            'nl', potemplate=trunk_template)
        entry = self._upload_file(pot_path)
        self._createApprover(pot_path).approve(entry)

        # This really did create a new template.
        self.assertNotEqual(None, entry.potemplate)
        self.assertNotEqual(trunk_template, entry.potemplate)
        self.assertEqual(trunk_template.name, entry.potemplate.name)

        # The new template also has a Dutch translation of its own.
        new_dutch_pofile = entry.potemplate.getPOFileByLang('nl')
        self.assertNotEqual(None, new_dutch_pofile)
        self.assertNotEqual(dutch_pofile, new_dutch_pofile)


class TestBranchApproverPrivileges(TestCaseWithFactory):
    """Test database privileges required for the branch approver.

    Runs the `TranslationsBranchApprover` through a few scenarios that
    exercise its database privileges.  This is a slow test because it
    needs to commit a lot; it's not a place to verify anything other
    than the database privileges.
    """

    layer = LaunchpadZopelessLayer

    def becomeTheApprover(self):
        """Assume the database role of the translations branch scanner.

        This is the role that the TranslationsBranchApprover is actually
        run under.
        """
        switch_dbuser('translationsbranchscanner')

    def test_approve_new_product_template(self):
        # The approver has sufficient privileges to create a new
        # template on a product.
        template = self.factory.makePOTemplate()
        entry = self.factory.makeTranslationImportQueueEntry(
            'messages.pot', potemplate=template,
            productseries=template.productseries)

        self.becomeTheApprover()
        approver = TranslationBranchApprover(
            [template.path], productseries=template.productseries)
        approver.approve(entry)

    def test_approve_new_package_template(self):
        # The approver has sufficient privileges to create a new
        # template on a source package.
        package = self.factory.makeSourcePackage()
        package_kwargs = {
            'distroseries': package.distroseries,
            'sourcepackagename': package.sourcepackagename,
        }
        template = self.factory.makePOTemplate(**package_kwargs)
        entry = self.factory.makeTranslationImportQueueEntry(
            path='messages.pot', potemplate=template, **package_kwargs)

        self.becomeTheApprover()
        approver = TranslationBranchApprover(
            [template.path], **package_kwargs)
        approver.approve(entry)

    def test_approve_sharing_template(self):
        # The approver has sufficient privileges to approve templates
        # that will have POFiles copied over from sharing templates.
        productseries = self.factory.makeProductSeries()
        package = self.factory.makeSourcePackage()
        package_kwargs = {
            'distroseries': package.distroseries,
            'sourcepackagename': package.sourcepackagename,
        }
        self.factory.makePackagingLink(
            productseries=productseries, **package_kwargs)

        template_name = self.factory.getUniqueString()
        template_path = "%s.pot" % template_name

        self.factory.makePOFile(
            potemplate=self.factory.makePOTemplate(
                name=template_name, productseries=productseries))
        self.factory.makePOFile(
            potemplate=self.factory.makePOTemplate(
                name=template_name, **package_kwargs))

        new_series = self.factory.makeProductSeries(
            product=productseries.product)
        entry = self.factory.makeTranslationImportQueueEntry(
            path=template_path, productseries=new_series)

        self.becomeTheApprover()
        TranslationBranchApprover([template_path], new_series).approve(entry)
