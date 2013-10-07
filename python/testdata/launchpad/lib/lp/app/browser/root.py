# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Browser code for the Launchpad root page."""

__metaclass__ = type
__all__ = [
    'LaunchpadRootIndexView',
    'LaunchpadSearchView',
    ]


import re
import time

import feedparser
from lazr.batchnavigator.z3batching import batch
from zope.component import getUtility
from zope.formlib.interfaces import ConversionError
from zope.interface import Interface
from zope.schema import TextLine
from zope.schema.interfaces import TooLong
from zope.schema.vocabulary import getVocabularyRegistry

from lp import _
from lp.answers.interfaces.questioncollection import IQuestionSet
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    safe_action,
    )
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.name import sanitize_name
from lp.blueprints.interfaces.specification import ISpecificationSet
from lp.bugs.interfaces.bug import IBugSet
from lp.code.interfaces.branchcollection import IAllBranches
from lp.registry.browser.announcement import HasAnnouncementsView
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.features import getFeatureFlag
from lp.services.googlesearch.interfaces import (
    GoogleResponseError,
    ISearchService,
    )
from lp.services.memcache.interfaces import IMemcacheClient
from lp.services.propertycache import cachedproperty
from lp.services.statistics.interfaces.statistic import ILaunchpadStatisticSet
from lp.services.timeout import urlfetch
from lp.services.webapp import LaunchpadView
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.vhosts import allvhosts


shipit_faq_url = 'http://www.ubuntu.com/getubuntu/shipit-faq'


class LaunchpadRootIndexView(HasAnnouncementsView, LaunchpadView):
    """An view for the default view of the LaunchpadRoot."""

    page_title = 'Launchpad'
    featured_projects = []
    featured_projects_top = None

    # Used by the footer to display the lp-arcana section.
    is_root_page = True
    has_watermark = False

    @staticmethod
    def _get_day_of_year():
        """Calculate the number of the current day.

        This method gets overridden in tests to make the selection of the
        top featured project deterministic.
        """
        return time.gmtime()[7]

    def initialize(self):
        """Set up featured projects list and the top featured project."""
        super(LaunchpadRootIndexView, self).initialize()
        # The maximum number of projects to be displayed as defined by the
        # number of items plus one top featured project.
        self.featured_projects = list(
            getUtility(IPillarNameSet).featured_projects)
        self._setFeaturedProjectsTop()

    def _setFeaturedProjectsTop(self):
        """Set the top featured project and remove it from the list."""
        project_count = len(self.featured_projects)
        if project_count > 0:
            top_project = self._get_day_of_year() % project_count
            self.featured_projects_top = self.featured_projects.pop(
                top_project)

    @cachedproperty
    def apphomes(self):
        return {
            'answers': canonical_url(self.context, rootsite='answers'),
            'blueprints': canonical_url(self.context, rootsite='blueprints'),
            'bugs': canonical_url(self.context, rootsite='bugs'),
            'code': canonical_url(self.context, rootsite='code'),
            'translations': canonical_url(self.context,
                                          rootsite='translations'),
            'ubuntu': canonical_url(
                getUtility(ILaunchpadCelebrities).ubuntu),
            }

    @property
    def branch_count(self):
        """The total branch count of public branches in all of Launchpad."""
        return getUtility(IAllBranches).visibleByUser(None).count()

    @property
    def bug_count(self):
        """The total bug count in all of Launchpad."""
        return getUtility(ILaunchpadStatisticSet).value('bug_count')

    @property
    def project_count(self):
        """The total project count in all of Launchpad."""
        return getUtility(IProductSet).count_all()

    @property
    def translation_count(self):
        """The total count of translatable strings in all of Launchpad """
        return getUtility(ILaunchpadStatisticSet).value('pomsgid_count')

    @property
    def blueprint_count(self):
        """The total blueprint count in all of Launchpad."""
        return getUtility(ISpecificationSet).specificationCount(self.user)

    @property
    def answer_count(self):
        """The total blueprint count in all of Launchpad."""
        return getUtility(ILaunchpadStatisticSet).value('question_count')

    @property
    def show_whatslaunchpad(self):
        """True if introduction to Launchpad should be displayed.

        Shown when not logged in or if blog is disabled.
        """
        return self.user is None or not getFeatureFlag("app.root_blog.enabled")

    def getRecentBlogPosts(self):
        """Return the parsed feed of the most recent blog posts.

        It returns a list of dict with keys title, description, link and date.

        The date is formatted and the description which may contain HTML is
        sanitized.

        The number of blog posts to display is controlled through
        launchpad.homepage_recent_posts_count. The posts are fetched
        from the feed specified in launchpad.homepage_recent_posts_feed.

        FeedParser takes care of sanitizing the HTML contained in the feed.
        """
        key = '%s:homepage-blog-posts' % config.instance_name
        cached_data = getUtility(IMemcacheClient).get(key)
        if cached_data:
            return cached_data
        try:
            # Use urlfetch which supports timeout
            data = urlfetch(config.launchpad.homepage_recent_posts_feed)
        except IOError:
            return []
        feed = feedparser.parse(data)
        posts = []
        max_count = config.launchpad.homepage_recent_posts_count
        # FeedParser takes care of HTML sanitisation.
        for entry in feed.entries[:max_count]:
            posts.append({
                'title': entry.title,
                'description': entry.description,
                'link': entry.link,
                'date': time.strftime('%d %b %Y', entry.updated_parsed),
                })
        # The cache of posts expires after an hour.
        getUtility(IMemcacheClient).set(key, posts, time=3600)
        return posts


class LaunchpadSearchFormView(LaunchpadView):
    """A view to display the global search form in any page."""
    id_suffix = '-secondary'
    text = None
    focusedElementScript = None
    form_wide_errors = None
    errors = None
    error_count = None
    error = None
    error_class = None

    @property
    def rooturl(self):
        """Return the site's root url."""
        return allvhosts.configs['mainsite'].rooturl


class LaunchpadPrimarySearchFormView(LaunchpadSearchFormView):
    """A view to display the global search form in the page."""
    id_suffix = ''

    @property
    def text(self):
        """The search text submitted to the context view."""
        return self.context.text

    @property
    def focusedElementScript(self):
        """The context view's focusedElementScript."""
        return self.context.focusedElementScript

    @property
    def form_wide_errors(self):
        """The context view's form_wide_errors."""
        return self.context.form_wide_errors

    @property
    def errors(self):
        """The context view's errors."""
        return self.context.errors

    @property
    def error_count(self):
        """The context view's error_count."""
        return self.context.error_count

    @property
    def error(self):
        """The context view's text field error."""
        return self.context.getFieldError('text')

    @property
    def error_class(self):
        """Return the 'error' if there is an error, or None."""
        if self.error:
            return 'error'
        return None


class ILaunchpadSearch(Interface):
    """The Schema for performing searches across all Launchpad."""

    text = TextLine(
        title=_('Search text'), required=False, max_length=250)


class LaunchpadSearchView(LaunchpadFormView):
    """A view to search for Launchpad pages and objects."""
    schema = ILaunchpadSearch
    field_names = ['text']

    shipit_keywords = set([
        'ubuntu', 'kubuntu', 'edubuntu',
        'ship', 'shipit', 'send', 'get', 'mail', 'free',
        'cd', 'cds', 'dvd', 'dvds', 'disc'])
    shipit_anti_keywords = set([
        'burn', 'burning', 'enable', 'error', 'errors', 'image', 'iso',
        'read', 'rip', 'write'])

    def __init__(self, context, request):
        """Initialize the view.

        Set the state of the search_params and matches.
        """
        super(LaunchpadSearchView, self).__init__(context, request)
        self.has_page_service = True
        self._bug = None
        self._question = None
        self._person_or_team = None
        self._pillar = None
        self._pages = None
        self.search_params = self._getDefaultSearchParams()
        # The Search Action should always run.
        self.request.form['field.actions.search'] = 'Search'

    def _getDefaultSearchParams(self):
        """Return a dict of the search param set to their default state."""
        return {
            'text': None,
            'start': 0,
            }

    def _updateSearchParams(self):
        """Sanitize the search_params and add the BatchNavigator params."""
        if self.search_params['text'] is not None:
            text = self.search_params['text'].strip()
            if text == '':
                self.search_params['text'] = None
            else:
                self.search_params['text'] = text
        request_start = self.request.get('start', self.search_params['start'])
        try:
            start = int(request_start)
        except (ValueError, TypeError):
            return
        self.search_params['start'] = start

    @property
    def text(self):
        """Return the text or None."""
        return self.search_params['text']

    @property
    def start(self):
        """Return the start index of the batch."""
        return self.search_params['start']

    @property
    def page_title(self):
        """Page title."""
        return self.page_heading

    @property
    def page_heading(self):
        """Heading to display above the search results."""
        if self.text is None:
            return 'Search Launchpad'
        else:
            return 'Pages matching "%s" in Launchpad' % self.text

    @property
    def batch_heading(self):
        """Heading to display in the batch navigation."""
        if self.has_exact_matches:
            return ('other page matching "%s"' % self.text,
                    'other pages matching "%s"' % self.text)
        else:
            return ('page matching "%s"' % self.text,
                    'pages matching "%s"' % self.text)

    @property
    def focusedElementScript(self):
        """Focus the first widget when there are no matches."""
        if self.has_matches:
            return None
        return super(LaunchpadSearchView, self).focusedElementScript()

    @property
    def bug(self):
        """Return the bug that matched the terms, or None."""
        return self._bug

    @property
    def question(self):
        """Return the question that matched the terms, or None."""
        return self._question

    @property
    def pillar(self):
        """Return the project that matched the terms, or None."""
        return self._pillar

    @property
    def person_or_team(self):
        """Return the person or team that matched the terms, or None."""
        return self._person_or_team

    @property
    def pages(self):
        """Return the pages that matched the terms, or None."""
        return self._pages

    @property
    def has_shipit(self):
        """Return True is the search text contains shipit keywords."""
        if self.text is None:
            return False
        terms = set(self.text.lower().split())
        anti_matches = self.shipit_anti_keywords.intersection(terms)
        if len(anti_matches) >= 1:
            return False
        matches = self.shipit_keywords.intersection(terms)
        return len(matches) >= 2

    @property
    def has_exact_matches(self):
        """Return True if something exactly matched the search terms."""
        kinds = (self.bug, self.question, self.pillar,
                 self.person_or_team, self.has_shipit)
        return self.containsMatchingKind(kinds)

    @property
    def shipit_faq_url(self):
        """The shipit FAQ URL."""
        return shipit_faq_url

    @property
    def has_matches(self):
        """Return True if something matched the search terms, or False."""
        kinds = (self.bug, self.question, self.pillar,
                 self.person_or_team, self.has_shipit, self.pages)
        return self.containsMatchingKind(kinds)

    @property
    def url(self):
        """Return the requested URL."""
        if 'QUERY_STRING' in self.request:
            query_string = self.request['QUERY_STRING']
        else:
            query_string = ''
        return self.request.getURL() + '?' + query_string

    def containsMatchingKind(self, kinds):
        """Return True if one of the items in kinds is not None, or False."""
        for kind in kinds:
            if kind is not None and kind is not False:
                return True
        return False

    def validate(self, data):
        """See `LaunchpadFormView`"""
        errors = list(self.errors)
        for error in errors:
            if isinstance(error, ConversionError):
                self.setFieldError(
                    'text', 'Can not convert your search term.')
            elif isinstance(error, unicode):
                continue
            elif (error.field_name == 'text'
                and isinstance(error.errors, TooLong)):
                self.setFieldError(
                    'text', 'The search text cannot exceed 250 characters.')

    @safe_action
    @action(u'Search', name='search')
    def search_action(self, action, data):
        """The Action executed when the user uses the search button.

        Saves the user submitted search parameters in an instance
        attribute.
        """
        self.search_params.update(**data)
        self._updateSearchParams()
        if self.text is None:
            return

        if self.start == 0:
            numeric_token = self._getNumericToken(self.text)
            if numeric_token is not None:
                try:
                    bug = getUtility(IBugSet).get(numeric_token)
                    if check_permission("launchpad.View", bug):
                        self._bug = bug
                except NotFoundError:
                    # Let self._bug remain None.
                    pass
                self._question = getUtility(IQuestionSet).get(numeric_token)

            name_token = self._getNameToken(self.text)
            if name_token is not None:
                self._person_or_team = self._getPersonOrTeam(name_token)
                self._pillar = self._getDistributionOrProductOrProjectGroup(
                    name_token)

        self._pages = self.searchPages(self.text, start=self.start)

    def _getNumericToken(self, text):
        """Return the first group of numbers in the search text, or None."""
        numeric_pattern = re.compile(r'(\d+)')
        match = numeric_pattern.search(text)
        if match is None:
            return None
        return match.group(1)

    def _getNameToken(self, text):
        """Return the search text as a Launchpad name.

        Launchpad names may contain ^[a-z0-9][a-z0-9\+\.\-]+$.
        See `valid_name_pattern`.
        """
        hypen_pattern = re.compile(r'[ _]')
        name = hypen_pattern.sub('-', text.strip().lower())
        return sanitize_name(name)

    def _getPersonOrTeam(self, name):
        """Return the matching active person or team."""
        person_or_team = getUtility(IPersonSet).getByName(name)
        if (person_or_team is not None
            and person_or_team.is_valid_person_or_team
            and check_permission('launchpad.View', person_or_team)):
            return person_or_team
        return None

    def _getDistributionOrProductOrProjectGroup(self, name):
        """Return the matching distribution, product or project, or None."""
        vocabulary_registry = getVocabularyRegistry()
        vocab = vocabulary_registry.get(
            None, 'DistributionOrProductOrProjectGroup')
        try:
            return vocab.getTermByToken(name).value
        except LookupError:
            return None

    def searchPages(self, query_terms, start=0):
        """Return the up to 20 pages that match the query_terms, or None.

        :param query_terms: The unescaped terms to query Google.
        :param start: The index of the page that starts the set of pages.
        :return: A GooglBatchNavigator or None.
        """
        if query_terms in [None, '']:
            return None
        google_search = getUtility(ISearchService)
        try:
            page_matches = google_search.search(
                terms=query_terms, start=start)
        except GoogleResponseError:
            # There was a connectivity or Google service issue that means
            # there is no data available at this moment.
            self.has_page_service = False
            return None
        if len(page_matches) == 0:
            return None
        navigator = GoogleBatchNavigator(
            page_matches, self.request, start=start)
        navigator.setHeadings(*self.batch_heading)
        return navigator


class WindowedList:
    """A list that contains a subset of items (a window) of a virtual list."""

    def __init__(self, window, start, total):
        """Create a WindowedList from a smaller list.

        :param window: The list with real items.
        :param start: An int, the list's starting index in the virtual list.
        :param total: An int, the total number of items in the virtual list.
        """
        self._window = window
        self._start = start
        self._total = total
        self._end = start + len(window)

    def __len__(self):
        """Return the length of the virtual list."""
        return self._total

    def __getitem__(self, key):
        """Return the key item or None if key belongs to the virtual list."""
        # When the key is a slice, return a list of items.
        if isinstance(key, (tuple, slice)):
            if isinstance(key, (slice)):
                indices = key.indices(len(self))
            else:
                indices = key
            return [self[index] for index in range(*indices)]
        # If the index belongs to the window return a real item.
        if key >= self._start and key < self._end:
            window_index = key - self._start
            return self._window[window_index]
        # Otherwise the index belongs to the virtual list.
        return None

    def __iter__(self):
        """Yield each item, or None if the index is virtual."""
        for index in range(0, self._total):
            yield self[index]


class WindowedListBatch(batch._Batch):
    """A batch class that does not include None objects when iterating."""

    def __iter__(self):
        """Iterate over objects that are not None."""
        for item in super(WindowedListBatch, self).__iter__():
            if item is not None:
                # Never yield None
                yield item

    def endNumber(self):
        """Return the end index of the batch, not including None objects."""
        return self.start + len(self.list._window)


class GoogleBatchNavigator(BatchNavigator):
    """A batch navigator with a fixed size of 20 items per batch."""

    _batch_factory = WindowedListBatch
    # Searches generally don't show the 'Last' link when there is a
    # good chance of getting over 100,000 results.
    show_last_link = False

    singular_heading = 'page'
    plural_heading = 'pages'

    def __init__(self, results, request, start=0, size=20, callback=None,
                 transient_parameters=None, force_start=False,
                 range_factory=None):
        """See `BatchNavigator`.

        :param results: A `PageMatches` object that contains the matching
            pages to iterate over.
        :param request: An `IBrowserRequest` that contains the form
            parameters.
        :param start: an int that represents the start of the current batch.
        :param size: The batch size is fixed to 20, The param is not used.
        :param callback: Not used.
        """
        results = WindowedList(results, start, results.total)
        super(GoogleBatchNavigator, self).__init__(results, request,
            start=start, size=size, callback=callback,
            transient_parameters=transient_parameters,
            force_start=force_start, range_factory=range_factory)

    def determineSize(self, size, batch_params_source):
        # Force the default and users requested sizes to 20.
        self.default_size = 20
        return 20
