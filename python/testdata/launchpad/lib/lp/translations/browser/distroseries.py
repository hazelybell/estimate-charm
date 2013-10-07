# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translations view classes related to `IDistroSeries`."""

__metaclass__ = type

__all__ = [
    'DistroSeriesLanguagePackView',
    'DistroSeriesTemplatesView',
    'DistroSeriesTranslationsAdminView',
    'DistroSeriesTranslationsMenu',
    'DistroSeriesView',
    'check_distroseries_translations_viewable',
    ]

from zope.component import getUtility

from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    )
from lp.app.enums import service_uses_launchpad
from lp.app.errors import TranslationUnavailable
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.series import SeriesStatus
from lp.services.propertycache import cachedproperty
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.menu import (
    enabled_with_permission,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    )
from lp.translations.browser.potemplate import BaseSeriesTemplatesView
from lp.translations.browser.translations import TranslationsMixin
from lp.translations.interfaces.distroserieslanguage import (
    IDistroSeriesLanguageSet,
    )


class DistroSeriesTranslationsAdminView(LaunchpadEditFormView):
    schema = IDistroSeries
    page_title = "Settings"
    label = "Translation settings"
    field_names = ['hide_all_translations', 'defer_translation_imports']

    @property
    def cancel_url(self):
        return canonical_url(self.context, rootsite="translations")

    next_url = cancel_url

    @action("Change")
    def change_action(self, action, data):
        self.updateContextFromData(data)
        self.request.response.addInfoNotification(
            'Your changes have been applied.')


class DistroSeriesLanguagePackView(LaunchpadEditFormView):
    """Browser view to manage used language packs."""
    schema = IDistroSeries
    label = "Language packs"
    page_title = "Language packs"

    def is_langpack_admin(self, action=None):
        """Find out if the current user is a Language Packs Admin.

        This group of users have launchpad.LanguagePacksAdmin rights on
        the DistroSeries but are not general Rosetta admins.

        :returns: True if the user is a Language Pack Admin (but not a
            Rosetta admin)."""
        return (check_permission("launchpad.LanguagePacksAdmin",
                                 self.context) and not
                check_permission("launchpad.TranslationsAdmin", self.context))

    def is_translations_admin(self, action=None):
        """Find out if the current user is a Rosetta Admin.

        :returns: True if the user is a Rosetta Admin.
        """
        return check_permission("launchpad.TranslationsAdmin", self.context)

    @property
    def is_admin(self):
        return self.is_langpack_admin() or self.is_translations_admin()

    def initialize(self):
        self.old_request_value = (
            self.context.language_pack_full_export_requested)
        if self.is_translations_admin():
            self.field_names = [
                'language_pack_base',
                'language_pack_delta',
                'language_pack_proposed',
                'language_pack_full_export_requested',
            ]
        elif self.is_langpack_admin():
            self.field_names = ['language_pack_full_export_requested']
        else:
            self.field_names = []
        super(DistroSeriesLanguagePackView, self).initialize()
        self.displayname = '%s %s' % (
            self.context.distribution.displayname,
            self.context.version)
        if self.is_langpack_admin():
            self.adminlabel = 'Request a full language pack export of %s' % (
                self.displayname)
        else:
            self.adminlabel = 'Settings for language packs'

    @cachedproperty
    def unused_language_packs(self):
        unused_language_packs = list(self.context.language_packs)

        if self.context.language_pack_base in unused_language_packs:
            unused_language_packs.remove(self.context.language_pack_base)
        if self.context.language_pack_delta in unused_language_packs:
            unused_language_packs.remove(self.context.language_pack_delta)
        if self.context.language_pack_proposed in unused_language_packs:
            unused_language_packs.remove(self.context.language_pack_proposed)

        return unused_language_packs

    @property
    def have_latest_full_pack(self):
        """Checks if this distribution series has a full language pack newer
        than the current one."""

        current = self.context.language_pack_base
        latest = self.context.last_full_language_pack_exported
        if (current is None or
            latest is None or
            current.file.http_url == latest.file.http_url):
            return False
        else:
            return True

    @property
    def have_latest_delta_pack(self):
        """Checks if this distribution series has a delta language pack newer
        than the current one."""

        current = self.context.language_pack_delta
        latest = self.context.last_delta_language_pack_exported
        if (current is None or
            latest is None or
            current.file.http_url == latest.file.http_url):
            return False
        else:
            return True

    def _request_full_export(self):
        if (self.old_request_value !=
            self.context.language_pack_full_export_requested):
            # There are changes.
            if self.context.language_pack_full_export_requested:
                self.request.response.addInfoNotification(
                    "Your request has been noted. Next language pack export "
                    "will include all available translations.")
            else:
                self.request.response.addInfoNotification(
                    "Your request has been noted. Next language pack "
                    "export will be made relative to the current base "
                    "language pack.")

    @action("Change Settings", condition=is_translations_admin)
    def change_action(self, action, data):
        if ('language_pack_base' in data and
            data['language_pack_base'] != self.context.language_pack_base):
            # language_pack_base changed, the delta one must be invalidated.
            data['language_pack_delta'] = None
        self.updateContextFromData(data)
        self._request_full_export()
        self.request.response.addInfoNotification(
            'Your changes have been applied.')
        self.next_url = canonical_url(
            self.context, rootsite='translations',
            view_name='+language-packs')

    @action("Request", condition=is_langpack_admin)
    def request_action(self, action, data):
        self.updateContextFromData(data)
        self._request_full_export()
        self.next_url = canonical_url(
            self.context, rootsite='translations',
            view_name='+language-packs')


class DistroSeriesTemplatesView(BaseSeriesTemplatesView):
    """Show a list of all templates for the DistroSeries."""

    def initialize(self):
        super(DistroSeriesTemplatesView, self).initialize(
            series=self.context, is_distroseries=True)

    def constructTemplateURL(self, template):
        """See `BaseSeriesTemplatesView`."""
        return '+source/%s/+pots/%s' % (
            template.sourcepackagename.name, template.name)


class DistroSeriesView(LaunchpadView, TranslationsMixin):

    label = "Translation status by language"

    def initialize(self):
        self.displayname = '%s %s' % (
            self.context.distribution.displayname,
            self.context.version)

    def checkTranslationsViewable(self):
        """ Check if user can view translations for this `IDistroSeries`"""

        # Is user allowed to see translations for this distroseries?
        # If not, raise TranslationUnavailable.
        check_distroseries_translations_viewable(self.context)

    def distroserieslanguages(self):
        """Produces a list containing a DistroSeriesLanguage object for
        each language this distro has been translated into, and for each
        of the user's preferred languages. Where the series has no
        DistroSeriesLanguage for that language, we use a
        DummyDistroSeriesLanguage.
        """

        # find the existing DRLanguages
        distroserieslangs = list(self.context.distroserieslanguages)

        # make a set of the existing languages
        existing_languages = set([drl.language for drl in distroserieslangs])

        # find all the preferred languages which are not in the set of
        # existing languages, and add a dummydistroserieslanguage for each
        # of them
        distroserieslangset = getUtility(IDistroSeriesLanguageSet)
        for lang in self.translatable_languages:
            if lang not in existing_languages:
                distroserieslang = distroserieslangset.getDummy(
                    self.context, lang)
                distroserieslangs.append(distroserieslang)

        return sorted(distroserieslangs, key=lambda a: a.language.englishname)

    def isPreferredLanguage(self, language):
        # if there are no preferred languages, mark all
        # languages as preferred
        if (len(self.translatable_languages) == 0):
            return True
        else:
            return language in self.translatable_languages

    @property
    def potemplates(self):
        return list(self.context.getCurrentTranslationTemplates())

    @property
    def is_translation_focus(self):
        """Is this DistroSeries the translation focus."""
        return self.context.distribution.translation_focus == self.context

    @cachedproperty
    def show_page_content(self):
        """Whether the main content of the page should be shown."""
        return (service_uses_launchpad(self.context.translations_usage) or
               self.is_translations_admin)

    def can_configure_translations(self):
        """Whether or not the user can configure translations."""
        return check_permission("launchpad.Edit", self.context)

    def is_translations_admin(self):
        """Whether or not the user is a translations admin."""
        return check_permission("launchpad.TranslationsAdmin", self.context)


class DistroSeriesTranslationsMenu(NavigationMenu):

    usedfor = IDistroSeries
    facet = 'translations'
    links = [
        'translations', 'templates', 'admin', 'language_packs',
        'latest_full_language_pack', 'latest_delta_language_pack', 'imports']

    def translations(self):
        return Link('', 'Overview', site='translations')

    def imports(self):
        return Link('+imports', 'Import queue', site='translations')

    @enabled_with_permission('launchpad.TranslationsAdmin')
    def admin(self):
        return Link('+admin', 'Settings', site='translations')

    @enabled_with_permission('launchpad.Edit')
    def templates(self):
        return Link('+templates', 'Templates', site='translations')

    def language_packs(self):
        return Link('+language-packs', 'Language packs', site='translations')

    def latest_full_language_pack(self):
        return Link(
            '+latest-full-language-pack',
            'Latest full language pack',
            site='translations')

    def latest_delta_language_pack(self):
        return Link(
            '+latest-delta-language-pack',
            'Latest delta language pack',
            site='translations')


def check_distroseries_translations_viewable(distroseries):
    """Check that these distribution series translations are visible.

    Launchpad admins, Translations admins, and users with admin
    rights on the `IDistroSeries` are always allowed.

    Checks the `hide_all_translations` flag.  If it is set, these
    translations are not to be shown to the public. In that case an
    appropriate message is composed based on the series' `status`,
    and a `TranslationUnavailable` exception is raised.

    :return: Returns normally if this series' translations are
        viewable to the current user.
    :raise TranslationUnavailable: if this series' translations are
        hidden and the user is not one of the limited caste that is
        allowed to access them.
    """

    if not distroseries.hide_all_translations:
        # Yup, viewable.
        return

    if check_permission(
        'launchpad.TranslationsAdmin', distroseries):
        return

    future = [
        SeriesStatus.EXPERIMENTAL,
        SeriesStatus.DEVELOPMENT,
        SeriesStatus.FUTURE,
        ]
    if distroseries.status in future:
        raise TranslationUnavailable(
            "Translations for this release series are not available yet.")
    elif distroseries.status == SeriesStatus.OBSOLETE:
        raise TranslationUnavailable(
            "This release series is obsolete.  Its translations are no "
            "longer available.")
    else:
        raise TranslationUnavailable(
            "Translations for this release series are not currently "
            "available.  Please come back soon.")
