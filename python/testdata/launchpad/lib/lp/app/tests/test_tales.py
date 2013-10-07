# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""tales.py doctests."""

from datetime import (
    datetime,
    timedelta,
    )

from lxml import html
from pytz import utc
from zope.component import (
    getAdapter,
    getUtility,
    )
from zope.traversing.interfaces import (
    IPathAdapter,
    TraversalError,
    )

from lp.app.browser.tales import (
    DateTimeFormatterAPI,
    format_link,
    ObjectImageDisplayAPI,
    PersonFormatterAPI,
    )
from lp.registry.interfaces.irc import IIrcIDSet
from lp.registry.interfaces.person import PersonVisibility
from lp.services.webapp.authorization import (
    check_permission,
    clear_cache,
    precache_permission_for_objects,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login_person,
    test_tales,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    LaunchpadFunctionalLayer,
    )


def test_requestapi():
    """
    >>> from lp.app.browser.tales import IRequestAPI, RequestAPI
    >>> from lp.registry.interfaces.person import IPerson
    >>> from zope.interface.verify import verifyObject

    >>> class FakePrincipal:
    ...     def __conform__(self, protocol):
    ...         if protocol is IPerson:
    ...             return "This is a person"
    ...

    >>> class FakeApplicationRequest:
    ...    principal = FakePrincipal()
    ...    def getURL(self):
    ...        return 'http://launchpad.dev/'
    ...

    Let's make a fake request, where request.principal is a FakePrincipal
    object.  We can use a class or an instance here.  It really doesn't
    matter.

    >>> request = FakeApplicationRequest()
    >>> adapter = RequestAPI(request)

    >>> verifyObject(IRequestAPI, adapter)
    True

    >>> adapter.person
    'This is a person'

    """


def test_cookie_scope():
    """
    The 'request/lp:cookie_scope' TALES expression returns a string
    that represents the scope parameters necessary for a cookie to be
    available for the entire Launchpad site.  It takes into account
    the request URL and the cookie_domains setting in launchpad.conf.

        >>> from lp.app.browser.tales import RequestAPI
        >>> def cookie_scope(url):
        ...     class FakeRequest:
        ...         def getURL(self):
        ...             return url
        ...     return RequestAPI(FakeRequest()).cookie_scope

    The cookie scope will use the secure attribute if the request was
    secure:

        >>> print cookie_scope('http://launchpad.net/')
        ; Path=/; Domain=.launchpad.net
        >>> print cookie_scope('https://launchpad.net/')
        ; Path=/; Secure; Domain=.launchpad.net

    The domain parameter is omitted for domains that appear to be
    separate from a Launchpad instance:

        >>> print cookie_scope('https://example.com/')
        ; Path=/; Secure
    """


def test_dbschemaapi():
    """
    >>> from lp.app.browser.tales import DBSchemaAPI
    >>> from lp.code.enums import BranchType

    The syntax to get the title is: number/lp:DBSchemaClass

    >>> (str(DBSchemaAPI(1).traverse('BranchType', []))
    ...  == BranchType.HOSTED.title)
    True

    Using an inappropriate number should give a KeyError.

    >>> DBSchemaAPI(99).traverse('BranchType', [])
    Traceback (most recent call last):
    ...
    KeyError: 99

    Using a dbschema name that doesn't exist should give a LocationError

    >>> DBSchemaAPI(99).traverse('NotADBSchema', [])
    Traceback (most recent call last):
    ...
    LocationError: 'NotADBSchema'

    """


class TestPersonFormatterAPI(TestCaseWithFactory):
    """Tests for PersonFormatterAPI"""

    layer = DatabaseFunctionalLayer

    def test_link_display_name_id(self):
        """The link to the user profile page using displayname and id."""
        person = self.factory.makePerson()
        formatter = getAdapter(person, IPathAdapter, 'fmt')
        result = formatter.link_display_name_id(None)
        expected = '<a href="%s" class="sprite person">%s (%s)</a>' % (
            formatter.url(), person.displayname, person.name)
        self.assertEqual(expected, result)


class TestTeamFormatterAPI(TestCaseWithFactory):
    """ Test permissions required to access TeamFormatterAPI methods.

    A user must have launchpad.LimitedView permission to use
    TeamFormatterAPI with private teams.
    """
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestTeamFormatterAPI, self).setUp()
        icon = self.factory.makeLibraryFileAlias(
            filename='smurf.png', content_type='image/png')
        self.team = self.factory.makeTeam(
            name='team', displayname='a team', icon=icon,
            visibility=PersonVisibility.PRIVATE)

    def _make_formatter(self, cache_permission=False):
        # Helper to create the formatter and optionally cache the permission.
        formatter = getAdapter(self.team, IPathAdapter, 'fmt')
        clear_cache()
        request = LaunchpadTestRequest()
        any_person = self.factory.makePerson()
        if cache_permission:
            login_person(any_person, request)
            precache_permission_for_objects(
                request, 'launchpad.LimitedView', [self.team])
        return formatter, request, any_person

    def _tales_value(self, attr, request, path='fmt'):
        # Evaluate the given formatted attribute value on team.
        result = test_tales(
            "team/%s:%s" % (path, attr), team=self.team, request=request)
        return result

    def _test_can_view_attribute_no_login(self, attr, hidden=None):
        # Test attribute access with no login.
        formatter, request, ignore = self._make_formatter()
        value = self._tales_value(attr, request)
        if value is not None:
            if hidden is None:
                hidden = formatter.hidden
            self.assertEqual(hidden, value)

    def _test_can_view_attribute_no_permission(self, attr, hidden=None):
        # Test attribute access when user has no permission.
        formatter, request, any_person = self._make_formatter()
        login_person(any_person, request)
        value = self._tales_value(attr, request)
        if value is not None:
            if hidden is None:
                hidden = formatter.hidden
            self.assertEqual(hidden, value)

    def _test_can_view_attribute_with_permission(self, attr):
        # Test attr access when user has launchpad.LimitedView permission.
        formatter, request, any_person = self._make_formatter(
            cache_permission=True)
        self.assertNotEqual(
            formatter.hidden, self._tales_value(attr, request))

    def _test_can_view_attribute(self, attr, hidden=None):
        # Test the visibility of the given attribute
        self._test_can_view_attribute_no_login(attr, hidden)
        self._test_can_view_attribute_no_permission(attr, hidden)
        self._test_can_view_attribute_with_permission(attr)

    def test_can_view_displayname(self):
        self._test_can_view_attribute('displayname')

    def test_can_view_unique_displayname(self):
        self._test_can_view_attribute('unique_displayname')

    def test_can_view_link(self):
        self._test_can_view_attribute(
            'link', u'<span class="sprite team">&lt;hidden&gt;</span>')

    def test_can_view_api_url(self):
        self._test_can_view_attribute('api_url')

    def test_can_view_url(self):
        self._test_can_view_attribute('url')

    def test_can_view_icon(self):
        self._test_can_view_attribute(
            'icon', '<span class="sprite team private"></span>')


class TestObjectFormatterAPI(TestCaseWithFactory):
    """Tests for ObjectFormatterAPI"""

    layer = DatabaseFunctionalLayer

    def test_object_link_ignores_default(self):
        # The rendering of an object's link ignores any specified default
        # value which would be used in the case where the object were None.
        person = self.factory.makePerson()
        person_link = test_tales(
            'person/fmt:link::default value', person=person)
        self.assertEqual(PersonFormatterAPI(person).link(None), person_link)
        person_link = test_tales(
            'person/fmt:link:bugs:default value', person=person)
        self.assertEqual(PersonFormatterAPI(person).link(
            None, rootsite='bugs'), person_link)


class TestFormattersAPI(TestCaseWithFactory):
    """Tests for FormattersAPI."""

    layer = DatabaseFunctionalLayer

    test_data = (
        'http://localhost:8086/bar/baz/foo.html\n'
        'ftp://localhost:8086/bar/baz/foo.bar.html\n'
        'sftp://localhost:8086/bar/baz/foo.bar.html.\n'
        'http://localhost:8086/bar/baz/foo.bar.html;\n'
        'news://localhost:8086/bar/baz/foo.bar.html:\n'
        'http://localhost:8086/bar/baz/foo.bar.html?\n'
        'http://localhost:8086/bar/baz/foo.bar.html,\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>,\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>.\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>;\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>:\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>?\n'
        '(http://localhost:8086/bar/baz/foo.bar.html)\n'
        '(http://localhost:8086/bar/baz/foo.bar.html),\n'
        '(http://localhost:8086/bar/baz/foo.bar.html).\n'
        '(http://localhost:8086/bar/baz/foo.bar.html);\n'
        '(http://localhost:8086/bar/baz/foo.bar.html):\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a.\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a,\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a;\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a:\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b='
            'a:b;c@d_e%f~g#h,j!k-l+m$n*o\'p\n'
        'http://www.searchtools.com/test/urls/(parens).html\n'
        'http://www.searchtools.com/test/urls/-dash.html\n'
        'http://www.searchtools.com/test/urls/_underscore.html\n'
        'http://www.searchtools.com/test/urls/period.x.html\n'
        'http://www.searchtools.com/test/urls/!exclamation.html\n'
        'http://www.searchtools.com/test/urls/~tilde.html\n'
        'http://www.searchtools.com/test/urls/*asterisk.html\n'
        'irc://irc.freenode.net/launchpad\n'
        'irc://irc.freenode.net/%23launchpad,isserver\n'
        'mailto:noreply@launchpad.net\n'
        'jabber:noreply@launchpad.net\n'
        'http://localhost/foo?xxx&\n'
        'http://localhost?testing=[square-brackets-in-query]\n')

    def test_linkification_with_target(self):
        # The text-to-html-with-target formatter sets the target
        # attribute of the links it produces to _new.
        linkified_text = test_tales(
            'foo/fmt:text-to-html-with-target', foo=self.test_data)
        tree = html.fromstring(linkified_text)
        for link in tree.xpath('//a'):
            self.assertEqual('_new', link.get('target'))


class TestNoneFormatterAPI(TestCaseWithFactory):
    """Tests for NoneFormatterAPI"""

    layer = FunctionalLayer

    def test_format_link_none(self):
        # Test that format_link() handles None correctly.
        self.assertEqual(format_link(None), 'None')
        self.assertEqual(format_link(None, empty_value=''), '')

    def test_valid_traversal(self):
        # Traversal of allowed names works as expected.

        allowed_names = set([
            'approximatedate',
            'approximateduration',
            'break-long-words',
            'date',
            'datetime',
            'displaydate',
            'isodate',
            'email-to-html',
            'exactduration',
            'lower',
            'nice_pre',
            'nl_to_br',
            'pagetitle',
            'rfc822utcdatetime',
            'text-to-html',
            'time',
            'url',
            'link',
            ])

        for name in allowed_names:
            self.assertEqual('', test_tales('foo/fmt:%s' % name, foo=None))

    def test_value_override(self):
        # Override of rendered value works as expected.
        self.assertEqual(
            'default value',
            test_tales('foo/fmt:link::default value', foo=None))
        self.assertEqual(
            'default value',
            test_tales('foo/fmt:link:rootsite:default value', foo=None))

    def test_invalid_traversal(self):
        # Traversal of invalid names raises an exception.
        adapter = getAdapter(None, IPathAdapter, 'fmt')
        traverse = getattr(adapter, 'traverse', None)
        self.failUnlessRaises(TraversalError, traverse, "foo", [])

    def test_shorten_traversal(self):
        # Traversal of 'shorten' works as expected.
        adapter = getAdapter(None, IPathAdapter, 'fmt')
        traverse = getattr(adapter, 'traverse', None)
        # We expect that the last item in extra will be popped off.
        extra = ['1', '2']
        self.assertEqual('', traverse('shorten', extra))
        self.assertEqual(['1'], extra)


class TestIRCNicknameFormatterAPI(TestCaseWithFactory):
    """Tests for IRCNicknameFormatterAPI"""

    layer = DatabaseFunctionalLayer

    def test_nick_displayname(self):
        person = self.factory.makePerson(name='fred')
        ircset = getUtility(IIrcIDSet)
        ircID = ircset.new(person, "irc.canonical.com", "fred")
        self.assertEqual(
            'fred on irc.canonical.com',
            test_tales('nick/fmt:displayname', nick=ircID))

    def test_nick_formatted_displayname(self):
        person = self.factory.makePerson(name='fred')
        ircset = getUtility(IIrcIDSet)
        # Include some bogus markup to check escaping works.
        ircID = ircset.new(person, "<b>irc.canonical.com</b>", "fred")
        expected_html = test_tales(
            'nick/fmt:formatted_displayname', nick=ircID)
        self.assertEquals(
            u'<strong>fred</strong>\n'
            '<span class="lesser"> on </span>\n'
            '<strong>&lt;b&gt;irc.canonical.com&lt;/b&gt;</strong>\n',
            expected_html)


class ObjectImageDisplayAPITestCase(TestCaseWithFactory):
    """Tests for ObjectImageDisplayAPI"""

    layer = LaunchpadFunctionalLayer

    def test_custom_icon_url_context_is_None(self):
        # When the context is None, the URL is an empty string.
        display_api = ObjectImageDisplayAPI(None)
        self.assertEqual('', display_api.custom_icon_url())

    def test_custom_icon_url_context_has_no_icon(self):
        # When the context has not set the custom icon, the URL is None.
        product = self.factory.makeProduct()
        display_api = ObjectImageDisplayAPI(product)
        self.assertEqual(None, display_api.custom_icon_url())

    def test_custom_icon_url_context_has_an_icon(self):
        # When the context has a custom icon, the URL is for the
        # LibraryFileAlias.
        icon = self.factory.makeLibraryFileAlias(
            filename='smurf.png', content_type='image/png')
        product = self.factory.makeProduct(icon=icon)
        display_api = ObjectImageDisplayAPI(product)
        self.assertEqual(icon.getURL(), display_api.custom_icon_url())


class TestDateTimeFormatterAPI(TestCase):

    def test_yearDelta(self):
        """Test that year delta gives reasonable values."""
        def assert_delta(expected, old, new):
            old = datetime(*old, tzinfo=utc)
            new = datetime(*new, tzinfo=utc)
            delta = DateTimeFormatterAPI._yearDelta(old, new)
            self.assertEqual(expected, delta)
        assert_delta(1, (2000, 1, 1), (2001, 1, 1))
        assert_delta(0, (2000, 1, 2), (2001, 1, 1))
        # Check leap year handling (2004 is an actual leap year)
        assert_delta(0, (2003, 10, 10), (2004, 2, 29))
        assert_delta(0, (2004, 2, 29), (2005, 2, 28))

    def getDurationsince(self, delta):
        """Return the durationsince for a given delta."""
        creation = datetime(2000, 1, 1, tzinfo=utc)
        formatter = DateTimeFormatterAPI(creation)
        formatter._now = lambda: creation + delta
        return formatter.durationsince()

    def test_durationsince_in_years(self):
        """Values with different years are measured in years."""
        self.assertEqual('1 year', self.getDurationsince(timedelta(366)))
        self.assertEqual('2 years', self.getDurationsince(timedelta(731)))

    def test_durationsince_in_day(self):
        """Values with different days are measured in days."""
        self.assertEqual('1 day', self.getDurationsince(timedelta(1)))
        self.assertEqual('365 days', self.getDurationsince(timedelta(365)))

    def test_durationsince_in_hours(self):
        """Values with different hours are measured in hours."""
        self.assertEqual('2 hours', self.getDurationsince(timedelta(0, 7200)))
        self.assertEqual('1 hour', self.getDurationsince(timedelta(0, 3600)))

    def test_durationsince_in_minutes(self):
        """Values with different minutes are measured in minutes."""
        five = self.getDurationsince(timedelta(0, 300))
        self.assertEqual('5 minutes', five)
        self.assertEqual('1 minute', self.getDurationsince(timedelta(0, 60)))

    def test_durationsince_in_seconds(self):
        """Values in seconds are reported as "less than a minute."""
        self.assertEqual('less than a minute',
            self.getDurationsince(timedelta(0, 59)))


class TestPackageBuildFormatterAPI(TestCaseWithFactory):
    """Tests for PackageBuildFormatterAPI."""

    layer = LaunchpadFunctionalLayer

    def _make_public_build_for_private_team(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        team_owner = self.factory.makePerson()
        private_team = self.factory.makeTeam(
            owner=team_owner, visibility=PersonVisibility.PRIVATE)
        p3a = self.factory.makeArchive(owner=private_team, private=True)
        build = self.factory.makeBinaryPackageBuild(
            source_package_release=spph.sourcepackagerelease, archive=p3a)
        return build, p3a, team_owner

    def test_public_build_private_team_no_permission(self):
        # A `PackageBuild` for a public `SourcePackageRelease` in an archive
        # for a private team is rendered gracefully when the user has no
        # permission.
        build, _, _ = self._make_public_build_for_private_team()
        # Make sure this is a valid test; the build itself must be public.
        self.assertTrue(check_permission('launchpad.View', build))
        self.assertEqual('private job', format_link(build))

    def test_public_build_private_team_with_permission(self):
        # Members of a private team can see their builds.
        build, p3a, team_owner = self._make_public_build_for_private_team()
        login_person(team_owner)
        self.assertIn(
            "[%s/%s]" % (p3a.owner.name, p3a.name), format_link(build))
