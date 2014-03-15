# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


import re

from lazr.restful.interfaces import IJSONRequestCache
from soupmatchers import (
    HTMLContains,
    Tag,
    )

from lp.app.enums import ServiceUsage
from lp.services.webapp import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    BrowserTestCase,
    EventRecorder,
    extract_lp_cache,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )
from lp.translations.browser.sourcepackage import (
    SourcePackageTranslationSharingDetailsView,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )
from lp.translations.model.translationpackagingjob import TranslationMergeJob


def make_initialized_view(sourcepackage):
    view = SourcePackageTranslationSharingDetailsView(
        sourcepackage, LaunchpadTestRequest())
    view.initialize()
    return view


class ConfigureScenarioMixin:
    """Provide a method for project configuration."""

    def configureUpstreamProject(self, productseries,
            set_upstream_branch=False,
            translations_usage=ServiceUsage.UNKNOWN,
            translation_import_mode=TranslationsBranchImportMode.NO_IMPORT):
        """Configure the productseries and its product as an upstream project.
        """
        with person_logged_in(productseries.product.owner):
            if set_upstream_branch:
                productseries.branch = self.factory.makeBranch(
                    product=productseries.product)
            productseries.product.translations_usage = translations_usage
            productseries.translations_autoimport_mode = (
                translation_import_mode)

    def makeFullyConfiguredSharing(self, suppress_merge_job=True):
        """Setup a fully configured sharing scenario."""
        if suppress_merge_job:
            # Intercept the job creation request.
            with EventRecorder():
                packaging = self.factory.makePackagingLink(in_ubuntu=True)
        else:
            packaging = self.factory.makePackagingLink(in_ubuntu=True)
        productseries = packaging.productseries
        sourcepackage = packaging.sourcepackage
        self.configureUpstreamProject(
            productseries,
            set_upstream_branch=True,
            translations_usage=ServiceUsage.LAUNCHPAD,
            translation_import_mode=(
                TranslationsBranchImportMode.IMPORT_TRANSLATIONS))
        return (sourcepackage, productseries)

    def endMergeJob(self, sourcepackage):
        """End the merge job that was automatically created."""
        for job in TranslationMergeJob.iterReady():
            if job.sourcepackage == sourcepackage:
                job.start()
                job.complete()


class TestSourcePackageTranslationSharingDetailsView(TestCaseWithFactory,
                                                     ConfigureScenarioMixin):
    """Tests for SourcePackageTranslationSharingStatus."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSourcePackageTranslationSharingDetailsView, self).setUp()
        distroseries = self.factory.makeUbuntuDistroSeries()
        self.sourcepackage = self.factory.makeSourcePackage(
            distroseries=distroseries)
        self.ubuntu_only_template = self.factory.makePOTemplate(
            sourcepackage=self.sourcepackage, name='ubuntu-only')
        self.shared_template_ubuntu_side = self.factory.makePOTemplate(
            sourcepackage=self.sourcepackage, name='shared-template')
        self.privileged_user = self.factory.makePerson(karma=200)
        product = self.factory.makeProduct(owner=self.privileged_user)
        self.productseries = self.factory.makeProductSeries(product=product)
        self.shared_template_upstream_side = self.factory.makePOTemplate(
            productseries=self.productseries, name='shared-template')
        self.upstream_only_template = self.factory.makePOTemplate(
            productseries=self.productseries, name='upstream-only')
        self.view = make_initialized_view(self.sourcepackage)

    def configureSharing(self,
            set_upstream_branch=False,
            translations_usage=ServiceUsage.UNKNOWN,
            translation_import_mode=TranslationsBranchImportMode.NO_IMPORT):
        """Configure translation sharing, at least partially.

        A packaging link is always set; the remaining configuration is
        done only if explicitly specified.
        """
        # Suppress merge job creation.
        with EventRecorder():
            self.sourcepackage.setPackaging(
                self.productseries, self.productseries.owner)
        self.configureUpstreamProject(
            self.productseries, set_upstream_branch, translations_usage,
            translation_import_mode)

    def test_is_packaging_configured__not_configured(self):
        # If a sourcepackage is not linked to a product series,
        # SourcePackageTranslationSharingStatus.is_packaging_configured
        # returns False.
        self.assertFalse(self.view.is_packaging_configured)

    def test_is_packaging_configured__configured(self):
        # If a sourcepackage is linked to a product series,
        # SourcePackageTranslationSharingStatus.is_packaging_configured
        # returns True.
        self.configureSharing()
        self.assertTrue(self.view.is_packaging_configured)

    def test_has_upstream_branch__no_packaging_link(self):
        # If the source package is not linked to an upstream series,
        # SourcePackageTranslationSharingStatus.has_upstream_branch
        # returns False.
        self.assertFalse(self.view.has_upstream_branch)

    def test_has_upstream_branch__no_branch_exists(self):
        # If the upstream product series does not have any source
        # code branch,
        # SourcePackageTranslationSharingStatus.has_upstream_branch
        # returns False.
        self.configureSharing()
        self.assertFalse(self.view.has_upstream_branch)

    def test_has_upstream_branch__branch_exists(self):
        # If the upstream product series has at least one  source
        # code branch,
        # SourcePackageTranslationSharingStatus.has_upstream_branch
        # returns True.
        self.configureSharing(set_upstream_branch=True)
        self.assertTrue(self.view.has_upstream_branch)

    def test_branch_link_text(self):
        self.configureSharing(set_upstream_branch=True)
        expected_text = '>lp:%s</a>' % self.view.upstream_branch.unique_name
        self.assertIn(expected_text, self.view.branch_link.escapedtext)

    def test_is_upstream_translations_enabled__no_packaging_link(self):
        # If the source package is not linked to an upstream series,
        # is_upstream_translations_enabled returns False.
        self.assertFalse(self.view.is_upstream_translations_enabled)

    def test_is_upstream_translations_enabled__when_unknown(self):
        # If it is unknown what the upstream project uses for
        # translations, is_upstream_translations_enabled returns False.
        self.configureSharing(translations_usage=ServiceUsage.UNKNOWN)
        self.assertFalse(self.view.is_upstream_translations_enabled)

    def test_is_upstream_translations_enabled__when_launchpad(self):
        # If the upstream product series uses Launchpad for
        # translations, is_upstream_translations_enabled returns True.
        self.configureSharing(translations_usage=ServiceUsage.LAUNCHPAD)
        self.assertTrue(self.view.is_upstream_translations_enabled)

    def test_is_upstream_translations_enabled__when_external(self):
        # If the upstream product series uses an external tool for
        # translations, is_upstream_translations_enabled returns True.
        self.configureSharing(translations_usage=ServiceUsage.EXTERNAL)
        self.assertTrue(self.view.is_upstream_translations_enabled)

    def test_is_upstream_translations_enabled__when_not_applicable(self):
        # If the upstream product series does not do translations at all,
        # is_upstream_translations_enabled returns False.
        self.configureSharing(translations_usage=ServiceUsage.NOT_APPLICABLE)
        self.assertFalse(self.view.is_upstream_translations_enabled)

    def test_is_upstream_synchronization_enabled__no_packaging_link(self):
        # If the source package is not linked to an upstream series,
        # is_upstream_synchronization_enabled returns False.
        self.assertFalse(self.view.is_upstream_synchronization_enabled)

    def test_is_upstream_synchronization_enabled__no_import(self):
        # If no synchronization is enabled on the upstream series,
        # is_upstream_synchronization_enabled returns False.
        self.configureSharing(
            translation_import_mode=TranslationsBranchImportMode.NO_IMPORT)
        self.assertFalse(self.view.is_upstream_synchronization_enabled)

    def test_is_upstream_synchronization_enabled__import_templates(self):
        # If only template synchronization is enabled on the upstream series,
        # is_upstream_synchronization_enabled returns False.
        self.configureSharing(
            translation_import_mode=(
                TranslationsBranchImportMode.IMPORT_TEMPLATES))
        self.assertFalse(self.view.is_upstream_synchronization_enabled)

    def test_is_upstream_synchronization_enabled__import_translations(self):
        # If full translation synchronization is enabled on the upstream
        # series, is_upstream_synchronization_enabled returns False.
        self.configureSharing(
            translation_import_mode=(
                TranslationsBranchImportMode.IMPORT_TRANSLATIONS))
        self.assertTrue(self.view.is_upstream_synchronization_enabled)

    def test_is_configuration_complete__nothing_configured(self):
        # If none of the conditions for translation sharing are
        # fulfilled (the default test setup), is_configuration_complete
        # is False.
        self.assertFalse(self.view.is_configuration_complete)

    def test_is_configuration_complete__only_packaging_set(self):
        # If the packaging link is set but the other conditions for
        # translation sharing are not fulfilled, is_configuration_complete
        # is False.
        self.configureSharing()
        self.assertFalse(self.view.is_configuration_complete)

    def test_is_configuration_complete__packaging_upstream_branch_set(self):
        # If the packaging link is set and if an upstream branch is
        # configuerd but if the other conditions are not fulfilled,
        # is_configuration_complete is False.
        self.configureSharing(set_upstream_branch=True)
        self.assertFalse(self.view.is_configuration_complete)

    def test_is_configuration_complete__packaging_transl_enabled(self):
        # If the packaging link is set and if an upstream series
        # uses Launchpad translations but if the other conditions
        # are not fulfilled, is_configuration_complete is False.
        self.configureSharing(translations_usage=ServiceUsage.LAUNCHPAD)
        self.assertFalse(self.view.is_configuration_complete)

    def test_is_configuration_complete__no_auto_sync(self):
        # If
        #   - a packaging link is set
        #   - a branch is set for the upstream series
        #   - the upstream series uses Launchpad translations
        # but if the upstream series does not synchronize translations
        # then is_configuration_complete is False.
        self.configureSharing(
            set_upstream_branch=True,
            translations_usage=ServiceUsage.LAUNCHPAD)
        self.assertFalse(self.view.is_configuration_complete)

    def test_is_configuration_complete__all_conditions_fulfilled(self):
        # If
        #   - a packaging link is set
        #   - a branch is set for the upstream series
        #   - the upstream series uses Launchpad translations
        #   - the upstream series synchronizes translations
        # then is_configuration_complete is True.
        self.configureSharing(
            set_upstream_branch=True,
            translations_usage=ServiceUsage.LAUNCHPAD,
            translation_import_mode=(
                TranslationsBranchImportMode.IMPORT_TRANSLATIONS))
        self.assertTrue(self.view.is_configuration_complete)

    def test_template_info__no_sharing(self):
        # If translation sharing is not configured,
        # SourcePackageTranslationSharingDetailsView.info returns
        # only data about templates in Ubuntu.
        expected = [
            {
                'name': 'shared-template',
                'status': 'only in Ubuntu',
                'package_template': self.shared_template_ubuntu_side,
                'upstream_template': None,
                },
            {
                'name': 'ubuntu-only',
                'status': 'only in Ubuntu',
                'package_template': self.ubuntu_only_template,
                'upstream_template': None,
                },
            ]
        self.assertEqual(expected, self.view.template_info())

    def test_template_info___sharing(self):
        # If translation sharing is configured,
        # SourcePackageTranslationSharingDetailsView.info returns
        # only data about templates in Ubuntu and about upstream
        # templates.
        self.configureSharing(
            set_upstream_branch=True,
            translations_usage=ServiceUsage.LAUNCHPAD,
            translation_import_mode=(
                TranslationsBranchImportMode.IMPORT_TRANSLATIONS))
        expected = [
            {
                'name': 'shared-template',
                'status': 'shared',
                'package_template': self.shared_template_ubuntu_side,
                'upstream_template': self.shared_template_upstream_side,
                },
            {
                'name': 'ubuntu-only',
                'status': 'only in Ubuntu',
                'package_template': self.ubuntu_only_template,
                'upstream_template': None,
                },
            {
                'name': 'upstream-only',
                'status': 'only in upstream',
                'package_template': None,
                'upstream_template': self.upstream_only_template,
                },
            ]
        self.assertEqual(expected, self.view.template_info())

    def getCacheObjects(self):
        view = make_initialized_view(self.sourcepackage)
        view.initialize()
        cache = IJSONRequestCache(view.request)
        return cache.objects

    def test_cache_contents_no_productseries(self):
        objects = self.getCacheObjects()
        self.assertIs(None, objects['productseries'])
        self.assertIn('user_can_change_product_series', objects)
        self.assertIn('user_can_change_branch', objects)
        self.assertIn('user_can_change_translation_usage', objects)
        self.assertIn('user_can_change_translations_autoimport_mode', objects)

    def test_cache_contents_no_branch(self):
        self.configureSharing()
        objects = self.getCacheObjects()
        self.assertEqual(self.productseries, objects['productseries'])
        self.assertEqual(self.productseries.product, objects['product'])
        self.assertIs(None, objects['upstream_branch'])

    def test_cache_contents_branch(self):
        self.configureSharing(set_upstream_branch=True)
        objects = self.getCacheObjects()
        self.assertEqual(
            self.productseries.branch, objects['upstream_branch'])

    def _getExpectedTranslationSettingsLink(self, id, series, visible):
        if series is None:
            url = '#'
        else:
            url = '%s/+configure-translations' % canonical_url(series.product)
        return (
            '<a id="upstream-translations-%(id)s" class="sprite '
            'edit action-icon%(seen)s" href="%(url)s">'
            'Configure Upstream Translations</a>') % {
            'id': id,
            'url': url,
            'seen': '' if visible else ' hidden',
            }

    def test_configure_translations_link__no_packaging_link(self):
        # If no packaging link exists,
        # configure_translations_link_unconfigured and
        # configure_translations_link_configured return hidden dummy
        # links.
        expected = self._getExpectedTranslationSettingsLink(
            id='incomplete', series=None, visible=False)
        self.assertEqual(
            expected,
            self.view.configure_translations_link_unconfigured.escapedtext)
        expected = self._getExpectedTranslationSettingsLink(
            id='complete', series=None, visible=False)
        self.assertEqual(
            expected,
            self.view.configure_translations_link_configured.escapedtext)

    def test_configure_translations_link__packaging_link__anon_user(self):
        # If a packaging link exists,
        # configure_translations_link_unconfigured and
        # configure_translations_link_configured return hidden links
        # pointing to the configuration page for anonymous users.
        self.configureSharing()
        expected = self._getExpectedTranslationSettingsLink(
            id='incomplete', series=self.productseries, visible=False)
        self.assertEqual(
            expected,
            self.view.configure_translations_link_unconfigured.escapedtext)
        expected = self._getExpectedTranslationSettingsLink(
            id='complete', series=self.productseries, visible=False)
        self.assertEqual(
            expected,
            self.view.configure_translations_link_configured.escapedtext)

    def test_configure_translations_link__packaging_link__unprivileged_user(
        self):
        # If a packaging link exists,
        # configure_translations_link_unconfigured and
        # configure_translations_link_configured return hidden links
        # pointing to the configuration page for users which cannot configure
        # the product series.
        self.configureSharing()
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            expected = self._getExpectedTranslationSettingsLink(
                id='incomplete', series=self.productseries, visible=False)
            self.assertEqual(
                expected,
                view.configure_translations_link_unconfigured.escapedtext)
            expected = self._getExpectedTranslationSettingsLink(
                id='complete', series=self.productseries, visible=False)
            self.assertEqual(
                expected,
                view.configure_translations_link_configured.escapedtext)

    def test_configure_translations_link__packaging_link__privileged_user(
        self):
        # If a packaging link exists,
        # configure_translations_link_unconfigured and
        # configure_translations_link_configured return visible links
        # pointing to the configuration page for users which can configure
        # the product series.
        self.configureSharing()
        with person_logged_in(self.productseries.owner):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            expected = self._getExpectedTranslationSettingsLink(
                id='incomplete', series=self.productseries, visible=True)
            self.assertEqual(
                expected,
                view.configure_translations_link_unconfigured.escapedtext)
            expected = self._getExpectedTranslationSettingsLink(
                id='complete', series=self.productseries, visible=True)
            self.assertEqual(
                expected,
                view.configure_translations_link_configured.escapedtext)

    def _getExpectedTranslationSyncLink(self, id, series, visible):
        if series is None:
            url = '#'
        else:
            url = '%s/+translations-settings' % canonical_url(series)
        return (
        '<a id="translation-synchronisation-%(id)s" class="sprite '
        'edit action-icon%(seen)s" href="%(url)s">'
        'Configure Translation Synchronisation</a>') % {
            'id': id,
            'url': url,
            'seen': '' if visible else ' hidden',
            }

    def test_upstream_sync_link__no_packaging_link(self):
        # If no packaging link exists, translation_sync_link_unconfigured
        # and translation_sync_link_configured return hidden dummy links.
        expected = self._getExpectedTranslationSyncLink(
            id='incomplete', series=None, visible=False)
        self.assertEqual(
            expected,
            self.view.translation_sync_link_unconfigured.escapedtext)
        expected = self._getExpectedTranslationSyncLink(
            id='complete', series=None, visible=False)
        self.assertEqual(
            expected,
            self.view.translation_sync_link_configured.escapedtext)

    def test_upstream_sync_link__packaging_link__anon_user(self):
        # If a packaging link exists, translation_sync_link_unconfigured
        # and translation_sync_link_configured return hidden links
        # for anonymous users.
        self.configureSharing()
        expected = self._getExpectedTranslationSyncLink(
            id='incomplete', series=self.productseries, visible=False)
        self.assertEqual(
            expected,
            self.view.translation_sync_link_unconfigured.escapedtext)
        expected = self._getExpectedTranslationSyncLink(
            id='complete', series=self.productseries, visible=False)
        self.assertEqual(
            expected,
            self.view.translation_sync_link_configured.escapedtext)

    def test_upstream_sync_link__packaging_link__unprivileged_user(self):
        # If a packaging link exists, translation_sync_link_unconfigured
        # and translation_sync_link_configured return hidden links
        # for users which don't have the permission to change the
        # translation sync setting.
        self.configureSharing()
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            expected = self._getExpectedTranslationSyncLink(
                id='incomplete', series=self.productseries, visible=False)
            self.assertEqual(
                expected,
                view.translation_sync_link_unconfigured.escapedtext)
            expected = self._getExpectedTranslationSyncLink(
                id='complete', series=self.productseries, visible=False)
            self.assertEqual(
                expected,
                view.translation_sync_link_configured.escapedtext)

    def test_upstream_sync_link__packaging_link__privileged_user(self):
        # If a packaging link exists, translation_sync_link_unconfigured
        # and translation_sync_link_configured return visible links
        # for users which have the permission to change the
        # translation sync setting.
        self.configureSharing()
        with person_logged_in(self.productseries.owner):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            expected = self._getExpectedTranslationSyncLink(
                id='incomplete', series=self.productseries, visible=True)
            self.assertEqual(
                expected,
                view.translation_sync_link_unconfigured.escapedtext)
            expected = self._getExpectedTranslationSyncLink(
                id='complete', series=self.productseries, visible=True)
            self.assertEqual(
                expected,
                view.translation_sync_link_configured.escapedtext)

    def _getExpectedPackagingLink(self, id, url, icon, text, visible):
        url = '%s/%s' % (canonical_url(self.sourcepackage), url)
        return (
            '<a id="%(id)s" class="sprite %(icon)s action-icon%(seen)s"'
            ' href="%(url)s">%(text)s</a>') % {
            'id': id,
            'url': url,
            'icon': icon,
            'seen': '' if visible else ' hidden',
            'text': text,
            }

    def test_set_packaging_link__anonymous(self):
        # The "set packaging" link is hidden for anonymous users.
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='set-packaging', url='+edit-packaging', icon='add',
            text='Set upstream link', visible=False)
        self.assertEqual(expected, self.view.set_packaging_link.escapedtext)

    def test_set_packaging_link__no_packaging_any_user(self):
        # If packaging is not configured, any user sees the "set packaging"
        # link.
        expected = self._getExpectedPackagingLink(
            id='set-packaging', url='+edit-packaging', icon='add',
            text='Set upstream link', visible=True)
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.set_packaging_link.escapedtext)

    def test_set_packaging_link__with_packaging_probationary_user(self):
        # If packaging is configured, probationary users do no see
        # the "set packaging" link.
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='set-packaging', url='+edit-packaging', icon='add',
            text='Set upstream link', visible=False)
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.set_packaging_link.escapedtext)

    def test_set_packaging_link__with_packaging_privileged_user(self):
        # If packaging is configured, privileged users see the
        # "set packaging" link. (See Packaging.userCanDelete() for more
        # details about which people are "privileged".)
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='set-packaging', url='+edit-packaging', icon='add',
            text='Set upstream link', visible=True)
        with person_logged_in(self.privileged_user):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.set_packaging_link.escapedtext)

    def test_change_packaging_link__anonymous(self):
        # The "change packaging" link is hidden for anonymous users.
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='change-packaging', url='+edit-packaging', icon='edit',
            text='Change upstream link', visible=False)
        self.assertEqual(
            expected, self.view.change_packaging_link.escapedtext)

    def test_change_packaging_link__no_packaging_any_user(self):
        # If packaging is not configured, any user sees the "change packaging"
        # link.
        expected = self._getExpectedPackagingLink(
            id='change-packaging', url='+edit-packaging', icon='edit',
            text='Change upstream link', visible=True)
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.change_packaging_link.escapedtext)

    def test_change_packaging_link__with_packaging_probationary_user(self):
        # If packaging is configured, probationary users do no see
        # the "change packaging" link.
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='change-packaging', url='+edit-packaging', icon='edit',
            text='Change upstream link', visible=False)
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.change_packaging_link.escapedtext)

    def test_change_packaging_link__with_packaging_privileged_user(self):
        # If packaging is configured, privileged users see the
        # "change packaging" link. (See Packaging.userCanDelete() for more
        # details about which people are "privileged".)
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='change-packaging', url='+edit-packaging', icon='edit',
            text='Change upstream link', visible=True)
        with person_logged_in(self.privileged_user):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.change_packaging_link.escapedtext)

    def test_remove_packaging_link__anonymous(self):
        # The "remove packaging" link is hidden for anonymous users.
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='remove-packaging', url='+remove-packaging', icon='remove',
            text='Remove upstream link', visible=False)
        self.assertEqual(
            expected, self.view.remove_packaging_link.escapedtext)

    def test_remove_packaging_link__no_packaging_any_user(self):
        # If packaging is not configured, any user sees the "remove packaging"
        # link.
        expected = self._getExpectedPackagingLink(
            id='remove-packaging', url='+remove-packaging', icon='remove',
            text='Remove upstream link', visible=True)
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.remove_packaging_link.escapedtext)

    def test_remove_packaging_link__with_packaging_probationary_user(self):
        # If packaging is configured, probationary users do no see
        # the "remove packaging" link.
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='remove-packaging', url='+remove-packaging', icon='remove',
            text='Remove upstream link', visible=False)
        with person_logged_in(self.factory.makePerson()):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.remove_packaging_link.escapedtext)

    def test_remove_packaging_link__with_packaging_privileged_user(self):
        # If packaging is configured, privileged users see the
        # "remove packaging" link. (See Packaging.userCanDelete() for more
        # details about which people are "privileged".)
        self.configureSharing()
        expected = self._getExpectedPackagingLink(
            id='remove-packaging', url='+remove-packaging', icon='remove',
            text='Remove upstream link', visible=True)
        with person_logged_in(self.privileged_user):
            view = SourcePackageTranslationSharingDetailsView(
                self.sourcepackage, LaunchpadTestRequest())
            view.initialize()
            self.assertEqual(
                expected, self.view.remove_packaging_link.escapedtext)


class TestSourcePackageSharingDetailsPage(BrowserTestCase,
                                          ConfigureScenarioMixin):
    """Test for the sharing details page of a source package."""

    layer = DatabaseFunctionalLayer

    def _makeSourcePackage(self):
        """Make a source package in Ubuntu."""
        distroseries = self.factory.makeUbuntuDistroSeries()
        return self.factory.makeSourcePackage(distroseries=distroseries)

    def _getSharingDetailsViewBrowser(self, sourcepackage, user=None):
        if user is None:
            no_login = True
        else:
            no_login = False
        return self.getViewBrowser(
            sourcepackage, no_login=no_login, rootsite="translations",
            view_name="+sharing-details", user=user)

    def asserthidden(self, browser, html_id):
        hidden_matcher = Tag(html_id, 'li', attrs={
            'id': html_id,
            'class': lambda v: v and 'hidden' in v.split(' ')})
        self.assertThat(browser.contents, HTMLContains(hidden_matcher))

    def assertSeen(self, browser, html_id, dimmed=False):
        seen_matcher = Tag(html_id, 'li', attrs={
            'id': html_id,
            'class': lambda v: v and 'hidden' not in v.split(' ')})
        self.assertThat(browser.contents, HTMLContains(seen_matcher))
        if dimmed:
            dimmed_matcher = Tag(html_id, 'li', attrs={
            'id': html_id,
            'class': lambda v: v and 'lowlight' in v.split(' ')})
        else:
            dimmed_matcher = Tag(html_id, 'li', attrs={
            'id': html_id,
            'class': lambda v: v and 'lowlight' not in v.split(' ')})
        self.assertThat(browser.contents, HTMLContains(dimmed_matcher))

    def assertStatusDisplayShowsIncomplete(self, browser):
        seen_matcher = Tag(
            'configuration-incomplete', 'span',
            attrs={
                'id': 'configuration-incomplete',
                'class': '',
                })
        self.assertThat(browser.contents, HTMLContains(seen_matcher))
        hidden_matcher = Tag(
            'configuration-complete', 'span',
            attrs={
                'id': 'configuration-complete',
                'class': 'hidden',
                })
        self.assertThat(browser.contents, HTMLContains(hidden_matcher))

    def assertStatusDisplayShowsCompleted(self, browser):
        seen_matcher = Tag(
            'configuration-complete', 'span',
            attrs={
                'id': 'configuration-complete',
                'class': '',
                })
        self.assertThat(browser.contents, HTMLContains(seen_matcher))
        hidden_matcher = Tag(
            'configuration-incomplete', 'span',
            attrs={
                'id': 'configuration-incomplete',
                'class': 'hidden',
                })
        self.assertThat(browser.contents, HTMLContains(hidden_matcher))

    def assertElementText(self, browser, id, expected):
        node = find_tag_by_id(browser.contents, id)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            expected, extract_text(node))

    def assertContentComplete(self, browser):
        # The HTML data contains always all text variants.
        checklist = find_tag_by_id(browser.contents, 'sharing-checklist')
        self.assertIsNot(None, checklist)
        self.assertTextMatchesExpressionIgnoreWhitespace("""
            Translation sharing configuration is incomplete.
            Translation sharing with upstream is active.
            No upstream project series has been linked.
            Set upstream link
            Linked upstream series is .*
            Change upstream link
            Remove upstream link
            No source branch exists for the upstream series.
            Link to branch
            Upstream source branch is.*
            Change branch
            Translations are not enabled on the upstream project.
            Configure Upstream Translations
            Translations are enabled on the upstream project.
            Configure Upstream Translations
            Automatic synchronization of translations is not enabled.
            Configure Translation Synchronisation
            Automatic synchronization of translations is enabled.
            Configure Translation Synchronisation""",
            extract_text(checklist))
        self.assertElementText(
            browser, 'packaging-incomplete',
            'No upstream project series has been linked.')
        self.assertElementText(
            browser, 'packaging-complete', 'Linked upstream series is .*')
        self.assertElementText(
            browser, 'packaging-complete', 'Linked upstream series is .*')
        self.assertElementText(
            browser, 'branch-incomplete',
            'No source branch exists for the upstream series.')
        self.assertElementText(
            browser, 'branch-complete', 'Upstream source branch is .*')
        self.assertElementText(
            browser, 'translation-incomplete',
            'Translations are not enabled on the upstream project.')
        self.assertElementText(
            browser, 'translation-complete',
            'Translations are enabled on the upstream project.')

    def test_checklist_unconfigured(self):
        # Without a packaging link, sharing is completely unconfigured
        sourcepackage = self._makeSourcePackage()
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        self.assertContentComplete(browser)
        self.assertStatusDisplayShowsIncomplete(browser)
        self.asserthidden(browser, 'packaging-complete')
        self.assertSeen(browser, 'branch-incomplete', dimmed=True)
        self.asserthidden(browser, 'branch-complete')
        self.assertSeen(browser, 'translation-incomplete', dimmed=True)
        self.asserthidden(browser, 'translation-complete')
        self.assertSeen(browser, 'upstream-sync-incomplete', dimmed=True)
        self.asserthidden(browser, 'upstream-sync-complete')

    def test_checklist_packaging_configured(self):
        # Linking a source package takes care of one item.
        # The other configuration elements are not dimmed.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        browser = self._getSharingDetailsViewBrowser(packaging.sourcepackage)
        self.assertContentComplete(browser)
        self.assertStatusDisplayShowsIncomplete(browser)
        self.asserthidden(browser, 'packaging-incomplete')
        self.assertSeen(browser, 'packaging-complete')
        self.assertSeen(browser, 'branch-incomplete')
        self.asserthidden(browser, 'branch-complete')
        self.assertSeen(browser, 'translation-incomplete')
        self.asserthidden(browser, 'translation-complete')
        self.assertSeen(browser, 'upstream-sync-incomplete')
        self.asserthidden(browser, 'upstream-sync-complete')

    def test_checklist_packaging_and_branch_configured(self):
        # Linking a source package and and setting an upstream branch
        # changes the text displayed for the branch configuration.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        self.configureUpstreamProject(
            productseries=packaging.productseries, set_upstream_branch=True)
        browser = self._getSharingDetailsViewBrowser(packaging.sourcepackage)
        self.assertContentComplete(browser)
        self.assertStatusDisplayShowsIncomplete(browser)
        self.asserthidden(browser, 'packaging-incomplete')
        self.assertSeen(browser, 'packaging-complete')
        self.asserthidden(browser, 'branch-incomplete')
        self.assertSeen(browser, 'branch-complete')
        self.assertSeen(browser, 'translation-incomplete')
        self.asserthidden(browser, 'translation-complete')
        self.assertSeen(browser, 'upstream-sync-incomplete')
        self.asserthidden(browser, 'upstream-sync-complete')

    def test_checklist_packaging_and_translations_enabled(self):
        # Linking a source package and and setting an upstream branch
        # changes the text displayed for the translation setting.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        self.configureUpstreamProject(
            productseries=packaging.productseries,
            translations_usage=ServiceUsage.LAUNCHPAD)
        browser = self._getSharingDetailsViewBrowser(packaging.sourcepackage)
        self.assertContentComplete(browser)
        self.assertStatusDisplayShowsIncomplete(browser)
        self.asserthidden(browser, 'packaging-incomplete')
        self.assertSeen(browser, 'packaging-complete')
        self.assertSeen(browser, 'branch-incomplete')
        self.asserthidden(browser, 'branch-complete')
        self.asserthidden(browser, 'translation-incomplete')
        self.assertSeen(browser, 'translation-complete')
        self.assertSeen(browser, 'upstream-sync-incomplete')
        self.asserthidden(browser, 'upstream-sync-complete')

    def test_checklist_packaging_and_upstream_sync_enabled(self):
        # Linking a source package and enabling upstream translation
        # synchronisation changes the text displayed for the
        # translation sync setting.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        self.configureUpstreamProject(
            productseries=packaging.productseries,
            translation_import_mode=(
                TranslationsBranchImportMode.IMPORT_TRANSLATIONS))
        browser = self._getSharingDetailsViewBrowser(packaging.sourcepackage)
        self.assertContentComplete(browser)
        self.assertStatusDisplayShowsIncomplete(browser)
        self.asserthidden(browser, 'packaging-incomplete')
        self.assertSeen(browser, 'packaging-complete')
        self.assertSeen(browser, 'branch-incomplete')
        self.asserthidden(browser, 'branch-complete')
        self.assertSeen(browser, 'translation-incomplete')
        self.asserthidden(browser, 'translation-complete')
        self.asserthidden(browser, 'upstream-sync-incomplete')
        self.assertSeen(browser, 'upstream-sync-complete')

    def test_checklist_fully_configured(self):
        # A fully configured sharing setup.
        sourcepackage = self.makeFullyConfiguredSharing()[0]
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        self.assertContentComplete(browser)
        self.assertStatusDisplayShowsCompleted(browser)
        self.asserthidden(browser, 'packaging-incomplete')
        self.assertSeen(browser, 'packaging-complete')
        self.asserthidden(browser, 'branch-incomplete')
        self.assertSeen(browser, 'branch-complete')
        self.asserthidden(browser, 'translation-incomplete')
        self.assertSeen(browser, 'translation-complete')
        self.asserthidden(browser, 'upstream-sync-incomplete')
        self.assertSeen(browser, 'upstream-sync-complete')

    def test_cache_javascript(self):
        # Cache object entries propagate into the javascript.
        sourcepackage = self.makeFullyConfiguredSharing()[0]
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        self.assertIn(
            'productseries', extract_lp_cache(browser.contents))

    def test_potlist_only_ubuntu(self):
        # Without a packaging link, only Ubuntu templates are listed.
        sourcepackage = self._makeSourcePackage()
        self.factory.makePOTemplate(
            name='foo-template', sourcepackage=sourcepackage)
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        tbody = find_tag_by_id(
            browser.contents, 'template-table').find('tbody')
        self.assertIsNot(None, tbody)
        self.assertEqual(
            "foo-template\nonly in Ubuntu\n0\na moment ago",
            extract_text(tbody))

    def test_potlist_sharing(self):
        # With sharing configured, templates on both sides are listed.
        sourcepackage, productseries = self.makeFullyConfiguredSharing()
        template_name = 'foo-template'
        self.factory.makePOTemplate(
            name=template_name, sourcepackage=sourcepackage)
        self.factory.makePOTemplate(
            name=template_name, productseries=productseries)
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        tbody = find_tag_by_id(
            browser.contents, 'template-table').find('tbody')
        self.assertIsNot(None, tbody)
        self.assertEqual(
            "foo-template\nshared\n0\na moment ago\n0\na moment ago\n"
            "View upstream", extract_text(tbody))

    def test_potlist_only_upstream(self):
        # A template that is only present in upstream is called
        # "only in upstream".
        sourcepackage, productseries = self.makeFullyConfiguredSharing()
        template_name = 'foo-template'
        self.factory.makePOTemplate(
            name=template_name, productseries=productseries)
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        tbody = find_tag_by_id(
            browser.contents, 'template-table').find('tbody')
        self.assertIsNot(None, tbody)
        self.assertEqual(
            "foo-template\nonly in upstream\n0\na moment ago\nView upstream",
            extract_text(tbody))

    def test_potlist_linking(self):
        # When a merge job is running, the state is "linking".
        sourcepackage, productseries = self.makeFullyConfiguredSharing(
            suppress_merge_job=False)
        template_name = 'foo-template'
        self.factory.makePOTemplate(
            name=template_name, sourcepackage=sourcepackage)
        self.factory.makePOTemplate(
            name=template_name, productseries=productseries)
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        tbody = find_tag_by_id(
            browser.contents, 'template-table').find('tbody')
        self.assertIsNot(None, tbody)
        self.assertTextMatchesExpressionIgnoreWhitespace("""
            foo-template  linking""",
            extract_text(tbody))

    def assertBranchLinks(self, contents, real_links, enabled):
        if real_links:
            match = (
                r'^http://translations.launchpad.dev/.*/trunk/\+setbranch$')

            def link_matcher(url):
                if url is None:
                    return False
                return re.search(match, url)
        else:
            link_matcher = '#'
        if enabled:
            css_class = 'sprite add action-icon'
        else:
            css_class = 'sprite add action-icon hidden'
        matcher = Tag('add-branch', 'a', attrs={
            'id': 'add-branch',
            'href': link_matcher,
            'class': css_class})
        self.assertThat(contents, HTMLContains(matcher))
        if enabled:
            css_class = 'sprite edit action-icon'
        else:
            css_class = 'sprite edit action-icon hidden'
        matcher = Tag('change-branch', 'a', attrs={
            'id': 'change-branch',
            'href': link_matcher,
            'class': css_class})
        self.assertThat(contents, HTMLContains(matcher))

    def test_edit_branch_links__no_packaging_link(self):
        # If no packaging link exists, new_branch_link and edit_branch_link
        # return hidden dummy links.
        sourcepackage = self._makeSourcePackage()
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        self.assertBranchLinks(
            browser.contents, real_links=False, enabled=False)

    def test_edit_branch_links__with_packaging_link__anon_user(self):
        # If a packaging link exists, new_branch_link and edit_branch_link
        # return hidden links which point to the product series
        # branch configuration page for anonymous users.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        self.configureUpstreamProject(
            productseries=packaging.productseries)
        browser = self._getSharingDetailsViewBrowser(packaging.sourcepackage)
        self.assertBranchLinks(
            browser.contents, real_links=True, enabled=False)

    def test_edit_branch_links__with_packaging_link__unprivileged_user(self):
        # If a packaging link exists, new_branch_link and edit_branch_link
        # return hidden links which point to the product series
        # branch configuration page for users which cannot change the
        # branch of the product series.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        self.configureUpstreamProject(
            productseries=packaging.productseries)
        browser = self._getSharingDetailsViewBrowser(
            packaging.sourcepackage, user=self.factory.makePerson())
        self.assertBranchLinks(
            browser.contents, real_links=True, enabled=False)

    def test_edit_branch_links__with_packaging_link__privileged_user(self):
        # If a packaging link exists, new_branch_link and edit_branch_link
        # return links which point to the product series
        # branch configuration page for users which can change the
        # branch of the product series.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        self.configureUpstreamProject(
            productseries=packaging.productseries)
        browser = self._getSharingDetailsViewBrowser(
            packaging.sourcepackage, user=packaging.productseries.owner)
        self.assertBranchLinks(
            browser.contents, real_links=True, enabled=True)

    def test_configure_translations(self):
        # The link to the translation configuration page of the
        # upstream product is included twice in the page.
        sourcepackage = self._makeSourcePackage()
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        matcher = Tag(
            'upstream-translations-incomplete', 'a',
            attrs={
                'id': 'upstream-translations-incomplete',
                'href': '#',
                'class': 'sprite edit action-icon hidden',
                },
        )
        self.assertThat(browser.contents, HTMLContains(matcher))
        matcher = Tag(
            'upstream-translations-complete', 'a',
            attrs={
                'id': 'upstream-translations-complete',
                'href': '#',
                'class': 'sprite edit action-icon hidden',
                },
        )
        self.assertThat(browser.contents, HTMLContains(matcher))

    def test_upstream_sync_link(self):
        # The link to the translation synchronisation page of the
        # upstream product series is included twice in the page.
        sourcepackage = self._makeSourcePackage()
        browser = self._getSharingDetailsViewBrowser(sourcepackage)
        matcher = Tag(
            'translation-synchronisation-incomplete', 'a',
            attrs={
                'id': 'translation-synchronisation-incomplete',
                'href': '#',
                'class': 'sprite edit action-icon hidden',
                },
        )
        self.assertThat(browser.contents, HTMLContains(matcher))
        matcher = Tag(
            'translation-synchronisation-complete', 'a',
            attrs={
                'id': 'translation-synchronisation-complete',
                'href': '#',
                'class': 'sprite edit action-icon hidden',
                },
        )
        self.assertThat(browser.contents, HTMLContains(matcher))


class TestTranslationSharingDetailsViewNotifications(TestCaseWithFactory,
                                                     ConfigureScenarioMixin):
    """Tests for Notifications in SourcePackageTranslationSharingView."""

    layer = DatabaseFunctionalLayer

    def _getNotifications(self, view):
        notifications = view.request.response.notifications
        return [extract_text(notification.message)
                for notification in notifications]

    no_templates_message = (
        "No upstream templates have been found yet. Please follow "
        "the import process by going to the Translation Import Queue "
        "of the upstream project series.")

    def test_message_no_templates(self):
        # When sharing is fully configured but no upstream templates are
        # found, a message is displayed.
        sourcepackage = self.makeFullyConfiguredSharing()[0]
        view = make_initialized_view(sourcepackage)
        self.assertIn(
            self.no_templates_message, self._getNotifications(view))

    def test_no_message_with_templates(self):
        # When sharing is fully configured and templates are found, no
        # message should be displayed.
        sourcepackage, productseries = self.makeFullyConfiguredSharing()
        self.factory.makePOTemplate(productseries=productseries)
        view = make_initialized_view(sourcepackage)
        self.assertNotIn(
            self.no_templates_message, self._getNotifications(view))

    def test_no_message_with_incomplate_sharing(self):
        # When sharing is not fully configured and templates are found, no
        # message should be displayed.
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        productseries = packaging.productseries
        sourcepackage = packaging.sourcepackage
        self.factory.makePOTemplate(productseries=productseries)
        view = make_initialized_view(sourcepackage)
        self.assertNotIn(
            self.no_templates_message, self._getNotifications(view))

    job_running_message = (
        "Translations are currently being linked by a background "
        "job. When that job has finished, translations will be "
        "shared with the upstream project.")

    def test_message_job_running(self):
        # When a merge job is running, a message is displayed.
        sourcepackage = self.makeFullyConfiguredSharing(
            suppress_merge_job=False)[0]
        view = make_initialized_view(sourcepackage)
        self.assertIn(
            self.job_running_message, self._getNotifications(view))

    def test_no_message_job_not_running(self):
        # Without a merge job running, no such message is displayed.
        sourcepackage = self.makeFullyConfiguredSharing(
            suppress_merge_job=False)[0]
        self.endMergeJob(sourcepackage)
        view = make_initialized_view(sourcepackage)
        self.assertNotIn(
            self.job_running_message, self._getNotifications(view))
