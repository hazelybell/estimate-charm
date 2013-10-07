# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser code for Distro Series Languages."""

__metaclass__ = type

__all__ = [
    'DistroSeriesLanguageNavigation',
    'DistroSeriesLanguageView',
    'ProductSeriesLanguageNavigation',
    'ProductSeriesLanguageView',
    ]

from lp.app.browser.tales import PersonFormatterAPI
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.bulk import load_related
from lp.services.propertycache import cachedproperty
from lp.services.webapp import LaunchpadView
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.publisher import Navigation
from lp.translations.enums import TranslationPermission
from lp.translations.interfaces.distroserieslanguage import (
    IDistroSeriesLanguage,
    )
from lp.translations.interfaces.productserieslanguage import (
    IProductSeriesLanguage,
    )
from lp.translations.interfaces.translationsperson import ITranslationsPerson


class BaseSeriesLanguageView(LaunchpadView):
    """View base class to render translation status for an
    `IDistroSeries` and `IProductSeries`

    This class should not be directly instantiated.
    """

    pofiles = None
    label = "Translatable templates"
    series = None
    parent = None
    translationgroup = None

    def initialize(self, series, translationgroup):
        self.series = series
        self.translationgroup = translationgroup
        self.form = self.request.form

        if IDistroSeriesLanguage.providedBy(self.context):
            self.batchnav = BatchNavigator(
                self.series.getCurrentTranslationTemplates(),
                self.request)
            self.pofiles = self.context.getPOFilesFor(
                self.batchnav.currentBatch())
            load_related(
                SourcePackageName, self.batchnav.currentBatch(),
                ['sourcepackagenameID'])
        else:
            self.batchnav = BatchNavigator(self.context.pofiles, self.request)
            self.pofiles = self.batchnav.currentBatch()

    @property
    def translation_group(self):
        """Return the translation group for these translations.

        Return None if there's no translation group for them.
        """
        return self.translationgroup

    @cachedproperty
    def translation_team(self):
        """Return the translation team for these translations.

        Return None if there's no translation team for them.
        """
        if self.translation_group is not None:
            team = self.translation_group.query_translator(
                self.context.language)
        else:
            team = None
        return team

    @property
    def access_level_description(self):
        """Must not be called when there's no translation group."""
        if self.user is None:
            return ("You are not logged in. Please log in to work "
                    "on translations.")

        translations_person = ITranslationsPerson(self.user)
        translations_contact_link = None

        if self.translation_team:
            translations_contact_link = PersonFormatterAPI(
                self.translation_team.translator).link(None)
        elif self.translation_group:
            translations_contact_link = PersonFormatterAPI(
                self.translation_group.owner).link(None)
        else:
            assert self.translation_group is not None, (
                "Must not be called when there's no translation group.")

        if not translations_person.translations_relicensing_agreement:
            translation_license_url = PersonFormatterAPI(
                self.user).url(
                    view_name='+licensing',
                    rootsite='translations')
            return ("To make translations in Launchpad you need to "
                    "agree with the "
                    "<a href='%s'>Translations licensing</a>.") % (
                        translation_license_url)

        if len(self.pofiles) > 0:
            sample_pofile = self.pofiles[0]
            if sample_pofile.canEditTranslations(self.user):
                return "You can add and review translations."

            if sample_pofile.canAddSuggestions(self.user):
                return ("Your suggestions will be held for review by "
                        "%s. If you need help, or your translations are "
                        "not being reviewed, please get in touch with "
                        "%s.") % (
                            translations_contact_link,
                            translations_contact_link)

            permission = sample_pofile.translationpermission
            if permission == TranslationPermission.CLOSED:
                return ("These templates can be translated only by "
                        "their managers.")

        if self.translation_team is None:
            return ("Since there is nobody to manage translation "
                    "approvals into this language, you cannot add "
                    "new suggestions. If you are interested in making "
                    "translations, please contact %s.") % (
                        translations_contact_link)

        raise AssertionError(
            "BUG! Couldn't identify the user's access level for these "
            "translations.")


class DistroSeriesLanguageView(BaseSeriesLanguageView):
    """View class to render translation status for an `IDistroSeries`."""

    def initialize(self):
        series = self.context.distroseries
        super(DistroSeriesLanguageView, self).initialize(
            series=series,
            translationgroup=series.distribution.translationgroup)
        self.parent = self.series.distribution


class ProductSeriesLanguageView(BaseSeriesLanguageView):
    """View class to render translation status for an `IProductSeries`."""

    def initialize(self):
        series = self.context.productseries
        super(ProductSeriesLanguageView, self).initialize(
            series=series,
            translationgroup=series.product.translationgroup)
        self.context.recalculateCounts()
        self.parent = self.series.product


class DistroSeriesLanguageNavigation(Navigation):
    """Navigation for `IDistroSeriesLanguage`."""
    usedfor = IDistroSeriesLanguage


class ProductSeriesLanguageNavigation(Navigation):
    """Navigation for `IProductSeriesLanguage`."""
    usedfor = IProductSeriesLanguage
