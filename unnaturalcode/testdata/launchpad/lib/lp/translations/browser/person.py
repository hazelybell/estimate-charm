# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person-related translations view classes."""

__metaclass__ = type

__all__ = [
    'PersonTranslationView',
    'PersonTranslationRelicensingView',
    'TranslationActivityView',
]

from datetime import (
    datetime,
    timedelta,
    )
from itertools import islice
import urllib

import pytz
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib.widgets import TextWidget
from zope.interface import (
    implements,
    Interface,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.enums import ServiceUsage
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    Link,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.menu import NavigationMenu
from lp.services.webapp.publisher import LaunchpadView
from lp.translations.browser.translationlinksaggregator import (
    TranslationLinksAggregator,
    )
from lp.translations.interfaces.pofiletranslator import IPOFileTranslatorSet
from lp.translations.interfaces.translationrelicensingagreement import (
    ITranslationRelicensingAgreementEdit,
    TranslationRelicensingAgreementOptions,
    )
from lp.translations.interfaces.translationsperson import ITranslationsPerson


class WorkListLinksAggregator(TranslationLinksAggregator):
    """Aggregate translation links for translation or review.

    Here, all files are actually `POFile`s, never `POTemplate`s.
    """

    def countStrings(self, pofile):
        """Count number of strings that need work."""
        raise NotImplementedError()

    def describe(self, target, link, covered_files):
        """See `TranslationLinksAggregator.describe`."""
        strings_count = sum(
            [self.countStrings(pofile) for pofile in covered_files])
        languages = set(
            [pofile.language.englishname for pofile in covered_files])
        languages_list = ", ".join(sorted(languages))

        if strings_count == 1:
            strings_wording = "%d string"
        else:
            strings_wording = "%d strings"

        return {
            'target': target,
            'count': strings_count,
            'count_wording': strings_wording % strings_count,
            'is_product': not ISourcePackage.providedBy(target),
            'link': link,
            'languages': languages_list,
        }


class ReviewLinksAggregator(WorkListLinksAggregator):
    """A `TranslationLinksAggregator` for translations to review."""
    # Link to unreviewed suggestions.
    pofile_link_suffix = '/+translate?show=new_suggestions'

    # Strings that need work are ones with unreviewed suggestions.
    def countStrings(self, pofile):
        """See `WorkListLinksAggregator.countStrings`."""
        return pofile.unreviewedCount()


class TranslateLinksAggregator(WorkListLinksAggregator):
    """A `TranslationLinksAggregator` for translations to complete."""
    # Link to untranslated strings.
    pofile_link_suffix = '/+translate?show=untranslated'

    # Strings that need work are untranslated ones.
    def countStrings(self, pofile):
        """See `WorkListLinksAggregator.countStrings`."""
        return pofile.untranslatedCount()


def compose_pofile_filter_url(pofile, person):
    """Compose URL for `Person`'s contributions to `POFile`."""
    person_name = urllib.urlencode({'person': person.name})
    return canonical_url(pofile) + "/+filter?%s" % person_name


class ActivityDescriptor:
    """Description of a past translation activity."""

    date = None
    title = None
    url = None

    def __init__(self, person, pofiletranslator):
        """Describe a past translation activity by `person`.

        :param person: The `Person` whose activity is being described.
        :param pofiletranslator: A `POFileTranslator` record for
            `person`.
        """
        assert person == pofiletranslator.person, (
            "Got POFileTranslator record for user %s "
            "while listing activity for %s." % (
                person.name, pofiletranslator.person.name))

        self._person = person
        self._pofiletranslator = pofiletranslator

    @cachedproperty
    def date(self):
        return self._pofiletranslator.date_last_touched

    @cachedproperty
    def _pofile(self):
        return self._pofiletranslator.pofile

    @cachedproperty
    def title(self):
        return self._pofile.potemplate.translationtarget.title

    @cachedproperty
    def url(self):
        return compose_pofile_filter_url(self._pofile, self._person)


def person_is_reviewer(person):
    """Is `person` a translations reviewer?"""
    groups = ITranslationsPerson(person).translation_groups
    return groups.any() is not None


class IPersonTranslationsMenu(Interface):
    """Marker interface for `Person` Translations navigation menu."""


class PersonTranslationsMenu(NavigationMenu):

    usedfor = IPersonTranslationsMenu
    facet = 'translations'
    links = ('overview', 'licensing', 'imports', 'translations_to_review')

    @property
    def person(self):
        return self.context.context

    def overview(self):
        text = 'Overview'
        return Link('', text, icon='info', site='translations')

    def imports(self):
        text = 'Import queue'
        return Link('+imports', text, icon='info', site='translations')

    def licensing(self):
        text = 'Translations licensing'
        enabled = (self.person == self.user)
        return Link('+licensing', text, enabled=enabled, icon='info',
                    site='translations')

    def translations_to_review(self):
        text = 'Translations to review'
        enabled = person_is_reviewer(self.person)
        return Link(
            '+translations-to-review', text, enabled=enabled, icon='info',
            site='translations')


class PersonTranslationView(LaunchpadView):
    """View for translation-related Person pages."""
    implements(IPersonTranslationsMenu)

    reviews_to_show = 10

    def __init__(self, *args, **kwargs):
        super(PersonTranslationView, self).__init__(*args, **kwargs)
        now = datetime.now(pytz.timezone('UTC'))
        # Down-to-the-second detail isn't important so the hope is that this
        # will result in faster queries (cache effects).
        today = now.replace(minute=0, second=0, microsecond=0)
        self.history_horizon = today - timedelta(90, 0, 0)
        self.user_can_edit = check_permission('launchpad.Edit', self.context)

    @property
    def page_title(self):
        return "Translations related to %s" % self.context.displayname

    @cachedproperty
    def recent_activity(self):
        """Recent translation activity by this person.

        If the translation activity is associated with a project, we ensure
        that the project is active.
        """
        all_entries = ITranslationsPerson(self.context).translation_history

        def is_active(entry):
            potemplate = entry.pofile.potemplate
            if potemplate is None:
                return True
            product = potemplate.product
            product_is_active = (
                product is None or (
                product.active and
                product.translations_usage == ServiceUsage.LAUNCHPAD))
            return product_is_active

        active_entries = (entry for entry in all_entries if is_active(entry))
        return [ActivityDescriptor(self.context, entry)
            for entry in islice(active_entries, 10)]

    @cachedproperty
    def latest_activity(self):
        """Single latest translation activity by this person."""
        translations_person = ITranslationsPerson(self.context)
        latest = list(translations_person.translation_history[:1])
        if len(latest) == 0:
            return None
        else:
            return ActivityDescriptor(self.context, latest[0])

    @cachedproperty
    def translation_groups(self):
        """Return translation groups a person is a member of."""
        translations_person = ITranslationsPerson(self.context)
        return list(translations_person.translation_groups)

    @cachedproperty
    def translators(self):
        """Return translators a person is a member of."""
        translations_person = ITranslationsPerson(self.context)
        return list(translations_person.translators)

    @property
    def person_is_reviewer(self):
        """Is this person in a translation group?"""
        return person_is_reviewer(self.context)

    @property
    def person_is_translator(self):
        """Is this person active in translations?"""
        if self.context.is_team:
            return False
        person = ITranslationsPerson(self.context)
        history = person.getTranslationHistory(self.history_horizon).any()
        return history is not None

    @property
    def person_includes_me(self):
        """Is the current user (a member of) this person?"""
        user = getUtility(ILaunchBag).user
        if user is None:
            return False
        else:
            return user.inTeam(self.context)

    @property
    def requires_preferred_languages(self):
        """Does this person need to set preferred languages?"""
        return not self.context.is_team and len(self.context.languages) == 0

    def should_display_message(self, translationmessage):
        """Should a certain `TranslationMessage` be displayed.

        Return False if user is not logged in and message may contain
        sensitive data such as email addresses.

        Otherwise, return True.
        """
        if self.user:
            return True
        return not (
            translationmessage.potmsgset.hide_translations_from_anonymous)

    @cachedproperty
    def _review_targets(self):
        """Query and aggregate the top targets for review.

        :return: a list of translation targets.  Multiple `POFile`s may be
            aggregated together into a single target.
        """
        person = ITranslationsPerson(self.context)
        pofiles = person.getReviewableTranslationFiles(
            no_older_than=self.history_horizon)

        return ReviewLinksAggregator().aggregate(pofiles)

    def _getTargetsForTranslation(self, max_fetch=None):
        """Get translation targets for this person to translate.

        Results are ordered from most to fewest untranslated messages.
        """
        person = ITranslationsPerson(self.context)
        urgent_first = (max_fetch >= 0)
        pofiles = person.getTranslatableFiles(
            no_older_than=self.history_horizon, urgent_first=urgent_first)

        if max_fetch is not None:
            pofiles = pofiles[:abs(max_fetch)]

        return TranslateLinksAggregator().aggregate(pofiles)

    @cachedproperty
    def all_projects_and_packages_to_review(self):
        """Top projects and packages for this person to review."""
        return self._review_targets

    def _addToTargetsList(self, existing_targets, new_targets, max_items,
                          max_overall):
        """Add `new_targets` to `existing_targets` list.

        This is for use in showing top-10 ists of translations a user
        should help review or complete.

        :param existing_targets: Translation targets that are already
            being listed.
        :param new_targets: Translation targets to add.  Ones that were
            already in `existing_targets` will not be added again.
        :param max_items: Maximum number of targets from `new_targets`
            to add.
        :param max_overall: Maximum overall size of the resulting list.
            What happens if `existing_targets` already exceeds this size
            is none of your business.
        :return: A list of translation targets containing all of
            `existing_targets`, followed by as many from `new_targets`
            as there is room for.
        """
        remaining_slots = max_overall - len(existing_targets)
        maximum_addition = min(max_items, remaining_slots)
        if remaining_slots <= 0:
            return existing_targets

        known_targets = set([item['target'] for item in existing_targets])
        really_new = [
            item
            for item in new_targets
            if item['target'] not in known_targets
            ]

        return existing_targets + really_new[:maximum_addition]

    @property
    def top_projects_and_packages_to_review(self):
        """Suggest translations for this person to review."""
        # Maximum number of projects/packages to list that this person
        # has recently worked on.
        max_known_targets = 9
        # Length of overall list to display.
        list_length = 10

        # Start out with the translations that the person has recently
        # worked on.
        recent = self._review_targets
        return self._addToTargetsList(
            [], recent, max_known_targets, list_length)

    @cachedproperty
    def num_projects_and_packages_to_review(self):
        """How many translations do we suggest for reviewing?"""
        return len(self.all_projects_and_packages_to_review)

    @property
    def top_projects_and_packages_to_translate(self):
        """Suggest translations for this person to help complete."""
        # Maximum number of translations to list that need the most work
        # done.
        max_urgent_targets = 5
        # Maximum number of translations to list that are almost
        # complete.
        max_almost_complete_targets = 5
        # Length of overall list to display.
        list_length = 10

        fetch = 5 * max_urgent_targets
        urgent = self._getTargetsForTranslation(fetch)
        overall = self._addToTargetsList(
            [], urgent, max_urgent_targets, list_length)

        fetch = 5 * max_almost_complete_targets
        almost_complete = self._getTargetsForTranslation(-fetch)
        overall = self._addToTargetsList(
            overall, almost_complete, max_almost_complete_targets,
            list_length)

        return overall

    to_complete_template = ViewPageTemplateFile(
        '../templates/person-translations-to-complete-table.pt')

    def translations_to_complete_table(self):
        return self.to_complete_template(dict(view=self))

    to_review_template = ViewPageTemplateFile(
        '../templates/person-translations-to-review-table.pt')

    def translations_to_review_table(self):
        return self.to_review_template(dict(view=self))


class PersonTranslationReviewView(PersonTranslationView):
    """View for translation-related Person pages."""

    page_title = "for review"

    def label(self):
        return "Translations for review by %s" % self.context.displayname


class PersonTranslationRelicensingView(LaunchpadFormView):
    """View for Person's translation relicensing page."""
    schema = ITranslationRelicensingAgreementEdit
    field_names = ['allow_relicensing', 'back_to']
    custom_widget(
        'allow_relicensing', LaunchpadRadioWidget, orientation='vertical')
    custom_widget('back_to', TextWidget, visible=False)

    page_title = "Licensing"

    @property
    def label(self):
        return "Translations licensing by %s" % self.context.displayname

    @property
    def initial_values(self):
        """Set the default value for the relicensing radio buttons."""
        translations_person = ITranslationsPerson(self.context)
        # If the person has previously made a choice, we default to that.
        # Otherwise, we default to BSD, because that's what we'd prefer.
        if translations_person.translations_relicensing_agreement == False:
            default = TranslationRelicensingAgreementOptions.REMOVE
        else:
            default = TranslationRelicensingAgreementOptions.BSD
        return {
            "allow_relicensing": default,
            "back_to": self.request.get('back_to'),
            }

    @property
    def relicensing_url(self):
        """Return an URL for this view."""
        return canonical_url(self.context, view_name='+licensing',
                             rootsite='translations')

    @property
    def cancel_url(self):
        """Escape to the person's main Translations page."""
        return canonical_url(self.context, rootsite='translations')

    def getSafeRedirectURL(self, url):
        """Successful form submission should send to this URL."""
        if url and url.startswith(self.request.getApplicationURL()):
            return url
        else:
            return canonical_url(self.context, rootsite='translations')

    @action(_("Confirm"), name="submit")
    def submit_action(self, action, data):
        """Store person's decision about translations relicensing.

        The user's decision is stored through
        `ITranslationsPerson.translations_relicensing_agreement`
        which is backed by the TranslationRelicensingAgreement table.
        """
        translations_person = ITranslationsPerson(self.context)
        allow_relicensing = data['allow_relicensing']
        if allow_relicensing == TranslationRelicensingAgreementOptions.BSD:
            translations_person.translations_relicensing_agreement = True
            self.request.response.addInfoNotification(_(
                "Thank you for BSD-licensing your translations."))
        elif (allow_relicensing ==
            TranslationRelicensingAgreementOptions.REMOVE):
            translations_person.translations_relicensing_agreement = False
            self.request.response.addInfoNotification(_(
                "We respect your choice. "
                "Thanks for trying out Launchpad Translations."))
        else:
            raise AssertionError(
                "Unknown allow_relicensing value: %r" % allow_relicensing)
        self.next_url = self.getSafeRedirectURL(data['back_to'])


class TranslationActivityView(LaunchpadView):
    """View for person's activity listing."""

    _pofiletranslator_cache = None

    page_title = "Activity"

    @property
    def label(self):
        return "Translation activity by %s" % self.context.displayname

    @cachedproperty
    def batchnav(self):
        """Iterate over person's translation_history."""
        translations_person = ITranslationsPerson(self.context)
        batchnav = BatchNavigator(
            translations_person.translation_history, self.request)

        pofiletranslatorset = getUtility(IPOFileTranslatorSet)
        batch = batchnav.currentBatch()
        self._pofiletranslator_cache = (
            pofiletranslatorset.prefetchPOFileTranslatorRelations(batch))

        return batchnav

    def composeURL(self, pofile):
        return compose_pofile_filter_url(pofile, self.context)
