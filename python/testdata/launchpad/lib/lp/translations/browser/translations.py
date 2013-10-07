# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'RosettaApplicationView',
    'RosettaStatsView',
    'RosettaApplicationNavigation',
    'TranslateRedirectView',
    'TranslationsLanguageBreadcrumb',
    'TranslationsMixin',
    'TranslationsRedirectView',
    'TranslationsVHostBreadcrumb',
    ]

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.geoip.interfaces import IRequestPreferredLanguages
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    Navigation,
    stepto,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.services.webapp.publisher import RedirectionView
from lp.services.worlddata.helpers import preferred_or_request_languages
from lp.services.worlddata.interfaces.country import ICountry
from lp.translations.interfaces.translations import IRosettaApplication
from lp.translations.publisher import TranslationsLayer


class TranslationsMixin:
    """Provide Translations specific properties."""

    @cachedproperty
    def translatable_languages(self):
        """Return a set of the Person's translatable languages."""
        english = getUtility(ILaunchpadCelebrities).english
        languages = preferred_or_request_languages(self.request)
        if english in languages:
            return [lang for lang in languages if lang != english]
        return languages

    @cachedproperty
    def answers_url(self):
        return canonical_url(
            getUtility(ILaunchpadCelebrities).launchpad,
            rootsite='answers')


class RosettaApplicationView(LaunchpadView, TranslationsMixin):
    """View for various top-level Translations pages."""

    page_title = 'Launchpad Translations'

    @property
    def ubuntu_translationseries(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        series = ubuntu.translation_focus
        if series is None:
            return ubuntu.currentseries
        else:
            return series

    def ubuntu_languages(self):
        langs = []
        series = self.ubuntu_translationseries
        for language in self.languages:
            langs.append(series.getDistroSeriesLanguageOrDummy(language))
        return langs

    def requestCountry(self):
        return ICountry(self.request, None)

    def browserLanguages(self):
        return IRequestPreferredLanguages(
            self.request).getPreferredLanguages()

    @cachedproperty
    def batchnav(self):
        """Return a BatchNavigator for the list of translatable products."""
        products = getUtility(IProductSet)
        return BatchNavigator(products.getTranslatables(),
                              self.request)

    def rosettaAdminEmail(self):
        return config.rosettaadmin.email

    @property
    def launchpad_users_team(self):
        """The url of the launchpad-users team."""
        team = getUtility(IPersonSet).getByName('launchpad-users')
        return canonical_url(team)


class TranslatableProductsView(LaunchpadView):
    """List of translatable products."""
    label = "Projects with translations in Launchpad"
    page_title = label

    @cachedproperty
    def batchnav(self):
        """Navigate the list of translatable products."""
        return BatchNavigator(
            getUtility(IProductSet).getTranslatables(), self.request)


class RosettaStatsView(LaunchpadView):
    """A view class for objects that support IRosettaStats. This is mainly
    used for the sortable untranslated percentage."""

    def sortable_untranslated(self):
        return '%06.2f' % self.context.untranslatedPercentage()


class RosettaApplicationNavigation(Navigation):

    usedfor = IRosettaApplication

    newlayer = TranslationsLayer

    @stepto('groups')
    def redirect_groups(self):
        """Redirect /translations/+groups to Translations root site."""
        target_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='translations')
        return self.redirectSubTree(
            target_url + '+groups', status=301)

    @stepto('imports')
    def redirect_imports(self):
        """Redirect /translations/imports to Translations root site."""
        target_url = canonical_url(
            getUtility(ILaunchpadRoot), rootsite='translations')
        return self.redirectSubTree(
            target_url + '+imports', status=301)

    @stepto('projects')
    def projects(self):
        # DEPRECATED
        return getUtility(IProductSet)

    @stepto('products')
    def products(self):
        # DEPRECATED
        return getUtility(IProductSet)


class TranslateRedirectView(RedirectionView):
    """Redirects to translations site for +translate page."""

    def __init__(self, context, request):
        target = canonical_url(
            context, rootsite='translations', view_name='+translate')
        super(TranslateRedirectView, self).__init__(
            target, request, status=301)


class TranslationsRedirectView(RedirectionView):
    """Redirects to translations site for +translations page."""

    def __init__(self, context, request):
        target = canonical_url(
            context, rootsite='translations', view_name='+translations')
        super(TranslationsRedirectView, self).__init__(
            target, request, status=301)


class TranslationsVHostBreadcrumb(Breadcrumb):
    rootsite = 'translations'
    text = 'Translations'


class TranslationsLanguageBreadcrumb(Breadcrumb):
    """Breadcrumb for objects with language."""

    @property
    def text(self):
        return self.context.language.displayname
