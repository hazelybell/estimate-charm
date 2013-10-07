# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for translation pages for sourcepackages."""

__metaclass__ = type

__all__ = [
    'SourcePackageTranslationsExportView',
    'SourcePackageTranslationsView',
    ]


from lazr.restful.interfaces import IJSONRequestCache

from lp.app.enums import ServiceUsage
from lp.registry.browser.productseries import ProductSeriesOverviewMenu
from lp.registry.browser.sourcepackage import SourcePackageOverviewMenu
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.escaping import structured
from lp.services.webapp.publisher import LaunchpadView
from lp.translations.browser.poexportrequest import BaseExportView
from lp.translations.browser.product import ProductTranslationsMenu
from lp.translations.browser.productseries import (
    ProductSeriesTranslationsMenu,
    )
from lp.translations.browser.translations import TranslationsMixin
from lp.translations.browser.translationsharing import (
    TranslationSharingDetailsMixin,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )
from lp.translations.model.translationpackagingjob import TranslationMergeJob


class SourcePackageTranslationsView(LaunchpadView, TranslationsMixin,
                                    TranslationSharingDetailsMixin):

    @property
    def potemplates(self):
        return list(self.context.getCurrentTranslationTemplates())

    @property
    def label(self):
        return "Translations for %s" % self.context.displayname

    def is_sharing(self):
        return self.sharing_productseries is not None

    @property
    def sharing_productseries(self):
        return self.context.productseries

    def getTranslationSourcePackage(self):
        """See `TranslationSharingDetailsMixin`."""
        return self.context


class SourcePackageTranslationsMenu(NavigationMenu):
    usedfor = ISourcePackage
    facet = 'translations'
    links = ('overview', 'download', 'imports')

    def imports(self):
        text = 'Import queue'
        return Link('+imports', text, site='translations')

    @enabled_with_permission('launchpad.ExpensiveRequest')
    def download(self):
        text = 'Download'
        enabled = bool(self.context.getCurrentTranslationTemplates().any())
        return Link('+export', text, icon='download', enabled=enabled,
                    site='translations')

    def overview(self):
        return Link('', 'Overview', icon='info', site='translations')


class SourcePackageTranslationsExportView(BaseExportView):
    """Request tarball export of all translations for a source package."""

    page_title = "Download"

    @property
    def download_description(self):
        """Current context description used inline in paragraphs."""
        return "%s package in %s %s" % (
            self.context.sourcepackagename.name,
            self.context.distroseries.distribution.displayname,
            self.context.distroseries.displayname)

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def label(self):
        return "Download translations for %s" % self.download_description


class SourcePackageTranslationSharingDetailsView(LaunchpadView):
    """Details about translation sharing."""

    page_title = "Sharing details"

    def is_sharing(self):
        return self.context.has_sharing_translation_templates

    def can_edit_sharing_details(self):
        return check_permission('launchpad.Edit', self.context.productseries)

    def initialize(self):
        super(SourcePackageTranslationSharingDetailsView, self).initialize()
        if self.is_configuration_complete and not self.is_sharing():
            self.request.response.addInfoNotification(
                structured(
                'No upstream templates have been found yet. Please follow '
                'the import process by going to the '
                '<a href="%s">Translation Import Queue</a> of the '
                'upstream project series.',
                canonical_url(
                    self.context.productseries, rootsite='translations',
                    view_name="+imports")))
        if self.is_merge_job_running:
            self.request.response.addInfoNotification(
                'Translations are currently being linked by a background '
                'job. When that job has finished, translations will be '
                'shared with the upstream project.')
        cache = IJSONRequestCache(self.request)
        cache.objects.update({
            'productseries': self.context.productseries,
            'upstream_branch': self.upstream_branch,
            'product': self.product,
        })
        cache.objects.update(self.context.getSharingDetailPermissions())

    @property
    def branch_link(self):
        if self.has_upstream_branch:
            # Normally should use BranchFormatterAPI(branch).link(None), but
            # on this page, that information is redundant.
            title = 'lp:' + self.upstream_branch.unique_name
            url = canonical_url(self.upstream_branch)
        else:
            title = ''
            url = '#'
        return structured(
            '<a class="sprite branch link" href="%s">%s</a>', url, title)

    def makeConfigCompleteCSS(self, complete, disable, lowlight):
        if complete:
            classes = ['sprite', 'yes']
        else:
            classes = ['sprite', 'no']
        if disable:
            classes.append('hidden')
        if lowlight:
            classes.append("lowlight")
        return ' '.join(classes)

    @property
    def configuration_complete_class(self):
        if self.is_configuration_complete:
            return ""
        return "hidden"

    @property
    def configuration_incomplete_class(self):
        if not self.is_configuration_complete:
            return ""
        return "hidden"

    @property
    def packaging_incomplete_class(self):
        return self.makeConfigCompleteCSS(
            False, self.is_packaging_configured, False)

    @property
    def packaging_complete_class(self):
        return self.makeConfigCompleteCSS(
            True, not self.is_packaging_configured, False)

    @property
    def branch_incomplete_class(self):
        return self.makeConfigCompleteCSS(
            False, self.has_upstream_branch, not self.is_packaging_configured)

    @property
    def branch_complete_class(self):
        return self.makeConfigCompleteCSS(
            True, not self.has_upstream_branch,
            not self.is_packaging_configured)

    @property
    def translations_disabled_class(self):
        return self.makeConfigCompleteCSS(
            False, self.is_upstream_translations_enabled,
            not self.is_packaging_configured)

    @property
    def translations_enabled_class(self):
        return self.makeConfigCompleteCSS(
            True, not self.is_upstream_translations_enabled,
            not self.is_packaging_configured)

    @property
    def upstream_sync_disabled_class(self):
        return self.makeConfigCompleteCSS(
            False, self.is_upstream_synchronization_enabled,
            not self.is_packaging_configured)

    @property
    def upstream_sync_enabled_class(self):
        return self.makeConfigCompleteCSS(
            True, not self.is_upstream_synchronization_enabled,
            not self.is_packaging_configured)

    @property
    def is_packaging_configured(self):
        """Is a packaging link defined for this branch?"""
        return self.context.direct_packaging is not None

    @property
    def no_item_class(self):
        """CSS class for 'no' items."""
        css_class = "sprite no"
        if self.is_packaging_configured:
            return css_class
        else:
            return css_class + " lowlight"

    @property
    def upstream_branch(self):
        if not self.is_packaging_configured:
            return None
        return self.context.direct_packaging.productseries.branch

    @property
    def product(self):
        if self.context.productseries is None:
            return None
        return self.context.productseries.product

    @property
    def has_upstream_branch(self):
        """Does the upstream series have a source code branch?"""
        return self.upstream_branch is not None

    @property
    def is_upstream_translations_enabled(self):
        """Are Launchpad translations enabled for the upstream series?"""
        if not self.is_packaging_configured:
            return False
        product = self.context.direct_packaging.productseries.product
        return product.translations_usage in (
            ServiceUsage.LAUNCHPAD, ServiceUsage.EXTERNAL)

    @property
    def is_upstream_synchronization_enabled(self):
        """Is automatic synchronization of upstream translations enabled?"""
        if not self.is_packaging_configured:
            return False
        series = self.context.direct_packaging.productseries
        return (
            series.translations_autoimport_mode ==
            TranslationsBranchImportMode.IMPORT_TRANSLATIONS)

    @property
    def is_configuration_complete(self):
        """Is anything missing in the set up for translation sharing?"""
        # A check if the required packaging link exists is implicitly
        # done in the implementation of the other properties.
        return (
            self.has_upstream_branch and
            self.is_upstream_translations_enabled and
            self.is_upstream_synchronization_enabled)

    @property
    def is_merge_job_running(self):
        """Is a merge job running for this source package?"""
        if not self.is_packaging_configured:
            return False
        return TranslationMergeJob.getNextJobStatus(
            self.context.direct_packaging) is not None

    def template_info(self):
        """Details about translation templates.

        :return: A list of dictionaries containing details about each
            template. Each dictionary contains:
                'name': The name of the template
                'package_template': The package template (may be None)
                'upstream_template': The corresponding upstream template
                    (may be None)
                'status': one of the string 'linking', 'shared',
                    'only in Ubuntu', 'only in upstream'
        """
        info = {}
        templates_on_this_side = self.context.getCurrentTranslationTemplates()
        for template in templates_on_this_side:
            info[template.name] = {
                'name': template.name,
                'package_template': template,
                'upstream_template': None,
                'status': 'only in Ubuntu',
                }
        if self.is_packaging_configured:
            upstream_templates = (
                self.context.productseries.getCurrentTranslationTemplates())
            for template in upstream_templates:
                if template.name in info:
                    info[template.name]['upstream_template'] = template
                    if self.is_merge_job_running:
                        info[template.name]['status'] = 'linking'
                    else:
                        info[template.name]['status'] = 'shared'
                else:
                    info[template.name] = {
                        'name': template.name,
                        'package_template': None,
                        'upstream_template': template,
                        'status': 'only in upstream',
                        }
        info = info.values()
        return sorted(info, key=lambda template: template['name'])

    def icon_link(self, id, icon, url, text, hidden):
        """The HTML link to a configuration page."""
        if hidden:
            css_class = 'sprite %s action-icon hidden' % icon
        else:
            css_class = 'sprite %s action-icon' % icon
        return structured(
            '<a id="%s" class="%s" href="%s">%s</a>',
            id, css_class, url, text)

    @property
    def set_packaging_link(self):
        """The HTML link to define a new packaging link."""
        # We can't use the SourcePackageOverviewMenu.set_upstream
        # ink itself because it is not rendered when the current
        # user cannot change an existing packaging.
        link = SourcePackageOverviewMenu(self.context).set_upstream()
        url = '%s/%s' % (canonical_url(self.context), link.target)
        return self.icon_link(
            'set-packaging', link.icon, url, link.text, not link.enabled)

    @property
    def change_packaging_link(self):
        """The HTML link to change an existing packaging link."""
        link = SourcePackageOverviewMenu(self.context).edit_packaging()
        url = '%s/%s' % (canonical_url(self.context), link.target)
        return self.icon_link(
            'change-packaging', link.icon, url, link.text, not link.enabled)

    @property
    def remove_packaging_link(self):
        """The HTML link to delete an existing packaging link"""
        link = SourcePackageOverviewMenu(self.context).remove_packaging()
        url = '%s/%s' % (canonical_url(self.context), link.target)
        return self.icon_link(
            'remove-packaging', link.icon, url, link.text, not link.enabled)

    def edit_branch_link(self, id, icon, text):
        """The HTML link to define or edit a product series branch.

        If a product is linked to the source package and if the current
        user has the permission to define the branch, a real link is
        returned, otherwise a hidden dummy link is returned.
        """
        packaging = self.context.direct_packaging
        if packaging is not None:
            productseries = self.context.direct_packaging.productseries
            productseries_menu = ProductSeriesOverviewMenu(productseries)
            branch_link = productseries_menu.set_branch()
            url = '%s/%s' % (canonical_url(productseries), branch_link.target)
            if branch_link.enabled:
                return self.icon_link(id, icon, url, text, hidden=False)
            else:
                return self.icon_link(id, icon, url, text, hidden=True)
        return self.icon_link(id, icon, '#', text, hidden=True)

    @property
    def new_branch_link(self):
        """The HTML link to define a product series branch."""
        return self.edit_branch_link('add-branch', 'add', 'Link to branch')

    @property
    def change_branch_link(self):
        """The HTML link to change a product series branch."""
        return self.edit_branch_link('change-branch', 'edit', 'Change branch')

    def getConfigureTranslationsLink(self, id):
        """The HTML link to the product translation configuration page.
        """
        packaging = self.context.direct_packaging
        if packaging is not None:
            productseries = self.context.direct_packaging.productseries
            product = productseries.product
            product_menu = ProductTranslationsMenu(product)
            settings_link = product_menu.settings()
            url = '%s/%s' % (canonical_url(product), settings_link.target)
            hidden = not settings_link.enabled
        else:
            url = '#'
            hidden = True
        icon = 'edit'
        text = 'Configure Upstream Translations'
        return self.icon_link(id, icon, url, text, hidden)

    @property
    def configure_translations_link_unconfigured(self):
        """The HTML link to the product translation configuration page.

        Variant for the status "not configured"
        """
        id = 'upstream-translations-incomplete'
        return self.getConfigureTranslationsLink(id)

    @property
    def configure_translations_link_configured(self):
        """The HTML link to the product translation configuration page.

        Variant for the status "configured"
        """
        id = 'upstream-translations-complete'
        return self.getConfigureTranslationsLink(id)

    def getTranslationSynchronisationLink(self, id):
        """The HTML link to the series translation synchronisation page.
        """
        packaging = self.context.direct_packaging
        if packaging is not None:
            productseries = self.context.direct_packaging.productseries
            productseries_menu = ProductSeriesTranslationsMenu(productseries)
            settings_link = productseries_menu.settings()
            url = '%s/%s' % (
                canonical_url(productseries), settings_link.target)
            hidden = not settings_link.enabled
        else:
            url = '#'
            hidden = True
        icon = 'edit'
        text = 'Configure Translation Synchronisation'
        return self.icon_link(id, icon, url, text, hidden)

    @property
    def translation_sync_link_unconfigured(self):
        """The HTML link to the series translation synchronisation page.

        Variant for the status "not configured"
        """
        id = 'translation-synchronisation-incomplete'
        return self.getTranslationSynchronisationLink(id)

    @property
    def translation_sync_link_configured(self):
        """The HTML link to the series translation synchronisation page.

        Variant for the status "configured"
        """
        id = 'translation-synchronisation-complete'
        return self.getTranslationSynchronisationLink(id)
