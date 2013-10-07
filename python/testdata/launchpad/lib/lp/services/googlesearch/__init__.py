# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for searching and working with results."""

__metaclass__ = type

__all__ = [
    'GoogleSearchService',
    'PageMatch',
    'PageMatches',
    ]

import urllib
import urllib2
from urlparse import (
    parse_qsl,
    urlunparse,
    )
import xml.etree.cElementTree as ET

from lazr.restful.utils import get_current_browser_request
from lazr.uri import URI
from zope.interface import implements

from lp.services.config import config
from lp.services.googlesearch.interfaces import (
    GoogleResponseError,
    GoogleWrongGSPVersion,
    ISearchResult,
    ISearchResults,
    ISearchService,
    )
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.services.timeout import TimeoutError
from lp.services.webapp import urlparse


class PageMatch:
    """See `ISearchResult`.

    A search result that represents a web page.
    """
    implements(ISearchResult)

    @property
    def url_rewrite_exceptions(self):
        """A list of launchpad.net URLs that must not be rewritten.

        Configured in config.google.url_rewrite_exceptions.
        """
        return config.google.url_rewrite_exceptions.split()

    @property
    def url_rewrite_scheme(self):
        """The URL scheme used in rewritten URLs.

        Configured in config.vhosts.use_https.
        """
        if config.vhosts.use_https:
            return 'https'
        else:
            return 'http'

    @property
    def url_rewrite_hostname(self):
        """The network location used in rewritten URLs.

        Configured in config.vhost.mainsite.hostname.
        """
        return config.vhost.mainsite.hostname

    def __init__(self, title, url, summary):
        """initialize a PageMatch.

        :param title: A string. The title of the item.
        :param url: A string. The full URL of the item.
        :param summary: A string. A summary of the item.
        """
        self.title = title
        self.summary = summary
        self.url = self._rewrite_url(url)

    def _sanitize_query_string(self, url):
        """Escapes invalid urls."""
        parts = urlparse(url)
        querydata = parse_qsl(parts.query)
        querystring = urllib.urlencode(querydata)
        urldata = list(parts)
        urldata[-2] = querystring
        return urlunparse(urldata)

    def _strip_trailing_slash(self, url):
        """Return the url without a trailing slash."""
        uri = URI(url).ensureNoSlash()
        return str(uri)

    def _rewrite_url(self, url):
        """Rewrite the url to the local environment.

        Links with launchpad.net are rewritten to the local hostname,
        except if the domain matches a domain in the url_rewrite_exceptions.
        property.

        :param url: A URL str that may be rewritten to the local
            launchpad environment.
        :return: A URL str.
        """
        url = self._sanitize_query_string(url)
        if self.url_rewrite_hostname == 'launchpad.net':
            # Do not rewrite the url is the hostname is the public hostname.
            return self._strip_trailing_slash(url)
        parts = urlparse(url)
        for netloc in self.url_rewrite_exceptions:
            # The network location is parts[1] in the tuple.
            if netloc in parts[1]:
                return url
        local_scheme = self.url_rewrite_scheme
        local_hostname = parts[1].replace(
            'launchpad.net', self.url_rewrite_hostname)
        local_parts = tuple(
            [local_scheme] + [local_hostname] + list(parts[2:]))
        url = urlunparse(local_parts)
        return self._strip_trailing_slash(url)


class PageMatches:
    """See `ISearchResults`.

    A collection of PageMatches.
    """
    implements(ISearchResults)

    def __init__(self, matches, start, total):
        """initialize a PageMatches.

        :param matches: A list of `PageMatch` objects.
        :param start: The index of the first item in the collection relative
            to the total number of items.
        :param total: The total number of items that matched a search.
        """
        self._matches = matches
        self.start = start
        self.total = total

    def __len__(self):
        """See `ISearchResults`."""
        return len(self._matches)

    def __getitem__(self, index):
        """See `ISearchResults`."""
        return self._matches[index]

    def __iter__(self):
        """See `ISearchResults`."""
        return iter(self._matches)


class GoogleSearchService:
    """See `ISearchService`.

    A search service that search Google for launchpad.net pages.
    """
    implements(ISearchService)

    _default_values = {
        'client': 'google-csbe',
        'cx': None,
        'ie': 'utf8',
        'num': 20,
        'oe': 'utf8',
        'output': 'xml_no_dtd',
        'start': 0,
        'q': None,
        }

    @property
    def client_id(self):
        """The client-id issued by Google.

        Google requires that each client of the Google Search Engine
        service to pass its id as a parameter in the request URL.
        """
        return config.google.client_id

    @property
    def site(self):
        """The URL to the Google Search Engine service.

        The URL is probably http://www.google.com/search.
        """
        return config.google.site

    def search(self, terms, start=0):
        """See `ISearchService`.

        The config.google.client_id is used as Google client-id in the
        search request. Search returns 20 or fewer results for each query.
        For terms that match more than 20 results, the start param can be
        used over multiple queries to get successive sets of results.

        :return: `ISearchResults` (PageMatches).
        :raise: `GoogleWrongGSPVersion` if the xml cannot be parsed.
        """
        search_url = self.create_search_url(terms, start=start)
        from lp.services.timeout import urlfetch
        request = get_current_browser_request()
        timeline = get_request_timeline(request)
        action = timeline.start("google-search-api", search_url)
        try:
            gsp_xml = urlfetch(search_url)
        except (TimeoutError, urllib2.HTTPError, urllib2.URLError) as error:
            # Google search service errors are not code errors. Let the
            # call site choose to handle the unavailable service.
            raise GoogleResponseError(
                "The response errored: %s" % str(error))
        finally:
            action.finish()
        page_matches = self._parse_google_search_protocol(gsp_xml)
        return page_matches

    def _checkParameter(self, name, value, is_int=False):
        """Check that a parameter value is not None or an empty string."""
        if value in (None, ''):
            raise AssertionError("Missing value for parameter '%s'." % name)
        if is_int:
            try:
                int(value)
            except ValueError:
                raise AssertionError(
                    "Value for parameter '%s' is not an int." % name)

    def create_search_url(self, terms, start=0):
        """Return a Google search url."""
        self._checkParameter('q', terms)
        self._checkParameter('start', start, is_int=True)
        self._checkParameter('cx', self.client_id)
        safe_terms = urllib.quote_plus(terms.encode('utf8'))
        search_params = dict(self._default_values)
        search_params['q'] = safe_terms
        search_params['start'] = start
        search_params['cx'] = self.client_id
        search_param_list = []
        for name in sorted(search_params):
            value = search_params[name]
            search_param_list.append('%s=%s' % (name, value))
        query_string = '&'.join(search_param_list)
        return self.site + '?' + query_string

    def _getElementsByAttributeValue(self, doc, path, name, value):
        """Return a list of elements whose named attribute matches the value.

        The cElementTree implementation does not support attribute selection
        (@) or conditional expressions (./PARAM[@name = 'start']).

        :param doc: An ElementTree of an XML document.
        :param path: A string path to match the first element.
        :param name: The attribute name to check.
        :param value: The string value of the named attribute.
        """
        elements = doc.findall(path)
        return [element for element in elements
                if element.get(name) == value]

    def _getElementByAttributeValue(self, doc, path, name, value):
        """Return the first element whose named attribute matches the value.

        :param doc: An ElementTree of an XML document.
        :param path: A string path to match an element.
        :param name: The attribute name to check.
        :param value: The string value of the named attribute.
        """
        return self._getElementsByAttributeValue(doc, path, name, value)[0]

    def _parse_google_search_protocol(self, gsp_xml):
        """Return a `PageMatches` object.

        :param gsp_xml: A string that should be Google Search Protocol
            version 3.2 XML. There is no guarantee that other GSP versions
            can be parsed.
        :return: `ISearchResults` (PageMatches).
        :raise: `GoogleResponseError` if the xml is incomplete.
        :raise: `GoogleWrongGSPVersion` if the xml cannot be parsed.
        """
        try:
            gsp_doc = ET.fromstring(gsp_xml)
            start_param = self._getElementByAttributeValue(
                gsp_doc, './PARAM', 'name', 'start')
        except (SyntaxError, IndexError):
            raise GoogleResponseError("The response was incomplete, no xml.")
        try:
            start = int(start_param.get('value'))
        except (AttributeError, ValueError):
            # The datatype is not what PageMatches requires.
            raise GoogleWrongGSPVersion(
                "Could not get the 'start' from the GSP XML response.")
        page_matches = []
        total = 0
        results = gsp_doc.find('RES')
        if results is None:
            # Google did not match any pages. Return an empty PageMatches.
            return PageMatches(page_matches, start, total)

        try:
            total = int(results.find('M').text)
        except (AttributeError, ValueError):
            # The datatype is not what PageMatches requires.
            raise GoogleWrongGSPVersion(
                "Could not get the 'total' from the GSP XML response.")
        if total < 0:
            # See bug 683115.
            total = 0
        for result in results.findall('R'):
            url_tag = result.find('U')
            title_tag = result.find('T')
            summary_tag = result.find('S')
            if None in (url_tag, title_tag, summary_tag):
                # Google indexed a bad page, or the page may be marked for
                # removal from the index. We should not include this.
                continue
            title = title_tag.text
            url = url_tag.text
            summary = summary_tag.text
            if None in (url, title, summary):
                # There is not enough data to create a PageMatch object.
                # This can be caused by an empty title or summary which
                # has been observed for pages that are from vhosts that
                # should not be indexed.
                continue
            summary = summary.replace('<br>', '')
            page_matches.append(PageMatch(title, url, summary))
        if len(page_matches) == 0 and total > 20:
            # No viable page matches could be found in the set and there
            # are more possible matches; the XML may be the wrong version.
            raise GoogleWrongGSPVersion(
                "Could not get any PageMatches from the GSP XML response.")
        return PageMatches(page_matches, start, total)
