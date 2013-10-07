# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing infrastructure for page tests."""

__metaclass__ = type

from datetime import datetime
import doctest
import os
import pdb
import pprint
import re
import unittest
from urlparse import urljoin

from BeautifulSoup import (
    BeautifulSoup,
    CData,
    Comment,
    Declaration,
    NavigableString,
    PageElement,
    ProcessingInstruction,
    SoupStrainer,
    Tag,
    )
from contrib.oauth import (
    OAuthConsumer,
    OAuthRequest,
    OAuthSignatureMethod_PLAINTEXT,
    OAuthToken,
    )
from lazr.restful.testing.webservice import WebServiceCaller
import transaction
from zope.app.testing.functional import (
    HTTPCaller,
    SimpleCookie,
    )
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy
from zope.session.interfaces import ISession
from zope.testbrowser.testing import Browser

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.errors import NameAlreadyTaken
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.services.config import config
from lp.services.oauth.interfaces import (
    IOAuthConsumerSet,
    OAUTH_REALM,
    )
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import OAuthPermission
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.services.webapp.url import urlsplit
from lp.testing import (
    ANONYMOUS,
    launchpadlib_for,
    login,
    login_person,
    logout,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import PageTestLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    stop,
    )


class UnstickyCookieHTTPCaller(HTTPCaller):
    """HTTPCaller subclass that do not carry cookies across requests.

    HTTPCaller propogates cookies between subsequent requests.
    This is a nice feature, except it triggers a bug in Launchpad where
    sending both Basic Auth and cookie credentials raises an exception
    (Bug 39881).
    """

    def __init__(self, *args, **kw):
        if kw.get('debug'):
            self._debug = True
            del kw['debug']
        else:
            self._debug = False
        HTTPCaller.__init__(self, *args, **kw)

    def __call__(self, *args, **kw):
        if self._debug:
            pdb.set_trace()
        try:
            return HTTPCaller.__call__(self, *args, **kw)
        finally:
            self.resetCookies()

    def chooseRequestClass(self, method, path, environment):
        """See `HTTPCaller`.

        This version adds the 'PATH_INFO' variable to the environment,
        because some of our factories expects it.
        """
        if 'PATH_INFO' not in environment:
            environment = dict(environment)
            environment['PATH_INFO'] = path
        return HTTPCaller.chooseRequestClass(self, method, path, environment)

    def resetCookies(self):
        self.cookies = SimpleCookie()


class LaunchpadWebServiceCaller(WebServiceCaller):
    """A class for making calls to Launchpad web services."""

    def __init__(self, oauth_consumer_key=None, oauth_access_key=None,
                 handle_errors=True, domain='api.launchpad.dev',
                 protocol='http'):
        """Create a LaunchpadWebServiceCaller.
        :param oauth_consumer_key: The OAuth consumer key to use.
        :param oauth_access_key: The OAuth access key to use for the request.
        :param handle_errors: Should errors raise exception or be handled by
            the publisher. Default is to let the publisher handle them.

        Other parameters are passed to the HTTPCaller used to make the calls.
        """
        if oauth_consumer_key is not None and oauth_access_key is not None:
            login(ANONYMOUS)
            consumers = getUtility(IOAuthConsumerSet)
            self.consumer = consumers.getByKey(oauth_consumer_key)
            if oauth_access_key == '':
                # The client wants to make an anonymous request.
                self.access_token = OAuthToken(oauth_access_key, '')
                if self.consumer is None:
                    # The client is trying to make an anonymous
                    # request with a previously unknown consumer. This
                    # is fine: we manually create a "fake"
                    # OAuthConsumer (it's "fake" because it's not
                    # really an IOAuthConsumer as returned by
                    # IOAuthConsumerSet.getByKey) to be used in the
                    # requests we make.
                    self.consumer = OAuthConsumer(oauth_consumer_key, '')
            else:
                if self.consumer is None:
                    # Requests using this caller will be rejected by
                    # the server, but we have a test that verifies
                    # such requests _are_ rejected, so we'll create a
                    # fake OAuthConsumer object.
                    self.consumer = OAuthConsumer(oauth_consumer_key, '')
                    self.access_token = OAuthToken(oauth_access_key, '')
                else:
                    # The client wants to make an authorized request
                    # using a recognized consumer key.
                    self.access_token = self.consumer.getAccessToken(
                        oauth_access_key)
            logout()
        else:
            self.consumer = None
            self.access_token = None

        self.handle_errors = handle_errors
        WebServiceCaller.__init__(self, handle_errors, domain, protocol)

    default_api_version = "beta"

    def addHeadersTo(self, full_url, full_headers):
        if self.consumer is not None and self.access_token is not None:
            request = OAuthRequest.from_consumer_and_token(
                self.consumer, self.access_token, http_url=full_url)
            request.sign_request(
                OAuthSignatureMethod_PLAINTEXT(), self.consumer,
                self.access_token)
            full_headers.update(request.to_header(OAUTH_REALM))
        if not self.handle_errors:
            full_headers['X_Zope_handle_errors'] = 'False'


def extract_url_parameter(url, parameter):
    """Extract parameter and its value from a URL.

    Use this if your test needs to inspect a parameter value embedded in
    a URL, but doesn't really care what the rest of the URL looks like
    or how the parameters are ordered.
    """
    scheme, host, path, query, fragment = urlsplit(url)
    args = query.split('&')
    for arg in args:
        key, value = arg.split('=')
        if key == parameter:
            return arg
    return None


class DuplicateIdError(Exception):
    """Raised by find_tag_by_id if more than one element has the given id."""


def find_tag_by_id(content, id):
    """Find and return the tag with the given ID"""
    if isinstance(content, PageElement):
        elements_with_id = content.findAll(True, {'id': id})
    else:
        elements_with_id = [
            tag for tag in BeautifulSoup(
                content, parseOnlyThese=SoupStrainer(id=id),
                fromEncoding='utf-8')]
    if len(elements_with_id) == 0:
        return None
    elif len(elements_with_id) == 1:
        return elements_with_id[0]
    else:
        raise DuplicateIdError(
            'Found %d elements with id %r' % (len(elements_with_id), id))


def first_tag_by_class(content, class_):
    """Find and return the first tag matching the given class(es)"""
    return find_tags_by_class(content, class_, True)


def find_tags_by_class(content, class_, only_first=False):
    """Find and return one or more tags matching the given class(es)"""

    match_classes = set(class_.split())

    def class_matcher(value):
        if value is None:
            return False
        classes = set(value.split())
        return match_classes.issubset(classes)
    soup = BeautifulSoup(
        content, parseOnlyThese=SoupStrainer(attrs={'class': class_matcher}),
        fromEncoding='utf-8')
    if only_first:
        find = BeautifulSoup.find
    else:
        find = BeautifulSoup.findAll
    return find(soup, attrs={'class': class_matcher})


def find_portlet(content, name):
    """Find and return the portlet with the given title. Sequences of
    whitespace are considered equivalent to one space, and beginning and
    ending whitespace is also ignored, as are non-text elements such as
    images.
    """
    whitespace_re = re.compile('\s+')
    name = whitespace_re.sub(' ', name.strip())
    for portlet in find_tags_by_class(content, 'portlet'):
        if portlet.find('h2'):
            portlet_title = extract_text(portlet.find('h2'))
            if name == whitespace_re.sub(' ', portlet_title.strip()):
                return portlet
    return None


def find_main_content(content):
    """Return the main content of the page, excluding any portlets."""
    main_content = find_tag_by_id(content, 'maincontent')
    if main_content is None:
        # One-column pages don't use a <div id="maincontent">, so we
        # use the next best thing: <div id="container">.
        main_content = find_tag_by_id(content, 'container')
    if main_content is None:
        # Simple pages have neither of these, so as a last resort, we get
        # the page <body>.
        main_content = BeautifulSoup(content, fromEncoding='utf-8').body
    return main_content


def get_feedback_messages(content):
    """Find and return the feedback messages of the page."""
    message_classes = ['message', 'informational message', 'error message',
                       'warning message']
    soup = BeautifulSoup(
        content,
        parseOnlyThese=SoupStrainer(['div', 'p'], {'class': message_classes}),
        fromEncoding='utf-8')
    return [extract_text(tag) for tag in soup]


def print_feedback_messages(content):
    """Print out the feedback messages."""
    for message in get_feedback_messages(content):
        print extract_text(message)


def print_table(content, columns=None, skip_rows=None, sep="\t"):
    """Given a <table> print the content of each row.

    The table is printed using `sep` as the separator.
    :param columns   a list of the column numbers (zero-based) to be included
                     in the output.  If None all columns are printed.
    :param skip_rows a list of row numbers (zero-based) to be skipped.  If
                     None no rows are skipped.
    :param sep       the separator to be used between output items.
    """
    for row_num, row in enumerate(content.findAll('tr')):
        if skip_rows is not None and row_num in skip_rows:
            continue
        row_content = []
        for col_num, item in enumerate(row.findAll('td')):
            if columns is None or col_num in columns:
                row_content.append(extract_text(item))
        if len(row_content) > 0:
            print sep.join(row_content)


def get_radio_button_text_for_field(soup, name):
    """Find the input called field.name, and return an iterable of strings.

    The resulting output will look something like:
    ['(*) A checked option', '( ) An unchecked option']
    """
    buttons = soup.findAll(
        'input', {'name': 'field.%s' % name})
    for button in buttons:
        if button.parent.name == 'label':
            label = extract_text(button.parent)
        else:
            label = extract_text(
                soup.find('label', attrs={'for': button['id']}))
        if button.get('checked', None):
            radio = '(*)'
        else:
            radio = '( )'
        yield "%s %s" % (radio, label)


def print_radio_button_field(content, name):
    """Find the input called field.name, and print a friendly representation.

    The resulting output will look something like:
    (*) A checked option
    ( ) An unchecked option
    """
    main = BeautifulSoup(content, fromEncoding='utf-8')
    for field in get_radio_button_text_for_field(main, name):
        print field


def strip_label(label):
    """Strip surrounding whitespace and non-breaking spaces."""
    return label.replace('\xC2', '').replace('\xA0', '').strip()


IGNORED_ELEMENTS = [Comment, Declaration, ProcessingInstruction]
ELEMENTS_INTRODUCING_NEWLINE = [
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'pre', 'dl',
    'div', 'noscript', 'blockquote', 'form', 'hr', 'table', 'fieldset',
    'address', 'li', 'dt', 'dd', 'th', 'td', 'caption', 'br']


NEWLINES_RE = re.compile(u'\n+')
LEADING_AND_TRAILING_SPACES_RE = re.compile(
    u'(^[ \t]+)|([ \t]$)', re.MULTILINE)
TABS_AND_SPACES_RE = re.compile(u'[ \t]+')
NBSP_RE = re.compile(u'&nbsp;|&#160;')


def extract_link_from_tag(tag, base=None):
    """Return a link from <a> `tag`, optionally considered relative to `base`.

    A `tag` should contain a 'href' attribute, and `base` will commonly
    be extracted from browser.url.
    """
    if not isinstance(tag, PageElement):
        link = BeautifulSoup(tag)
    else:
        link = tag

    href = dict(link.attrs).get('href')
    if base is None:
        return href
    else:
        return urljoin(base, href)


def extract_text(content, extract_image_text=False, skip_tags=None):
    """Return the text stripped of all tags.

    All runs of tabs and spaces are replaced by a single space and runs of
    newlines are replaced by a single newline. Leading and trailing white
    spaces are stripped.
    """
    if skip_tags is None:
        skip_tags = ['script']
    if not isinstance(content, PageElement):
        soup = BeautifulSoup(content, fromEncoding='utf-8')
    else:
        soup = content

    result = []
    nodes = list(soup)
    while nodes:
        node = nodes.pop(0)
        if type(node) in IGNORED_ELEMENTS:
            continue
        elif isinstance(node, CData):
            # CData inherits from NavigableString which inherits from unicode,
            # but contains a __unicode__() method that calls __str__() that
            # wraps the contents in <![CDATA[...]]>.  In Python 2.4, calling
            # unicode(cdata_instance) copies the data directly so the wrapping
            # does not happen.  Python 2.5 changed the unicode() function (C
            # function PyObject_Unicode) to call its operand's __unicode__()
            # method, which ends up calling CData.__str__() and the wrapping
            # happens.  We don't want our test output to have to deal with the
            # <![CDATA[...]]> wrapper.
            #
            # The CData class does not override slicing though, so by slicing
            # node first, we're effectively turning it into a concrete unicode
            # instance, which does not wrap the contents when its
            # __unicode__() is called of course.  We could remove the
            # unicode() call here, but we keep it for consistency and clarity
            # purposes.
            result.append(unicode(node[:]))
        elif isinstance(node, NavigableString):
            result.append(unicode(node))
        else:
            if isinstance(node, Tag):
                # If the node has the class "sortkey" then it is invisible.
                if node.get('class') == 'sortkey':
                    continue
                elif getattr(node, 'name', '') in skip_tags:
                    continue
                if node.name.lower() in ELEMENTS_INTRODUCING_NEWLINE:
                    result.append(u'\n')

                # If extract_image_text is True and the node is an
                # image, try to find its title or alt attributes.
                if extract_image_text and node.name.lower() == 'img':
                    # Title outweighs alt text for the purposes of
                    # pagetest output.
                    if node.get('title') is not None:
                        result.append(node['title'])
                    elif node.get('alt') is not None:
                        result.append(node['alt'])

            # Process this node's children next.
            nodes[0:0] = list(node)

    text = u''.join(result)
    text = NBSP_RE.sub(' ', text)
    text = TABS_AND_SPACES_RE.sub(' ', text)
    text = LEADING_AND_TRAILING_SPACES_RE.sub('', text)
    text = NEWLINES_RE.sub('\n', text)

    # Remove possible newlines at beginning and end.
    return text.strip()


# XXX cprov 2007-02-07: This function seems to be more specific to a
# particular product (soyuz) than the rest. Maybe it belongs to
# somewhere else.
def parse_relationship_section(content):
    """Parser package relationship section.

    See package-relationship-pages.txt and related.
    """
    soup = BeautifulSoup(content, fromEncoding='utf-8')
    section = soup.find('ul')
    whitespace_re = re.compile('\s+')
    if section is None:
        print 'EMPTY SECTION'
        return
    for li in section.findAll('li'):
        if li.a:
            link = li.a
            content = whitespace_re.sub(' ', link.string.strip())
            url = link['href']
            print 'LINK: "%s" -> %s' % (content, url)
        else:
            content = whitespace_re.sub(' ', li.string.strip())
            print 'TEXT: "%s"' % content


def print_action_links(content):
    """Print action menu urls."""
    actions = find_tag_by_id(content, 'actions')
    if actions is None:
        print "No actions portlet"
        return
    entries = actions.findAll('li')
    for entry in entries:
        if entry.a:
            print '%s: %s' % (entry.a.string, entry.a['href'])
        elif entry.strong:
            print entry.strong.string


def print_navigation_links(content):
    """Print navigation menu urls."""
    navigation_links = find_tag_by_id(content, 'navigation-tabs')
    if navigation_links is None:
        print "No navigation links"
        return
    title = navigation_links.find('label')
    if title is not None:
        print '= %s =' % title.string
    entries = navigation_links.findAll(['strong', 'a'])
    for entry in entries:
        try:
            print '%s: %s' % (entry.span.string, entry['href'])
        except KeyError:
            print entry.span.string


def print_portlet_links(content, name, base=None):
    """Print portlet urls.

    This function expects the browser.content as well as the h2 name of the
    portlet. base is optional. It will locate the portlet and print out the
    links. It will report if the portlet cannot be found and will also report
    if there are no links to be found. Unlike the other functions on this
    page, this looks for "a" instead of "li". Example usage:
    --------------
    >>> print_portlet_links(admin_browser.contents,'Milestone milestone3 for
        Ubuntu details')
    Ubuntu: /ubuntu
    Warty: /ubuntu/warty
    --------------
    """

    portlet_contents = find_portlet(content, name)
    if portlet_contents is None:
        print "No portlet found with name:", name
        return
    portlet_links = portlet_contents.findAll('a')
    if len(portlet_links) == 0:
        print "No links were found in the portlet."
        return
    for portlet_link in portlet_links:
        print '%s: %s' % (portlet_link.string,
            extract_link_from_tag(portlet_link, base))


def print_submit_buttons(content):
    """Print the submit button values found in the main content.

    Use this to check that the buttons on a page match your expectations.
    """
    buttons = find_main_content(content).findAll(
        'input', attrs={'class': 'button', 'type': 'submit'})
    if buttons is None:
        print "No buttons found"
    else:
        for button in buttons:
            print button['value']


def print_comments(page):
    """Print the comments on a BugTask index page."""
    main_content = find_main_content(page)
    for comment in main_content('div', 'boardCommentBody'):
        for li_tag in comment('li'):
            print "Attachment: %s" % li_tag.a.renderContents()
        print comment.div.renderContents()
        print "-" * 40


def print_batch_header(soup):
    """Print the batch navigator header."""
    navigation = soup.find('td', {'class': 'batch-navigation-index'})
    print extract_text(navigation).encode('ASCII', 'backslashreplace')


def print_self_link_of_entries(json_body):
    """Print the self_link attribute of each entry in the given JSON body."""
    links = sorted(entry['self_link'] for entry in json_body['entries'])
    for link in links:
        print link


def print_ppa_packages(contents):
    packages = find_tags_by_class(contents, 'archive_package_row')
    for pkg in packages:
        print extract_text(pkg)
    empty_section = find_tag_by_id(contents, 'empty-result')
    if empty_section is not None:
        print extract_text(empty_section)


def print_location(contents):
    """Print the hierarchy, application tabs, and main heading of the page.

    The hierarchy shows your position in the Launchpad structure:
    for example, Ubuntu > 8.04.
    The application tabs represent the major facets of an object:
    for example, Overview, Bugs, and Translations.
    The main heading is the first <h1> element in the page.
    """
    doc = find_tag_by_id(contents, 'document')
    hierarchy = doc.find(attrs={'class': 'breadcrumbs'}).findAll(
        recursive=False)
    segments = [extract_text(step).encode('us-ascii', 'replace')
                for step in hierarchy]

    if len(segments) == 0:
        breadcrumbs = 'None displayed'
    else:
        breadcrumbs = ' > '.join(segments)

    print 'Hierarchy:', breadcrumbs
    print 'Tabs:'
    print_location_apps(contents)
    main_heading = doc.h1
    if main_heading:
        main_heading = extract_text(main_heading).encode(
            'us-ascii', 'replace')
    else:
        main_heading = '(No main heading)'
    print "Main heading: %s" % main_heading


def print_location_apps(contents):
    """Print the application tabs' text and URL."""
    location_apps = find_tag_by_id(contents, 'lp-apps')
    if location_apps is None:
        location_apps = first_tag_by_class(contents, 'watermark-apps-portlet')
        if location_apps is not None:
            location_apps = location_apps.ul.findAll('li')
    else:
        location_apps = location_apps.findAll('span')
    if location_apps is None:
        print "(Application tabs omitted)"
    elif len(location_apps) == 0:
        print "(No application tabs)"
    else:
        for tab in location_apps:
            tab_text = extract_text(tab)
            if tab['class'].find('active') != -1:
                tab_text += ' (selected)'
            if tab.a:
                link = tab.a['href']
            else:
                link = 'not linked'
            print "* %s - %s" % (tab_text, link)


def print_tag_with_id(contents, id):
    """A simple helper to print the extracted text of the tag."""
    tag = find_tag_by_id(contents, id)
    print extract_text(tag)


def print_errors(contents):
    """Print all the errors on the page."""
    errors = find_tags_by_class(contents, 'error')
    error_texts = [extract_text(error) for error in errors]
    for error in error_texts:
        print error


def setupBrowser(auth=None):
    """Create a testbrowser object for use in pagetests.

    :param auth: HTTP authentication string. None for the anonymous user, or a
        string of the form 'Basic email:password' for an authenticated user.
    :return: A `Browser` object.
    """
    browser = Browser()
    # Set up our Browser objects with handleErrors set to False, since
    # that gives a tracebacks instead of unhelpful error messages.
    browser.handleErrors = False
    if auth is not None:
        browser.addHeader("Authorization", auth)
    return browser


def setupBrowserForUser(user):
    """Setup a browser grabbing details from a user.

    :param user: The user to use.
    """
    naked_user = removeSecurityProxy(user)
    email = naked_user.preferredemail.email
    logout()
    return setupBrowser(auth="Basic %s:test" % str(email))


def setupBrowserFreshLogin(user):
    """Create a test browser with a recently logged in user.

    The request is not shared by the browser, so we create
    a session of the test request and set a cookie to reference
    the session in the test browser.
    """
    request = LaunchpadTestRequest()
    session = ISession(request)
    authdata = session['launchpad.authenticateduser']
    authdata['logintime'] = datetime.utcnow()
    namespace = config.launchpad_session.cookie
    cookie = '%s=%s' % (namespace, session.client_id)
    browser = setupBrowserForUser(user)
    browser.addHeader('Cookie', cookie)
    return browser


def safe_canonical_url(*args, **kwargs):
    """Generate a bytestring URL for an object"""
    return str(canonical_url(*args, **kwargs))


def webservice_for_person(person, consumer_key='launchpad-library',
                          permission=OAuthPermission.READ_PUBLIC,
                          context=None):
    """Return a valid LaunchpadWebServiceCaller for the person.

    Use this method to create a way to test the webservice that doesn't depend
    on sample data.
    """
    if person.is_team:
        raise AssertionError('This cannot be used with teams.')
    login(ANONYMOUS)
    oacs = getUtility(IOAuthConsumerSet)
    consumer = oacs.getByKey(consumer_key)
    if consumer is None:
        consumer = oacs.new(consumer_key)
    request_token = consumer.newRequestToken()
    request_token.review(person, permission, context)
    access_token = request_token.createAccessToken()
    logout()
    service = LaunchpadWebServiceCaller(consumer_key, access_token.key)
    service.user = person
    return service


def setupDTCBrowser():
    """Testbrowser configured for Distribution Translations Coordinators.

    Ubuntu is the configured distribution.
    """
    login('foo.bar@canonical.com')
    try:
        dtg_member = LaunchpadObjectFactory().makePerson(
            name='ubuntu-translations-coordinator', email="dtg-member@ex.com")
    except NameAlreadyTaken:
        # We have already created the translations coordinator
        pass
    else:
        dtg = LaunchpadObjectFactory().makeTranslationGroup(
            name="ubuntu-translators",
            title="Ubuntu Translators",
            owner=dtg_member)
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        ubuntu.translationgroup = dtg
    logout()
    return setupBrowser(auth='Basic dtg-member@ex.com:test')


def setupRosettaExpertBrowser():
    """Testbrowser configured for Rosetta Experts."""

    login('admin@canonical.com')
    try:
        rosetta_expert = LaunchpadObjectFactory().makePerson(
            name='rosetta-experts-member', email='re@ex.com')
    except NameAlreadyTaken:
        # We have already created an Rosetta expert
        pass
    else:
        rosetta_experts_team = removeSecurityProxy(getUtility(
            ILaunchpadCelebrities).rosetta_experts)
        rosetta_experts_team.addMember(
            rosetta_expert, reviewer=rosetta_experts_team,
            status=TeamMembershipStatus.ADMIN)
    logout()
    return setupBrowser(auth='Basic re@ex.com:test')


def setUpGlobs(test):
    test.globs['transaction'] = transaction
    test.globs['http'] = UnstickyCookieHTTPCaller()
    test.globs['webservice'] = LaunchpadWebServiceCaller(
        'launchpad-library', 'salgado-change-anything')
    test.globs['public_webservice'] = LaunchpadWebServiceCaller(
        'foobar123451432', 'salgado-read-nonprivate')
    test.globs['user_webservice'] = LaunchpadWebServiceCaller(
        'launchpad-library', 'nopriv-read-nonprivate')
    test.globs['anon_webservice'] = LaunchpadWebServiceCaller(
        'launchpad-library', '')
    test.globs['setupBrowser'] = setupBrowser
    test.globs['setupDTCBrowser'] = setupDTCBrowser
    test.globs['setupRosettaExpertBrowser'] = setupRosettaExpertBrowser
    test.globs['browser'] = setupBrowser()
    test.globs['anon_browser'] = setupBrowser()
    test.globs['user_browser'] = setupBrowser(
        auth="Basic no-priv@canonical.com:test")
    test.globs['admin_browser'] = setupBrowser(
        auth="Basic foo.bar@canonical.com:test")

    test.globs['ANONYMOUS'] = ANONYMOUS
    # If a unicode URL is opened by the test browswer, later navigation
    # raises ValueError exceptions in /usr/lib/python2.4/Cookie.py
    test.globs['canonical_url'] = safe_canonical_url
    test.globs['factory'] = LaunchpadObjectFactory()
    test.globs['find_tag_by_id'] = find_tag_by_id
    test.globs['first_tag_by_class'] = first_tag_by_class
    test.globs['find_tags_by_class'] = find_tags_by_class
    test.globs['find_portlet'] = find_portlet
    test.globs['find_main_content'] = find_main_content
    test.globs['print_feedback_messages'] = print_feedback_messages
    test.globs['print_table'] = print_table
    test.globs['extract_link_from_tag'] = extract_link_from_tag
    test.globs['extract_text'] = extract_text
    test.globs['launchpadlib_for'] = launchpadlib_for
    test.globs['login'] = login
    test.globs['login_person'] = login_person
    test.globs['logout'] = logout
    test.globs['parse_relationship_section'] = parse_relationship_section
    test.globs['pretty'] = pprint.PrettyPrinter(width=1).pformat
    test.globs['print_action_links'] = print_action_links
    test.globs['print_errors'] = print_errors
    test.globs['print_location'] = print_location
    test.globs['print_location_apps'] = print_location_apps
    test.globs['print_navigation_links'] = print_navigation_links
    test.globs['print_portlet_links'] = print_portlet_links
    test.globs['print_comments'] = print_comments
    test.globs['print_submit_buttons'] = print_submit_buttons
    test.globs['print_radio_button_field'] = print_radio_button_field
    test.globs['print_batch_header'] = print_batch_header
    test.globs['print_ppa_packages'] = print_ppa_packages
    test.globs['print_self_link_of_entries'] = print_self_link_of_entries
    test.globs['print_tag_with_id'] = print_tag_with_id
    test.globs['PageTestLayer'] = PageTestLayer
    test.globs['stop'] = stop


# This function name doesn't follow our standard naming conventions,
# but does follow the convention of the other doctest related *Suite()
# functions.

def PageTestSuite(storydir, package=None, setUp=setUpGlobs):
    """Create a suite of page tests for files found in storydir.

    :param storydir: the directory containing the page tests.
    :param package: the package to resolve storydir relative to.  Defaults
        to the caller's package.

    Each file is added as a separate DocFileTest.
    """
    # we need to normalise the package name here, because it
    # involves checking the parent stack frame.  Otherwise the
    # files would be looked up relative to this module.
    package = doctest._normalize_module(package)
    abs_storydir = doctest._module_relative_path(package, storydir)

    filenames = set(
        filename
        for filename in os.listdir(abs_storydir)
        if filename.lower().endswith('.txt'))

    suite = unittest.TestSuite()
    # Add tests to the suite individually.
    if filenames:
        checker = doctest.OutputChecker()
        paths=[os.path.join(storydir, filename)
               for filename in filenames]
        suite.addTest(LayeredDocFileSuite(
            paths=paths,
            package=package, checker=checker, stdout_logging=False,
            layer=PageTestLayer, setUp=setUp))
    return suite
