# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from operator import attrgetter
import os.path

import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.database.interfaces import (
    ISlaveStore,
    IStore,
    )
from lp.services.librarianserver.testing.fake import FakeLibrarian
from lp.services.tarfile_helpers import LaunchpadWriteTarFile
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.model.translationimportqueue import (
    compose_approval_conflict_notice,
    list_distroseries_request_targets,
    list_product_request_targets,
    TranslationImportQueueEntry,
    )


class TestCanSetStatusBase:
    """Base for tests that check that canSetStatus works ."""

    layer = LaunchpadZopelessLayer
    dbuser = None
    entry = None

    def setUp(self):
        """Set up context to test in."""
        super(TestCanSetStatusBase, self).setUp()

        self.queue = getUtility(ITranslationImportQueue)
        self.rosetta_experts = (
            getUtility(ILaunchpadCelebrities).rosetta_experts)
        self.productseries = self.factory.makeProductSeries()
        self.productseries.driver = self.factory.makePerson()
        self.productseries.product.driver = self.factory.makePerson()
        self.uploaderperson = self.factory.makePerson()

    def _switch_dbuser(self):
        if self.dbuser != None:
            switch_dbuser(self.dbuser)

    def _assertCanSetStatus(self, user, entry, expected_list):
        # Helper to check for all statuses.
        # Could iterate RosettaImportStatus.items but listing them here
        # explicitly is better to read. They are sorted alphabetically.
        possible_statuses = [
            RosettaImportStatus.APPROVED,
            RosettaImportStatus.BLOCKED,
            RosettaImportStatus.DELETED,
            RosettaImportStatus.FAILED,
            RosettaImportStatus.IMPORTED,
            RosettaImportStatus.NEEDS_INFORMATION,
            RosettaImportStatus.NEEDS_REVIEW,
        ]
        self._switch_dbuser()
        # Do *not* use assertContentEqual here, as the order matters.
        self.assertEqual(expected_list,
            [entry.canSetStatus(status, user)
                 for status in possible_statuses])

    def test_canSetStatus_non_admin(self):
        # A non-privileged users cannot set any status.
        some_user = self.factory.makePerson()
        self._assertCanSetStatus(some_user, self.entry,
            #  A      B      D      F      I     NI     NR
            [False, False, False, False, False, False, False])

    def test_canSetStatus_rosetta_expert(self):
        # Rosetta experts are all-powerful, didn't you know that?
        self._assertCanSetStatus(self.rosetta_experts, self.entry,
            #  A     B     D     F     I    NI    NR
            [True, True, True, True, True, True, True])

    def test_canSetStatus_rosetta_expert_no_target(self):
        # If the entry has no import target set, even Rosetta experts
        # cannot set it to approved or imported.
        self.entry.potemplate = None
        self.entry.pofile = None
        self._assertCanSetStatus(self.rosetta_experts, self.entry,
            #  A      B     D     F     I    NI     NR
            [False, True, True, True, False, True, True])

    def test_canSetStatus_uploader(self):
        # The uploader can set some statuses.
        self._assertCanSetStatus(self.uploaderperson, self.entry,
            #  A      B     D     F      I     NI     NR
            [False, False, True, False, False, False, True])

    def test_canSetStatus_product_owner(self):
        # The owner (maintainer) of the product gets to set Blocked as well.
        owner = self.productseries.product.owner
        self._assertCanSetStatus(owner, self.entry,
            #  A     B     D     F      I     NI    NR
            [True, True, True, False, False, True, True])

    def test_canSetStatus_owner_and_uploader(self):
        # Corner case: Nothing changes if the maintainer is also the uploader.
        self.productseries.product.owner = self.uploaderperson
        self._assertCanSetStatus(self.uploaderperson, self.entry,
            #  A     B     D     F      I     NI    NR
            [True, True, True, False, False, True, True])

    def test_canSetStatus_driver(self):
        # The driver gets the same permissions as the maintainer.
        driver = self.productseries.driver
        self._assertCanSetStatus(driver, self.entry,
            #  A     B     D     F      I     NI    NR
            [True, True, True, False, False, True, True])

    def test_canSetStatus_driver_and_uploader(self):
        # Corner case: Nothing changes if the driver is also the uploader.
        self.productseries.driver = self.uploaderperson
        self._assertCanSetStatus(self.uploaderperson, self.entry,
            #  A     B     D     F      I     NI    NR
            [True, True, True, False, False, True, True])

    def test_canSetStatus_product_driver(self):
        # The driver of the product, too.
        driver = self.productseries.product.driver
        self._assertCanSetStatus(driver, self.entry,
            #  A      B     D     F     I     NI    NR
            [True, True, True, False, False, True, True])

    def test_canSetStatus_product_driver_and_uploader(self):
        # Corner case: Nothing changes if the driver is also the uploader.
        self.productseries.product.driver = self.uploaderperson
        self._assertCanSetStatus(self.uploaderperson, self.entry,
            #  A      B     D     F     I     NI    NR
            [True, True, True, False, False, True, True])

    def _setUpUbuntu(self):
        self.ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        self.ubuntu_group_owner = self.factory.makePerson()
        self.ubuntu.translationgroup = (
            self.factory.makeTranslationGroup(self.ubuntu_group_owner))

    def test_canSetStatus_ubuntu_translation_group(self):
        # Owners of the Ubuntu translation Groups can set entries to approved
        # that are targeted to Ubuntu.
        self._setUpUbuntu()
        ubuntu_entry = self.queue.addOrUpdateEntry(
            'demo.pot', '#demo', False, self.uploaderperson,
            distroseries=self.factory.makeDistroSeries(self.ubuntu),
            sourcepackagename=self.factory.makeSourcePackageName(),
            potemplate=self.potemplate)
        self._assertCanSetStatus(self.ubuntu_group_owner, ubuntu_entry,
            #  A     B     D     F      I     NI    NR
            [True, True, True, False, False, True, True])

    def test_canSetStatus_ubuntu_translation_group_not_ubuntu(self):
        # Outside of Ubuntu, owners of the Ubuntu translation Groups have no
        # powers.
        self._setUpUbuntu()
        self._assertCanSetStatus(self.ubuntu_group_owner, self.entry,
            #  A      B      D      F      I     NI     NR
            [False, False, False, False, False, False, False])


class TestCanSetStatusPOTemplate(TestCanSetStatusBase, TestCaseWithFactory):
    """Test canStatus applied to an entry with a POTemplate."""

    def setUp(self):
        """Create the entry to test on."""
        super(TestCanSetStatusPOTemplate, self).setUp()

        self.potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        self.entry = self.queue.addOrUpdateEntry(
            'demo.pot', '#demo', False, self.uploaderperson,
            productseries=self.productseries, potemplate=self.potemplate)


class TestCanSetStatusPOFile(TestCanSetStatusBase, TestCaseWithFactory):
    """Test canStatus applied to an entry with a POFile."""

    def setUp(self):
        """Create the entry to test on."""
        super(TestCanSetStatusPOFile, self).setUp()

        self.potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        self.pofile = self.factory.makePOFile(
            'eo', potemplate=self.potemplate)
        self.entry = self.queue.addOrUpdateEntry(
            'demo.po', '#demo', False, self.uploaderperson,
            productseries=self.productseries, pofile=self.pofile)


class TestCanSetStatusPOTemplateWithUPTJUser(TestCanSetStatusPOTemplate):
    """Test handling of the status of an upload queue entry as 'uptj' db user.

    The archive uploader needs to set (and therefore check) the status of a
    translations upload queue entry. It connects as a different database user
    ('upload_package_translations_job') and therefore we need to make sure
    that setStatus stays within the correct user's permissions.
    This is the version for POTemplate entries.
    """

    dbuser = 'upload_package_translations_job'


class TestCanSetStatusPOFileWithUPTJUser(TestCanSetStatusPOFile):
    """Test handling of the status of an upload queue entry as 'uptj' db user.

    The archive uploader needs to set (and therefore check) the status of a
    translations upload queue entry. It connects as a different database user
    ('upload_package_translations_job') and therefore we need to make sure
    that setStatus stays within the correct user's permissions.
    This is the version for POFile entries.
    """

    dbuser = 'upload_package_translations_job'


class TestGetGuessedPOFile(TestCaseWithFactory):
    """Test matching of PO files with respective templates and languages."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Set up context to test in."""
        super(TestGetGuessedPOFile, self).setUp()
        self.queue = getUtility(ITranslationImportQueue)
        self.factory = LaunchpadObjectFactory()
        self.distribution = self.factory.makeDistribution('boohoo')
        self.distroseries = self.factory.makeDistroSeries(self.distribution)
        self.uploaderperson = self.factory.makePerson()

    def createSourcePackageAndPOTemplate(self, sourcepackagename, template):
        """Create and return a source package and a POTemplate.

        Creates a source package in the self.distroseries with the passed-in
        sourcepackagename, and a template in that sourcepackage named
        template with the identical translation domain.
        """
        target_sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.distroseries)
        pot = self.factory.makePOTemplate(
            sourcepackagename=target_sourcepackage.sourcepackagename,
            distroseries=target_sourcepackage.distroseries,
            name=template, translation_domain=template)
        spn = self.factory.makeSourcePackageName(sourcepackagename)
        l10n_sourcepackage = self.factory.makeSourcePackage(
            sourcepackagename=spn,
            distroseries=self.distroseries)
        return (l10n_sourcepackage, pot)

    def _getGuessedPOFile(self, source_name, template_path):
        """Return new POTemplate and matched POFile for package and template.
        """
        template_name = os.path.basename(template_path)
        package, pot = self.createSourcePackageAndPOTemplate(
            source_name, template_name)
        queue_entry = self.queue.addOrUpdateEntry(
            '%s.po' % template_path, template_name, True, self.uploaderperson,
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        pofile = queue_entry.getGuessedPOFile()
        return (pot, pofile)

    def test_KDE4_language(self):
        # PO files 'something.po' in a package named like 'kde-l10n-sr'
        # belong in the 'something' translation domain as Serbian (sr)
        # translations.
        potemplate, pofile = self._getGuessedPOFile(
            'kde-l10n-sr', 'template')
        serbian = getUtility(ILanguageSet).getLanguageByCode('sr')
        self.assertEquals(potemplate, pofile.potemplate)
        self.assertEquals(serbian, pofile.language)

    def test_KDE4_language_country(self):
        # If package name is kde-l10n-engb, it needs to be mapped
        # to British English (en_GB).
        potemplate, pofile = self._getGuessedPOFile(
            'kde-l10n-engb', 'template')
        real_english = getUtility(ILanguageSet).getLanguageByCode('en_GB')
        self.assertEquals(potemplate, pofile.potemplate)
        self.assertEquals(real_english, pofile.language)

    def test_KDE4_language_variant(self):
        # If package name is kde-l10n-ca-valencia, it needs to be mapped
        # to Valencian variant of Catalan (ca@valencia).
        catalan_valencia = self.factory.makeLanguage(
            'ca@valencia', 'Catalan Valencia')
        potemplate, pofile = self._getGuessedPOFile(
            'kde-l10n-ca-valencia', 'template')
        self.assertEquals(potemplate, pofile.potemplate)
        self.assertEquals(catalan_valencia, pofile.language)

    def test_KDE4_language_subvariant(self):
        # PO file 'sr@test/something.po' in a package named like
        # 'kde-l10n-sr' belong in the 'something' translation domain
        # for "sr@test" language translations.
        serbian_test = self.factory.makeLanguage('sr@test')
        potemplate, pofile = self._getGuessedPOFile(
            'kde-l10n-sr', 'sr@test/template')
        self.assertEquals(potemplate, pofile.potemplate)
        self.assertEquals(serbian_test, pofile.language)

    def test_KDE4_language_at_sign(self):
        # PO file 'blah@test/something.po' in a package named like
        # 'kde-l10n-sr' belong in the 'something' translation domain
        # for "sr" language translations.
        serbian = getUtility(ILanguageSet).getLanguageByCode('sr')
        potemplate, pofile = self._getGuessedPOFile(
            'kde-l10n-sr', 'source/blah@test/template')
        self.assertEquals(potemplate, pofile.potemplate)
        self.assertEquals(serbian, pofile.language)


class TestProductOwnerEntryImporter(TestCaseWithFactory):
    """Test entries update when owners change."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestProductOwnerEntryImporter, self).setUp()
        self.product = self.factory.makeProduct()
        self.old_owner = self.product.owner
        self.new_owner = self.factory.makePerson()
        with person_logged_in(self.old_owner):
            self.product.driver = self.new_owner
        self.import_queue = getUtility(ITranslationImportQueue)

    def test_product_change_owner_changes_entry_importer(self):
        # Changing the Product owner also updates the importer of the entry.
        with person_logged_in(self.old_owner):
            entry = self.import_queue.addOrUpdateEntry(
                u'po/sr.po', 'foo', True, self.old_owner,
                productseries=self.product.series[0])
            self.product.owner = self.new_owner
        self.assertEqual(self.new_owner, entry.importer)

    def test_product_change_owner_preserves_entry_importer(self):
        # When the new owner already has an entry in the product's import
        # queue, the entry importer is not updated because that would
        # cause an non-unique key for the entry.
        with person_logged_in(self.new_owner):
            self.import_queue.addOrUpdateEntry(
                u'po/sr.po', 'foo', True, self.new_owner,
                productseries=self.product.series[0])
        with person_logged_in(self.old_owner):
            old_entry = self.import_queue.addOrUpdateEntry(
                u'po/sr.po', 'foo', True, self.old_owner,
                productseries=self.product.series[0])
            self.product.owner = self.new_owner
        self.assertEqual(self.old_owner, old_entry.importer)


class TestTranslationImportQueue(TestCaseWithFactory):
    """Tests for `TranslationImportQueue`."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestTranslationImportQueue, self).setUp()
        self.productseries = self.factory.makeProductSeries()
        self.importer = self.factory.makePerson()
        self.import_queue = getUtility(ITranslationImportQueue)

    def _makeFile(self, extension=None, directory=None):
        """Create a file with arbitrary name and content.

        Returns a tuple (name, content).
        """
        filename = self.factory.getUniqueString()
        if extension is not None:
            filename = "%s.%s" % (filename, extension)
        if directory is not None:
            filename = os.path.join(directory, filename)
        content = self.factory.getUniqueString()
        return (filename, content)

    def _getQueuePaths(self):
        entries = self.import_queue.getAllEntries(target=self.productseries)
        return [entry.path for entry in entries]

    def test_addOrUpdateEntriesFromTarball_baseline(self):
        # Files from a tarball are placed in the queue.
        files = dict((
            self._makeFile('pot'),
            self._makeFile('po'),
            self._makeFile('xpi'),
            ))
        tarfile_content = LaunchpadWriteTarFile.files_to_string(files)
        self.import_queue.addOrUpdateEntriesFromTarball(
            tarfile_content, True, self.importer,
            productseries=self.productseries)
        self.assertContentEqual(files.keys(), self._getQueuePaths())

    def test_addOrUpdateEntriesFromTarball_only_translation_files(self):
        # Only files with the right extensions are added.
        files = dict((
            self._makeFile(),
            ))
        tarfile_content = LaunchpadWriteTarFile.files_to_string(files)
        self.import_queue.addOrUpdateEntriesFromTarball(
            tarfile_content, True, self.importer,
            productseries=self.productseries)
        self.assertEqual([], self._getQueuePaths())

    def test_addOrUpdateEntriesFromTarball_path(self):
        # File names are store with full path.
        files = dict((
            self._makeFile('pot', 'directory'),
            ))
        tarfile_content = LaunchpadWriteTarFile.files_to_string(files)
        self.import_queue.addOrUpdateEntriesFromTarball(
            tarfile_content, True, self.importer,
            productseries=self.productseries)
        self.assertEqual(files.keys(), self._getQueuePaths())

    def test_addOrUpdateEntriesFromTarball_path_leading_slash(self):
        # Leading slashes are stripped from path names.
        path, content = self._makeFile('pot', '/directory')
        files = dict(((path, content),))
        tarfile_content = LaunchpadWriteTarFile.files_to_string(files)
        self.import_queue.addOrUpdateEntriesFromTarball(
            tarfile_content, True, self.importer,
            productseries=self.productseries)
        stripped_path = path.lstrip('/')
        self.assertEqual([stripped_path], self._getQueuePaths())

    def test_addOrUpdateEntry_detects_conflicts(self):
        pot = self.factory.makePOTemplate(translation_domain='domain')
        uploader = self.factory.makePerson()
        pofile = self.factory.makePOFile(potemplate=pot, language_code='fr')

        # Add an import queue entry with a single pofile for a template.
        tiqe1 = self.factory.makeTranslationImportQueueEntry(
            path=pofile.path, productseries=pot.productseries,
            potemplate=pot, uploader=uploader)

        # Add an import queue entry for a the same pofile, but done
        # directly on the pofile object (i.e. more specific).
        tiqe2 = self.factory.makeTranslationImportQueueEntry(
            path=pofile.path, productseries=pot.productseries,
            potemplate=pot, pofile=pofile, uploader=uploader)

        self.assertEquals(tiqe1, tiqe2)

    def test_reportApprovalConflict_sets_error_output_just_once(self):
        # Repeated occurrence of the same approval conflict will not
        # result in repeated setting of error_output.
        series = self.factory.makeProductSeries()
        domain = self.factory.getUniqueString()
        templates = [
            self.factory.makePOTemplate(
                productseries=series, translation_domain=domain)
            for counter in xrange(3)]
        entry = removeSecurityProxy(
            self.factory.makeTranslationImportQueueEntry())

        entry.reportApprovalConflict(domain, len(templates), templates)
        original_error = entry.error_output
        transaction.commit()

        # Try reporting the conflict again, with the templates
        # reshuffled to see if reportApprovalConflict can be fooled into
        # thinking it's a different error.  Make as sure as we can that
        # entry.error_output is not modified.
        slave_entry = ISlaveStore(entry).get(
            TranslationImportQueueEntry, entry.id)
        slave_entry.setErrorOutput = FakeMethod()
        slave_entry.reportApprovalConflict(
            domain, len(templates), reversed(templates))
        self.assertEqual(original_error, slave_entry.error_output)
        self.assertIn(domain, original_error)
        self.assertEqual(0, slave_entry.setErrorOutput.call_count)


class TestHelpers(TestCaseWithFactory):
    """Tests for stand-alone helper functions in the module."""

    layer = ZopelessDatabaseLayer

    def clearQueue(self):
        """Clear the translations import queue."""
        store = IStore(TranslationImportQueueEntry)
        store.find(TranslationImportQueueEntry).remove()

    def test_compose_approval_conflict_notice_summarizes_conflict(self):
        # The output from compose_approval_conflict_notice summarizes
        # the conflict: what translation domain is affected and how many
        # clashing templates are there?
        domain = self.factory.getUniqueString()
        num_templates = self.factory.getUniqueInteger()

        notice = compose_approval_conflict_notice(domain, num_templates, [])

        self.assertIn("translation domain '%s'" % domain, notice)
        self.assertIn(
            "There are %d competing templates" % num_templates, notice)

    def test_compose_approval_conflict_notice_shows_sample(self):
        # The notice includes the list of sample templates' display
        # names, one per line, separated by semicolons but terminated
        # with a full stop.
        class FakePOTemplate:
            def __init__(self, displayname):
                self.displayname = displayname

        domain = self.factory.getUniqueString()
        samples = [
            FakePOTemplate(self.factory.getUniqueString())
            for counter in range(3)]
        sorted_samples = sorted(samples, key=attrgetter('displayname'))

        notice = compose_approval_conflict_notice(domain, 3, samples)

        self.assertIn(
            ';\n'.join([
                '"%s"' % sample.displayname for sample in sorted_samples]),
            notice)
        self.assertIn('"%s".\n' % sorted_samples[-1].displayname, notice)

    def test_compose_approval_conflict_notice_says_when_there_is_more(self):
        # If there are more clashing templates than the sample lists,
        # the list of names ends with a note to that effect.
        class FakePOTemplate:
            def __init__(self, displayname):
                self.displayname = displayname

        domain = self.factory.getUniqueString()
        samples = [
            FakePOTemplate(self.factory.getUniqueString())
            for counter in range(3)]
        samples.sort(key=attrgetter('displayname'))

        notice = compose_approval_conflict_notice(domain, 4, samples)

        self.assertIn(
            '"%s";\nand more (not shown here).\n' % samples[-1].displayname,
            notice)

    def test_list_product_request_targets_orders_by_product_name(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        names = ['c', 'a', 'b']
        products = [self.factory.makeProduct(name=name) for name in names]
        productseries = [
            self.factory.makeProductSeries(product=product)
            for product in products]
        for series in productseries:
            self.factory.makeTranslationImportQueueEntry(productseries=series)
        self.assertEqual(
            sorted(names),
            [
                product.name
                for product in list_product_request_targets(None, True)])

    def test_list_product_request_filters_private_products(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner,
            information_type=InformationType.PROPRIETARY)
        self.factory.makeTranslationImportQueueEntry(
            productseries=self.factory.makeProductSeries(product=product))
        self.assertEqual([], list_product_request_targets(None, True))
        self.assertEqual([product], list_product_request_targets(owner, True))

    def test_list_product_request_targets_ignores_distro_uploads(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        self.factory.makeTranslationImportQueueEntry(
            distroseries=self.factory.makeDistroSeries())
        self.assertEqual([], list_product_request_targets(None, True))

    def test_list_product_request_targets_ignores_inactive_products(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        product = self.factory.makeProduct()
        product.active = False
        self.factory.makeTranslationImportQueueEntry(
            productseries=self.factory.makeProductSeries(product=product))
        self.assertEqual([], list_product_request_targets(None, False))

    def test_list_product_request_targets_does_not_duplicate(self):
        # list_product_request_targets will list a product only once.
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        product = self.factory.makeProduct()
        productseries = [
            self.factory.makeProductSeries(product=product)
            for counter in range(2)]
        for series in productseries:
            for counter in range(2):
                self.factory.makeTranslationImportQueueEntry(
                    productseries=series)
        self.assertEqual([product], list_product_request_targets(None, True))

    def test_list_product_request_targets_filters_status(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        entry_status = RosettaImportStatus.APPROVED
        other_status = RosettaImportStatus.NEEDS_REVIEW
        entry = self.factory.makeTranslationImportQueueEntry(
            productseries=self.factory.makeProductSeries())
        removeSecurityProxy(entry).status = entry_status
        self.assertEqual(
            [],
            list_product_request_targets(
                None,
                TranslationImportQueueEntry.status == other_status))
        self.assertEqual(
            [entry.productseries.product],
            list_product_request_targets(
                None,
                TranslationImportQueueEntry.status == entry_status))

    def test_list_distroseries_request_targets_orders_by_names(self):
        # list_distroseries_request_targets returns distroseries sorted
        # primarily by Distribution.name, and secondarily by
        # DistroSeries.name.
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        names = ['c', 'a', 'b']
        distros = [
            self.factory.makeDistribution(name=distro_name)
            for distro_name in names]
        for distro in distros:
            for series_name in names:
                series = self.factory.makeDistroSeries(
                    distribution=distro, name=series_name)
                series.defer_translation_imports = False
                self.factory.makeTranslationImportQueueEntry(
                    distroseries=series)
        self.assertEqual(
            [
                ('a', 'a'), ('a', 'b'), ('a', 'c'),
                ('b', 'a'), ('b', 'b'), ('b', 'c'),
                ('c', 'a'), ('c', 'b'), ('c', 'c'),
            ],
            [
                (series.distribution.name, series.name)
                for series in list_distroseries_request_targets(True)])

    def test_list_distroseries_request_targets_ignores_product_uploads(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        self.factory.makeTranslationImportQueueEntry(
            productseries=self.factory.makeProductSeries())
        self.assertEqual([], list_distroseries_request_targets(True))

    def test_list_distroseries_request_targets_ignores_inactive_series(self):
        # Distroseries whose imports have been suspended are not
        # included in list_distroseries_request_targets.
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        series = self.factory.makeDistroSeries()
        series.defer_translation_imports = True
        self.factory.makeTranslationImportQueueEntry(distroseries=series)
        self.assertEqual([], list_distroseries_request_targets(True))

    def test_list_distroseries_request_targets_does_not_duplicate(self):
        # list_distroseries_request_targets will list a distroseries
        # only once.
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        series = self.factory.makeDistroSeries()
        series.defer_translation_imports = False
        for counter in range(2):
            self.factory.makeTranslationImportQueueEntry(distroseries=series)
        self.assertEqual([series], list_distroseries_request_targets(True))

    def test_list_distroseries_request_targets_filters_status(self):
        self.clearQueue()
        self.useFixture(FakeLibrarian())
        entry_status = RosettaImportStatus.APPROVED
        other_status = RosettaImportStatus.NEEDS_REVIEW
        series = self.factory.makeDistroSeries()
        series.defer_translation_imports = False
        entry = self.factory.makeTranslationImportQueueEntry(
            distroseries=series)
        removeSecurityProxy(entry).status = entry_status
        self.assertEqual(
            [],
            list_distroseries_request_targets(
                TranslationImportQueueEntry.status == other_status))
        self.assertEqual(
            [entry.distroseries],
            list_distroseries_request_targets(
                TranslationImportQueueEntry.status == entry_status))
