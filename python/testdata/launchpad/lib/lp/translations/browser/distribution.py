# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translations browser views for distributions."""

__metaclass__ = type

__all__ = [
    'DistributionLanguagePackAdminView',
    'DistributionSettingsView',
    'DistributionView',
    ]

import operator

from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    )
from lp.app.enums import service_uses_launchpad
from lp.registry.browser import RegistryEditFormView
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.series import SeriesStatus
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    Link,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.menu import NavigationMenu
from lp.services.webapp.publisher import LaunchpadView
from lp.translations.browser.translations import TranslationsMixin


class DistributionTranslationsMenu(NavigationMenu):

    usedfor = IDistribution
    facet = 'translations'
    links = ['overview', 'settings', 'language_pack_admin', 'imports']

    def overview(self):
        text = 'Overview'
        link = canonical_url(self.context, rootsite='translations')
        return Link(link, text)

    @enabled_with_permission('launchpad.TranslationsAdmin')
    def settings(self):
        text = 'Configure translations'
        return Link('+settings', text, icon='edit', site='translations')

    @enabled_with_permission('launchpad.TranslationsAdmin')
    def language_pack_admin(self):
        text = 'Language pack admin'
        return Link(
            '+select-language-pack-admin', text, icon='edit',
            site='translations')

    def imports(self):
        text = 'Import queue'
        return Link('+imports', text, site='translations')


class DistributionLanguagePackAdminView(LaunchpadEditFormView):
    """Browser view to change the language pack administrator."""

    schema = IDistribution
    label = "Select the language pack administrator"
    field_names = ['language_pack_admin']

    @property
    def cancel_url(self):
        return canonical_url(self.context, rootsite="translations")

    next_url = cancel_url

    @property
    def page_title(self):
        return 'Change the %s language pack administrator' % (
            self.context.displayname)

    @action("Change", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)


class DistributionView(LaunchpadView):
    """Default Distribution view class."""

    label = "Translations overview"

    @cachedproperty
    def translation_focus(self):
        """Return the IDistroSeries where the translators should work.

        If ther isn't a defined focus, we return latest series.
        """
        if self.context.translation_focus is None:
            return self.context.currentseries
        else:
            return self.context.translation_focus

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

    def secondary_translatable_series(self):
        """Return a list of IDistroSeries that aren't the translation_focus.

        It only includes the ones that are still supported.
        """
        series = [
            series
            for series in self.context.series
            if (series.status != SeriesStatus.OBSOLETE
                and (self.translation_focus is None or
                     self.translation_focus.id != series.id))]

        return sorted(series, key=operator.attrgetter('version'),
                      reverse=True)


class DistributionSettingsView(TranslationsMixin, RegistryEditFormView):
    label = "Translations settings"
    page_title = "Settings"
    schema = IDistribution

    field_names = [
        "translations_usage",
        "translation_focus",
        "translationgroup",
        "translationpermission",
        ]

    @property
    def cancel_url(self):
        return canonical_url(self.context, rootsite="translations")

    next_url = cancel_url

    @action('Change', name='change')
    def edit(self, action, data):
        self.updateContextFromData(data)
