# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translations browser views for products."""

__metaclass__ = type

__all__ = [
    'ProductSettingsView',
    'ProductTranslationsMenu',
    'ProductView',
    ]

from lp.app.enums import service_uses_launchpad
from lp.registry.browser.product import ProductConfigureBase
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.series import SeriesStatus
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.menu import NavigationMenu
from lp.translations.browser.translations import TranslationsMixin


class ProductTranslationsMenu(NavigationMenu):

    usedfor = IProduct
    facet = 'translations'
    links = (
        'overview',
        'settings',
        'translationdownload',
        'imports',
        )

    def imports(self):
        text = 'Import queue'
        return Link('+imports', text, site='translations')

    @enabled_with_permission('launchpad.TranslationsAdmin')
    def settings(self):
        text = 'Configure translations'
        return Link(
            '+configure-translations', text, icon='edit', site='translations')

    @enabled_with_permission('launchpad.AnyPerson')
    def translationdownload(self):
        text = 'Download'
        preferred_series = self.context.primary_translatable
        enabled = (service_uses_launchpad(self.context.translations_usage)
            and preferred_series is not None)
        link = ''
        if enabled:
            link = canonical_url(
                preferred_series,
                rootsite='translations',
                view_name='+export')
            text = 'Download "%s"' % preferred_series.name

        return Link(link, text, icon='download', enabled=enabled)

    def overview(self):
        text = 'Overview'
        link = canonical_url(self.context, rootsite='translations')
        return Link(link, text, icon='translation')


class ProductSettingsView(TranslationsMixin, ProductConfigureBase):
    label = "Configure translations"
    page_title = "Configure translations"
    usage_fieldname = "translations_usage"
    field_names = [
            usage_fieldname,
            "translation_focus",
            "translationgroup",
            "translationpermission",
            ]


class ProductView(LaunchpadView):

    label = "Translation overview"

    @cachedproperty
    def uses_translations(self):
        """Whether this product has translatable templates."""
        return (service_uses_launchpad(self.context.translations_usage)
                and self.primary_translatable is not None)

    @cachedproperty
    def no_translations_available(self):
        """Has no translation templates but does support translations."""
        return (service_uses_launchpad(self.context.translations_usage)
                and self.primary_translatable is None)

    @cachedproperty
    def show_page_content(self):
        """Whether the main content of the page should be shown."""
        return (service_uses_launchpad(self.context.translations_usage) or
               self.is_translations_admin)

    def can_configure_translations(self):
        """Whether or not the user can configure translations."""
        return check_permission("launchpad.TranslationsAdmin", self.context)

    def is_translations_admin(self):
        """Whether or not the user is a translations admin."""
        return check_permission("launchpad.TranslationsAdmin", self.context)

    @cachedproperty
    def primary_translatable(self):
        """Return the context's primary translatable if it's a product series.
        """
        translatable = self.context.primary_translatable

        if not IProductSeries.providedBy(translatable):
            return None

        return translatable

    @cachedproperty
    def untranslatable_series(self):
        """Return series which are not yet set up for translations.

        The list is sorted in alphabetically order and obsolete series
        are excluded.
        """

        translatable = self.context.translatable_series
        return [series for series in self.context.series if (
            series.status != SeriesStatus.OBSOLETE and
            series not in translatable)]

    @property
    def allow_series_translation(self):
        return (check_permission("launchpad.Edit", self.context) and not
                self.context.private)
