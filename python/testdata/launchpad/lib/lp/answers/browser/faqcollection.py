# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IFAQCollection browser views."""

__metaclass__ = type

__all__ = [
    'FAQCollectionMenu',
    'SearchFAQsView',
    ]

from urllib import urlencode

from lp import _
from lp.answers.enums import (
    QUESTION_STATUS_DEFAULT_SEARCH,
    QuestionSort,
    )
from lp.answers.interfaces.faqcollection import (
    FAQSort,
    IFAQCollection,
    ISearchFAQsForm,
    )
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    safe_action,
    )
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.menu import enabled_with_permission


class FAQCollectionMenu(NavigationMenu):
    """Base menu definition for `IFAQCollection`."""

    usedfor = IFAQCollection
    facet = 'answers'
    links = ['list_all', 'create_faq']

    def list_all(self):
        """Return a Link to list all FAQs."""
        # We adapt to IFAQCollection so that the link can be used
        # on objects which don't provide `IFAQCollection` directly, but for
        # which an adapter exists that gives the proper context.
        collection = IFAQCollection(self.context)
        url = canonical_url(collection, rootsite='answers') + '/+faqs'
        return Link(url, 'All FAQs', icon='info')

    @enabled_with_permission('launchpad.Append')
    def create_faq(self):
        """Return a Link to create a new FAQ."""
        collection = IFAQCollection(self.context)
        if IProjectGroup.providedBy(self.context):
            url = ''
            enabled = False
        else:
            url = canonical_url(
                collection, view_name='+createfaq', rootsite='answers')
            enabled = True
        return Link(url, 'Create a new FAQ', icon='add', enabled=enabled)


class SearchFAQsView(LaunchpadFormView):
    """View to list and search FAQs."""

    schema = ISearchFAQsForm

    # This attribute contains the search_text to use.
    search_text = None

    # This attribute is updated to the number of matching questions when
    # the user does a search.
    matching_questions_count = 0

    @property
    def page_title(self):
        """Return the page_title that should be used for the listing."""
        replacements = dict(
            displayname=self.context.displayname,
            search_text=self.search_text)
        if self.search_text:
            return _(u'FAQs matching \u201c${search_text}\u201d for '
                     u'$displayname', mapping=replacements)
        else:
            return _('FAQs for $displayname', mapping=replacements)

    label = page_title

    @property
    def empty_listing_message(self):
        """Return the message to render when there are no FAQs to display."""
        replacements = dict(
            displayname=self.context.displayname,
            search_text=self.search_text)
        if self.search_text:
            return _(u'There are no FAQs for $displayname matching '
                     u'\u201c${search_text}\u201d.', mapping=replacements)
        else:
            return _('There are no FAQs for $displayname.',
                     mapping=replacements)

    def getMatchingFAQs(self):
        """Return a BatchNavigator of the matching FAQs."""
        faqs = self.context.searchFAQs(search_text=self.search_text)
        return BatchNavigator(faqs, self.request)

    @property
    def portlet_action(self):
        """The action URL of the portlet form."""
        return canonical_url(
            self.context, view_name='+faqs', rootsite='answers')

    @cachedproperty
    def latest_faqs(self):
        """Return the latest faqs created for this target.

        This is used by the +portlet-listfaqs view.
        """
        quantity = 5
        faqs = self.context.searchFAQs(
            search_text=self.search_text, sort=FAQSort.NEWEST_FIRST)
        return list(faqs[:quantity])

    @safe_action
    @action(_('Search'), name='search')
    def search_action(self, action, data):
        """Filter the search results by keywords."""
        self.search_text = data.get('search_text', None)
        if self.search_text:
            matching_questions = self.context.searchQuestions(
                search_text=self.search_text)
            self.matching_questions_count = matching_questions.count()

    @property
    def matching_questions_url(self):
        """Return the URL to the questions matching the same keywords."""
        return canonical_url(self.context) + '/+questions?' + urlencode(
            {'field.status': [
                status.title for status in QUESTION_STATUS_DEFAULT_SEARCH],
             'field.search_text': self.search_text,
             'field.actions.search': 'Search',
             'field.sort': QuestionSort.RELEVANCY.title,
             'field.language-empty-marker': 1}, doseq=True)
