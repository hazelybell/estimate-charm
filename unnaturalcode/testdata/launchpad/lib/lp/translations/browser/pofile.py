# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser code for Translation files."""

__metaclass__ = type

__all__ = [
    'POExportView',
    'POFileFacets',
    'POFileFilteredView',
    'POFileNavigation',
    'POFileNavigationMenu',
    'POFileTranslateView',
    'POFileUploadView',
    'POFileView',
    ]

import os.path
import re
import urllib

from lazr.restful.utils import smartquote
from zope.component import getUtility
from zope.publisher.browser import FileUpload

from lp import _
from lp.app.errors import (
    NotFoundError,
    UnexpectedFormData,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    NavigationMenu,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag
from lp.translations.browser.poexportrequest import BaseExportView
from lp.translations.browser.potemplate import POTemplateFacets
from lp.translations.browser.translationmessage import (
    BaseTranslationView,
    CurrentTranslationMessageView,
    )
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translationimporter import (
    ITranslationImporter,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.interfaces.translationsperson import ITranslationsPerson


class POFileNavigation(Navigation):

    usedfor = IPOFile

    def traverse(self, name):
        """Return the IPOMsgSet associated with the given name."""
        assert self.request.method in ['GET', 'HEAD', 'POST'], (
            'We only know about GET, HEAD, and POST')

        try:
            sequence = int(name)
        except ValueError:
            # The URL does not have a number to do the traversal.
            raise NotFoundError(
                "%r is not a valid sequence number." % name)

        if sequence < 1:
            # We got an invalid sequence number.
            raise NotFoundError(
                "%r is not a valid sequence number." % name)

        potmsgset = self.context.potemplate.getPOTMsgSetBySequence(sequence)

        if potmsgset is None:
            raise NotFoundError(
                "%r is not a valid sequence number." % name)

        return potmsgset.getCurrentTranslationMessageOrDummy(self.context)


class POFileFacets(POTemplateFacets):
    usedfor = IPOFile

    def __init__(self, context):
        POTemplateFacets.__init__(self, context.potemplate)


class POFileMenuMixin:
    """Mixin class to share code between navigation and action menus."""

    def details(self):
        text = 'Translation details'
        return Link('+details', text, icon='info')

    def translate(self):
        text = 'Translate'
        return Link('+translate', text, icon='language')

    @enabled_with_permission('launchpad.Edit')
    def upload(self):
        text = 'Upload translation'
        return Link('+upload', text, icon='add')

    def download(self):
        text = 'Download translation'
        return Link('+export', text, icon='download')


class POFileNavigationMenu(NavigationMenu, POFileMenuMixin):
    """Navigation menus for `IPOFile` objects."""
    usedfor = IPOFile
    facet = 'translations'
    links = ('details', 'translate', 'upload', 'download')


class POFileMetadataViewMixin:
    """`POFile` metadata that multiple views can use."""

    @cachedproperty
    def translation_group(self):
        """Is there a translation group for this translation?

        :return: TranslationGroup or None if not found.
        """
        translation_groups = self.context.potemplate.translationgroups
        if translation_groups is not None and len(translation_groups) > 0:
            group = translation_groups[0]
        else:
            group = None
        return group

    @cachedproperty
    def translator_entry(self):
        """The translator entry or None if none is assigned."""
        group = self.translation_group
        if group is not None:
            return group.query_translator(self.context.language)
        return None

    @cachedproperty
    def translator(self):
        """Who is assigned for translations to this language?"""
        translator_entry = self.translator_entry
        if translator_entry is not None:
            return translator_entry.translator
        return None

    @cachedproperty
    def user_is_new_translator(self):
        """Is this user someone who has done no translation work yet?"""
        user = getUtility(ILaunchBag).user
        if user is not None:
            translationsperson = ITranslationsPerson(user)
            if not translationsperson.hasTranslated():
                return True

        return False

    @cachedproperty
    def translation_group_guide(self):
        """URL to translation group's translation guide, if any."""
        group = self.translation_group
        if group is None:
            return None
        else:
            return group.translation_guide_url

    @cachedproperty
    def translation_team_guide(self):
        """URL to translation team's translation guide, if any."""
        translator = self.translator_entry
        if translator is None:
            return None
        else:
            return translator.style_guide_url

    @cachedproperty
    def has_any_documentation(self):
        """Return whether there is any documentation for this POFile."""
        return (
            self.translation_group_guide is not None or
            self.translation_team_guide is not None or
            self.user_is_new_translator)

    @property
    def introduction_link(self):
        """Link to introductory documentation, if appropriate.

        If no link is appropriate, returns the empty string.
        """
        if not self.user_is_new_translator:
            return ""

        return """
            New to translating in Launchpad?
            <a href="/+help-translations/new-to-translating.html"
            target="help">Read our guide</a>.
            """

    @property
    def guide_links(self):
        """Links to translation group/team guidelines, if available.

        If no guidelines are available, returns the empty string.
        """
        group_guide = self.translation_group_guide
        team_guide = self.translation_team_guide
        if group_guide is None and team_guide is None:
            return ""

        links = []
        if group_guide is not None:
            links.append(
                structured(
                    '<a class="style-guide-url" href="%s">%s instructions</a>',
                    group_guide, self.translation_group.title).escapedtext)

        if team_guide is not None:
            if group_guide is None:
                # Use team's full name.
                name = self.translator.displayname
            else:
                # Full team name may get tedious after we just named the
                # group.  Just use the language name.
                name = self.context.language.englishname
            links.append(
                structured(
                    '<a class="style-guide-url" href="%s"> %s guidelines</a>',
                    team_guide, name).escapedtext)

        text = ' and '.join(links).rstrip()

        return "Before translating, be sure to go through %s." % text

    @property
    def documentation_link_bubble(self):
        """Reference to documentation, if appropriate."""
        if not self.has_any_documentation:
            return ""

        return """
            <div class="important-notice-container">
                <div class="important-notice-balloon">
                    <div class="important-notice-buttons">
                        <img class="important-notice-cancel-button"
                             src="/@@/no"
                             alt="Don't show this notice anymore"
                             title="Hide this notice." />
                    </div>
                    <span class="sprite info">
                    <span class="important-notice">
                        %s
                    </span>
                </div>
            </div>
            """ % ' '.join([
                self.introduction_link, self.guide_links])


class POFileView(LaunchpadView):
    """A basic view for a POFile"""

    @cachedproperty
    def contributors(self):
        return list(self.context.contributors)

    @cachedproperty
    def user_can_edit(self):
        """Does the user have full edit rights for this translation?"""
        return self.context.canEditTranslations(self.user)

    @cachedproperty
    def user_can_suggest(self):
        """Is the user allowed to make suggestions here?"""
        return self.context.canAddSuggestions(self.user)

    @cachedproperty
    def has_translationgroup(self):
        """Is there a translation group for this translation?"""
        return self.context.potemplate.translationgroups

    @cachedproperty
    def is_managed(self):
        """Is a translation group member assigned to this translation?"""
        for group in self.context.potemplate.translationgroups:
            if group.query_translator(self.context.language):
                return True
        return False

    @cachedproperty
    def managers(self):
        """List translation groups and translation teams for this translation.

        Returns a list of descriptions of who may manage this
        translation.  Each entry contains a "group" (the
        `TranslationGroup`) and a "team" (the translation team, or
        possibly a single person).  The team is None for groups that
        haven't assigned a translation team for this translation's
        language.

        Duplicates are eliminated; every translation group will occur
        at most once.
        """
        managers = []
        policy = self.context.potemplate.getTranslationPolicy()
        translators = policy.getTranslators(self.context.language)
        for group, translator, team in reversed(translators):
            if translator is None:
                style_guide_url = None
            else:
                style_guide_url = translator.style_guide_url
            managers.append({
                'group': group,
                'team': team,
                'style_guide_url': style_guide_url,
            })
        return managers


class POFileDetailsView(POFileView):
    """View for the detail page of a POFile"""

    page_title = _("Details")

    @property
    def label(self):
        return _("Details for %s translation") % (
                    self.context.language.englishname)


class TranslationMessageContainer:
    """A `TranslationMessage` decorated with usage class.

    The usage class (in-use, hidden" or suggested) is used in CSS to
    render these messages differently.
    """

    def __init__(self, translation, pofile):
        self.data = translation

        # Assign a CSS class to the translation
        # depending on whether it's used, suggested,
        # or an obsolete suggestion.
        if translation.is_current_ubuntu:
            self.usage_class = 'usedtranslation'
        else:
            if translation.isHidden(pofile):
                self.usage_class = 'hiddentranslation'
            else:
                self.usage_class = 'suggestedtranslation'


class FilteredPOTMsgSets:
    """`POTMsgSet`s and translations shown by the `POFileFilteredView`."""

    def __init__(self, translations, pofile):
        potmsgsets = []
        current_potmsgset = None
        if translations is None:
            self.potmsgsets = None
        else:
            for translation in translations:
                if (current_potmsgset is not None and
                    current_potmsgset['potmsgset'] == translation.potmsgset):
                    current_potmsgset['translations'].append(
                        TranslationMessageContainer(translation, pofile))
                else:
                    if current_potmsgset is not None:
                        potmsgsets.append(current_potmsgset)
                    translation.setPOFile(pofile)
                    current_potmsgset = {
                        'potmsgset': translation.potmsgset,
                        'translations': [
                            TranslationMessageContainer(translation, pofile)],
                        'context': translation,
                        }
            if current_potmsgset is not None:
                potmsgsets.append(current_potmsgset)

            self.potmsgsets = potmsgsets


class POFileFilteredView(LaunchpadView):
    """A filtered view for a `POFile`."""

    DEFAULT_BATCH_SIZE = 50

    @property
    def _person_name(self):
        """Person's display name.  Graceful about unknown persons."""
        if self.person is None:
            return "unknown person"
        else:
            return self.person.displayname

    @property
    def page_title(self):
        """See `LaunchpadView`."""
        return smartquote('Translations by %s in "%s"') % (
            self._person_name, self.context.title)

    def label(self):
        """See `LaunchpadView`."""
        return "Translations by %s" % self._person_name

    def initialize(self):
        """See `LaunchpadView`."""
        self.person = None
        person = self.request.form.get('person')
        if person is None:
            self.request.response.addErrorNotification(
                "No person to filter by specified.")
            translations = None
        else:
            self.person = getUtility(IPersonSet).getByName(person)
            if self.person is None:
                self.request.response.addErrorNotification(
                    "Requested person not found.")
                translations = None
            else:
                translations = self.context.getTranslationsFilteredBy(
                    person=self.person)
        self.batchnav = BatchNavigator(translations, self.request,
                                       size=self.DEFAULT_BATCH_SIZE)

    @property
    def translations(self):
        """Group a list of `TranslationMessages` under `POTMsgSets`.

        Batching is done over TranslationMessages, and in order to
        display them grouped by English string, we transform the
        current batch.
        """
        return FilteredPOTMsgSets(self.batchnav.currentBatch(),
                                  self.context).potmsgsets


class POFileUploadView(POFileView):
    """A basic view for a `POFile`."""

    page_title = "Upload translation"

    def initialize(self):
        self.form = self.request.form
        self.process_form()

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def label(self):
        return "Upload %s translation" % self.context.language.englishname

    def process_form(self):
        """Handle a form submission to request a translation file upload."""
        # XXX henninge 2008-12-03 bug=192925: This code is duplicated for
        # productseries and potemplate and should be unified.

        if self.request.method != 'POST' or self.user is None:
            # The form was not submitted or the user is not logged in.
            return

        upload_file = self.form.get('file', None)

        if not isinstance(upload_file, FileUpload):
            if upload_file is None or upload_file == '':
                self.request.response.addErrorNotification(
                    "Ignored your upload because you didn't select a file to"
                    " upload.")
            else:
                # XXX: Carlos Perello Marin 2004-12-30 bug=116:
                # Epiphany seems to have an unpredictable bug with upload
                # forms (or perhaps it's launchpad because I never had
                # problems with bugzilla). The fact is that some uploads don't
                # work and we get a unicode object instead of a file-like
                # object in "upload_file". We show an error if we see that
                # behaviour.
                self.request.response.addErrorNotification(
                    "The upload failed because there was a problem receiving"
                    " the data.")
            return

        filename = upload_file.filename
        content = upload_file.read()

        if len(content) == 0:
            self.request.response.addWarningNotification(
                "Ignored your upload because the uploaded file is empty.")
            return

        translation_import_queue = getUtility(ITranslationImportQueue)
        root, ext = os.path.splitext(filename)
        translation_importer = getUtility(ITranslationImporter)
        if (ext not in translation_importer.supported_file_extensions):
            self.request.response.addErrorNotification(
                "Ignored your upload because the file you uploaded was not"
                " recognised as a file that can be imported.")
            return

        # Uploads on this form are never done by the maintainer.
        by_maintainer = False

        if self.context.path is None:
            # The POFile is a dummy one, we use the filename as the path.
            path = filename
        else:
            path = self.context.path
        # Add it to the queue.
        translation_import_queue.addOrUpdateEntry(
            path, content, by_maintainer, self.user,
            sourcepackagename=self.context.potemplate.sourcepackagename,
            distroseries=self.context.potemplate.distroseries,
            productseries=self.context.potemplate.productseries,
            potemplate=self.context.potemplate, pofile=self.context)

        self.request.response.addInfoNotification(
            structured(
            'Thank you for your upload.  It will be automatically '
            'reviewed in the next hours.  If that is not '
            'enough to determine whether and where your file '
            'should be imported, it will be reviewed manually by an '
            'administrator in the coming few days.  You can track '
            'your upload\'s status in the '
            '<a href="%s/+imports">Translation Import Queue</a>',
            canonical_url(self.context.potemplate.translationtarget)))


class POFileBatchNavigator(BatchNavigator):
    """Special BatchNavigator to override the maximum batch size."""

    @property
    def max_batch_size(self):
        return config.rosetta.translate_pages_max_batch_size


class POFileTranslateView(BaseTranslationView, POFileMetadataViewMixin):
    """The View class for a `POFile` or a `DummyPOFile`.

    This view is based on `BaseTranslationView` and implements the API
    defined by that class.

    `DummyPOFile`s are presented where there is no `POFile` in the
    database but the user may want to translate.  See how `POTemplate`
    traversal is done for details about how we decide between a `POFile`
    or a `DummyPOFile`.
    """

    DEFAULT_SHOW = 'all'
    DEFAULT_SIZE = 10

    def initialize(self):
        self.pofile = self.context
        translations_person = ITranslationsPerson(self.user, None)
        if (self.user is not None and
            translations_person.translations_relicensing_agreement is None):
            url = str(self.request.URL).decode('US-ASCII', 'replace')
            if self.request.get('QUERY_STRING', None):
                url = url + '?' + self.request['QUERY_STRING']

            return self.request.response.redirect(
                canonical_url(self.user, view_name='+licensing',
                              rootsite='translations') +
                '?' + urllib.urlencode({'back_to': url}))

        # The handling of errors is slightly tricky here. Because this
        # form displays multiple POMsgSetViews, we need to track the
        # various errors individually. This dictionary is keyed on
        # POTMsgSet; it's a slightly unusual key value but it will be
        # useful for doing display of only widgets with errors when we
        # do that.
        self.errors = {}
        self.translationmessage_views = []
        # The batchnav's start should change when the user mutates a
        # filtered views of messages.
        self.start_offset = 0

        self._initializeShowOption()
        super(POFileTranslateView, self).initialize()

    #
    # BaseTranslationView API
    #

    def _buildBatchNavigator(self):
        """See BaseTranslationView._buildBatchNavigator."""

        # Changing the "show" option resets batching.
        old_show_option = self.request.form_ng.getOne('old_show')
        show_option_changed = (
            old_show_option is not None and old_show_option != self.show)
        if show_option_changed:
            # Start will be 0 by default.
            force_start = True
        else:
            force_start = False
        return POFileBatchNavigator(self._getSelectedPOTMsgSets(),
                                    self.request, size=self.DEFAULT_SIZE,
                                    transient_parameters=["old_show"],
                                    force_start=force_start)

    def _initializeTranslationMessageViews(self):
        """See BaseTranslationView._initializeTranslationMessageViews."""
        self._buildTranslationMessageViews(self.batchnav.currentBatch())

    def _buildTranslationMessageViews(self, for_potmsgsets):
        """Build translation message views for all potmsgsets given."""
        can_edit = self.context.canEditTranslations(self.user)
        for potmsgset in for_potmsgsets:
            translationmessage = (
                potmsgset.getCurrentTranslationMessageOrDummy(self.context))
            error = self.errors.get(potmsgset)

            view = self._prepareView(
                CurrentTranslationMessageView, translationmessage,
                pofile=self.context, can_edit=can_edit, error=error)
            view.zoomed_in_view = False
            self.translationmessage_views.append(view)

    def _submitTranslations(self):
        """See BaseTranslationView._submitTranslations."""
        for key in self.request.form:
            match = re.match('msgset_(\d+)$', key)
            if not match:
                continue

            id = int(match.group(1))
            potmsgset = self.context.potemplate.getPOTMsgSetByID(id)
            if potmsgset is None:
                # This should only happen if someone tries to POST his own
                # form instead of ours, and he uses a POTMsgSet id that
                # does not exist for this POTemplate.
                raise UnexpectedFormData(
                    "Got translation for POTMsgID %d which is not in the "
                    "template." % id)

            error = self._receiveTranslations(potmsgset)
            if error and potmsgset.getSequence(self.context.potemplate) != 0:
                # There is an error, we should store it to be rendered
                # together with its respective view.
                #
                # The check for potmsgset.getSequence() != 0 is meant to catch
                # messages which are not current anymore. This only
                # happens as part of a race condition, when someone gets
                # a translation form, we get a new template for
                # that context that disables some entries in that
                # translation form, and after that, the user submits the
                # form. We accept the translation, but if it has an
                # error, we cannot render that error so we discard it,
                # that translation is not being used anyway, so it's not
                # a big loss.
                self.errors[potmsgset] = error

        if self.errors:
            if len(self.errors) == 1:
                message = ("There is an error in a translation you provided. "
                           "Please correct it before continuing.")
            else:
                message = ("There are %d errors in the translations you "
                           "provided. Please correct them before "
                           "continuing." % len(self.errors))
            self.request.response.addErrorNotification(message)
            return False

        if self.batchnav.batch.nextBatch() is not None:
            # Update the start of the next batch by the number of messages
            # that were removed from the batch.
            self.batchnav.batch.start -= self.start_offset
        self._redirectToNextPage()
        return True

    def _observeTranslationUpdate(self, potmsgset):
        """see `BaseTranslationView`.

        Update the start_offset when the filtered batch has mutated.
        """
        if self.show == 'untranslated':
            translationmessage = potmsgset.getCurrentTranslation(
                self.pofile.potemplate, self.pofile.language,
                self.pofile.potemplate.translation_side)
            if translationmessage is not None:
                self.start_offset += 1
        elif self.show == 'new_suggestions':
            new_suggestions = potmsgset.getLocalTranslationMessages(
                self.pofile.potemplate, self.pofile.language)
            if new_suggestions.count() == 0:
                self.start_offset += 1
        else:
            # This change does not mutate the batch.
            pass

    def _buildRedirectParams(self):
        parameters = BaseTranslationView._buildRedirectParams(self)
        if self.show and self.show != self.DEFAULT_SHOW:
            parameters['show'] = self.show
        return parameters

    #
    # Specific methods
    #

    def _initializeShowOption(self):
        # Get any value given by the user
        self.show = self.request.form_ng.getOne('show')
        self.search_text = self.request.form_ng.getOne('search')
        if self.search_text is not None:
            self.show = 'all'

        # Functions that deliver the correct message counts for each
        # valid option value.
        count_functions = {
            'all': self.context.messageCount,
            'translated': self.context.translatedCount,
            'untranslated': self.context.untranslatedCount,
            'new_suggestions': self.context.unreviewedCount,
            'changed_in_ubuntu': self.context.updatesCount,
            }

        if self.show not in count_functions:
            self.show = self.DEFAULT_SHOW

        self.shown_count = count_functions[self.show]()

    def _handleShowAll(self):
        """Get `POTMsgSet`s when filtering for "all" (but possibly searching).

        Normally returns all `POTMsgSet`s for this `POFile`, but also handles
        search requests which act as a separate form of filtering.
        """
        if self.search_text is None:
            return self.context.potemplate.getPOTMsgSets()

        if len(self.search_text) <= 1:
            self.request.response.addWarningNotification(
                "Please try searching for a longer string.")
            return self.context.potemplate.getPOTMsgSets()

        return self.context.findPOTMsgSetsContaining(text=self.search_text)

    def _getSelectedPOTMsgSets(self):
        """Return a list of the POTMsgSets that will be rendered."""
        # The set of message sets we get is based on the selection of kind
        # of strings we have in our form.
        get_functions = {
            'all': self._handleShowAll,
            'translated': self.context.getPOTMsgSetTranslated,
            'untranslated': self.context.getPOTMsgSetUntranslated,
            'new_suggestions': self.context.getPOTMsgSetWithNewSuggestions,
            'changed_in_ubuntu':
                self.context.getPOTMsgSetDifferentTranslations,
            }

        if self.show not in get_functions:
            raise UnexpectedFormData('show = "%s"' % self.show)

        # We cannot listify the results to avoid additional count queries,
        # because we could end up with a list of more than 32000 items with
        # an average list of 5000 items.
        # The batch system will slice the list of items so we will fetch only
        # the exact number of entries we need to render the page.
        return get_functions[self.show]()

    @property
    def completeness(self):
        return '%.0f%%' % self.context.translatedPercentage()

    def _messages_html_id(self):
        order = []
        if self.form_is_writeable:
            for message in self.translationmessage_views:
                order += [
                    dictionary['html_id_translation'] + '_new'
                    for dictionary in message.translation_dictionaries]
        return order

    @property
    def autofocus_html_id(self):
        if (len(self._messages_html_id()) > 0):
            return self._messages_html_id()[0]
        else:
            return ""

    @property
    def translations_order(self):
        return ' '.join(self._messages_html_id())

    @property
    def is_upstream_pofile(self):
        potemplate = self.context.potemplate
        return potemplate.translation_side == TranslationSide.UPSTREAM

    def is_sharing(self):
        potemplate = self.context.potemplate.getOtherSidePOTemplate()
        return potemplate is not None

    @property
    def sharing_pofile(self):
        potemplate = self.context.potemplate.getOtherSidePOTemplate()
        if potemplate is None:
            return None
        pofile = potemplate.getPOFileByLang(self.context.language.code)
        if pofile is None:
            pofile = potemplate.getDummyPOFile(
                self.context.language, check_for_existing=False)
        return pofile


class POExportView(BaseExportView):

    page_title = "Download translation"

    def getExportFormat(self):
        format = self.request.form.get("format")
        pochanged = self.request.form.get("pochanged")
        if format == 'PO' and pochanged == 'POCHANGED':
            return 'POCHANGED'
        return format

    def processForm(self):
        is_upstream = (
            self.context.potemplate.translation_side ==
                TranslationSide.UPSTREAM)
        if is_upstream and self.getExportFormat() == 'POCHANGED':
            other_side_pofile = self.context.getOtherSidePOFile()
            if other_side_pofile is None:
                return None
            return (None, [other_side_pofile])
        return (None, [self.context])

    def getDefaultFormat(self):
        return self.context.potemplate.source_file_format

    @property
    def has_pochanged_option(self):
        is_ubuntu = (
            self.context.potemplate.translation_side ==
                TranslationSide.UBUNTU)
        if is_ubuntu:
            return True
        other_side_pofile = self.context.getOtherSidePOFile()
        return other_side_pofile is not None

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def label(self):
        return "Download %s translation" % self.context.language.englishname
