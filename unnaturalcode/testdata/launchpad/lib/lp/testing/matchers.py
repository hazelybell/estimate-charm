# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BrowsesWithQueryLimit',
    'Contains',
    'DocTestMatches',
    'DoesNotCorrectlyProvide',
    'DoesNotProvide',
    'EqualsIgnoringWhitespace',
    'HasQueryCount',
    'IsNotProxied',
    'IsProxied',
    'MatchesPickerText',
    'MatchesTagText',
    'MissingElement',
    'MultipleElements',
    'Provides',
    'ProvidesAndIsProxied',
    ]

from lazr.lifecycle.snapshot import Snapshot
from testtools import matchers
from testtools.content import Content
from testtools.content_type import UTF8_TEXT
from testtools.matchers import (
    DocTestMatches as OriginalDocTestMatches,
    Equals,
    LessThan,
    Matcher,
    Mismatch,
    )
from testtools.matchers._higherorder import MismatchesAll
from zope.interface.exceptions import (
    BrokenImplementation,
    BrokenMethodImplementation,
    DoesNotImplement,
    )
from zope.interface.verify import verifyObject
from zope.security.proxy import (
    builtin_isinstance,
    Proxy,
    )

from lp.services.database.sqlbase import flush_database_caches
from lp.services.webapp import canonical_url
from lp.services.webapp.batching import BatchNavigator
from lp.testing import normalize_whitespace
from lp.testing._login import person_logged_in
from lp.testing._webservice import QueryCollector


class BrowsesWithQueryLimit(Matcher):
    """Matches the rendering of an objects default view with a query limit.

    This is a wrapper for HasQueryCount which does the heavy lifting on the
    query comparison - BrowsesWithQueryLimit simply provides convenient
    glue to use a userbrowser and view an object.
    """

    def __init__(self, query_limit, user, view_name="+index", **options):
        """Create a BrowsesWithQueryLimit checking for limit query_limit.

        :param query_limit: The number of queries permited for the page.
        :param user: The user to use to render the page.
        :param view_name: The name of the view to use to render tha page.
        :param options: Additional options for view generation eg rootsite.
        """
        self.query_limit = query_limit
        self.user = user
        self.view_name = view_name
        self.options = options

    def match(self, context):
        # circular dependencies.
        from lp.testing.pages import setupBrowserForUser
        with person_logged_in(self.user):
            context_url = canonical_url(
                context, view_name=self.view_name, **self.options)
        browser = setupBrowserForUser(self.user)
        flush_database_caches()
        collector = QueryCollector()
        collector.register()
        try:
            browser.open(context_url)
            counter = HasQueryCount(LessThan(self.query_limit))
            # When bug 724691 is fixed, this can become an AnnotateMismatch to
            # describe the object being rendered.
            return counter.match(collector)
        finally:
            # Unregister now in case this method is called multiple
            # times in a single test.
            collector.unregister()

    def __str__(self):
        return "BrowsesWithQueryLimit(%s, %s)" % (self.query_limit, self.user)


class DoesNotProvide(Mismatch):
    """An object does not provide an interface."""

    def __init__(self, obj, interface):
        """Create a DoesNotProvide Mismatch.

        :param obj: the object that does not match.
        :param interface: the Interface that the object was supposed to match.
        """
        self.obj = obj
        self.interface = interface

    def describe(self):
        return "%r does not provide %r." % (self.obj, self.interface)


class DoesNotCorrectlyProvide(DoesNotProvide):
    """An object does not correctly provide an interface."""

    def __init__(self, obj, interface, extra=None):
        """Create a DoesNotCorrectlyProvide Mismatch.

        :param obj: the object that does not match.
        :param interface: the Interface that the object was supposed to match.
        :param extra: any extra information about the mismatch as a string,
            or None
        """
        super(DoesNotCorrectlyProvide, self).__init__(obj, interface)
        self.extra = extra

    def describe(self):
        if self.extra is not None:
            extra = ": %s" % self.extra
        else:
            extra = "."
        return ("%r claims to provide %r, but does not do so correctly%s"
                % (self.obj, self.interface, extra))


class Provides(Matcher):
    """Test that an object provides a certain interface."""

    def __init__(self, interface):
        """Create a Provides Matcher.

        :param interface: the Interface that the object should provide.
        """
        self.interface = interface

    def __str__(self):
        return "provides %r." % self.interface

    def match(self, matchee):
        if not self.interface.providedBy(matchee):
            return DoesNotProvide(matchee, self.interface)
        passed = True
        extra = None
        try:
            if not verifyObject(self.interface, matchee):
                passed = False
        except (BrokenImplementation, BrokenMethodImplementation,
                DoesNotImplement) as e:
            passed = False
            extra = str(e)
        if not passed:
            return DoesNotCorrectlyProvide(
                matchee, self.interface, extra=extra)
        return None


class HasQueryCount(Matcher):
    """Adapt a Binary Matcher to the query count on a QueryCollector.

    If there is a mismatch, the queries from the collector are provided as a
    test attachment.
    """

    def __init__(self, count_matcher):
        """Create a HasQueryCount that will match using count_matcher."""
        self.count_matcher = count_matcher

    def __str__(self):
        return "HasQueryCount(%s)" % self.count_matcher

    def match(self, something):
        mismatch = self.count_matcher.match(something.count)
        if mismatch is None:
            return None
        return _MismatchedQueryCount(mismatch, something)


class _MismatchedQueryCount(Mismatch):
    """The Mismatch for a HasQueryCount matcher."""

    def __init__(self, mismatch, query_collector):
        self.count_mismatch = mismatch
        self.query_collector = query_collector

    def describe(self):
        return "queries do not match: %s" % (self.count_mismatch.describe(),)

    def get_details(self):
        result = []
        for query in self.query_collector.queries:
            result.append(unicode(query).encode('utf8'))
        return {'queries': Content(UTF8_TEXT, lambda: ['\n'.join(result)])}


class IsNotProxied(Mismatch):
    """An object is not proxied."""

    def __init__(self, obj):
        """Create an IsNotProxied Mismatch.

        :param obj: the object that is not proxied.
        """
        self.obj = obj

    def describe(self):
        return "%r is not proxied." % self.obj


class IsProxied(Matcher):
    """Check that an object is proxied."""

    def __str__(self):
        return "Is proxied."

    def match(self, matchee):
        if not builtin_isinstance(matchee, Proxy):
            return IsNotProxied(matchee)
        return None


class ProvidesAndIsProxied(Matcher):
    """Test that an object implements an interface, and is proxied."""

    def __init__(self, interface):
        """Create a ProvidesAndIsProxied matcher.

        :param interface: the Interface the object must provide.
        """
        self.interface = interface

    def __str__(self):
        return "Provides %r and is proxied." % self.interface

    def match(self, matchee):
        mismatch = Provides(self.interface).match(matchee)
        if mismatch is not None:
            return mismatch
        return IsProxied().match(matchee)


class DoesNotContain(Mismatch):

    def __init__(self, matchee, expected):
        """Create a DoesNotContain Mismatch.

        :param matchee: the string that did not match.
        :param expected: the string that `matchee` was expected to contain.
        """
        self.matchee = matchee
        self.expected = expected

    def describe(self):
        return "'%s' does not contain '%s'." % (
            self.matchee, self.expected)


class Contains(Matcher):
    """Checks whether one string contains another."""

    def __init__(self, expected):
        """Create a Contains Matcher.

        :param expected: the string that matchees should contain.
        """
        self.expected = expected

    def __str__(self):
        return "Contains '%s'." % self.expected

    def match(self, matchee):
        if self.expected not in matchee:
            return DoesNotContain(matchee, self.expected)
        return None


class IsConfiguredBatchNavigator(Matcher):
    """Check that an object is a batch navigator."""

    def __init__(self, singular, plural, batch_size=None):
        """Create a ConfiguredBatchNavigator.

        :param singular: The singular header the batch should be using.
        :param plural: The plural header the batch should be using.
        :param batch_size: The batch size that should be configured by
            default.
        """
        self._single = Equals(singular)
        self._plural = Equals(plural)
        self._batch = None
        if batch_size:
            self._batch = Equals(batch_size)
        self.matchers = dict(
            _singular_heading=self._single, _plural_heading=self._plural)
        if self._batch:
            self.matchers['default_size'] = self._batch

    def __str__(self):
        if self._batch:
            batch = ", %r" % self._batch.expected
        else:
            batch = ''
        return "ConfiguredBatchNavigator(%r, %r%s)" % (
            self._single.expected, self._plural.expected, batch)

    def match(self, matchee):
        if not isinstance(matchee, BatchNavigator):
            # Testtools doesn't have an IsInstanceMismatch yet.
            return matchers._BinaryMismatch(
                BatchNavigator, 'isinstance', matchee)
        mismatches = []
        for attrname, matcher in self.matchers.items():
            mismatch = matcher.match(getattr(matchee, attrname))
            if mismatch is not None:
                mismatches.append(mismatch)
        if mismatches:
            return MismatchesAll(mismatches)


class WasSnapshotted(Mismatch):

    def __init__(self, matchee, attribute):
        self.matchee = matchee
        self.attribute = attribute

    def describe(self):
        return "Snapshot of %s should not include %s" % (
            self.matchee, self.attribute)


class DoesNotSnapshot(Matcher):
    """Checks that certain fields are skipped on Snapshots."""

    def __init__(self, attr_list, interface, error_msg=None):
        self.attr_list = attr_list
        self.interface = interface
        self.error_msg = error_msg

    def __str__(self):
        return "Does not include %s when Snapshot is provided %s." % (
            ', '.join(self.attr_list), self.interface)

    def match(self, matchee):
        snapshot = Snapshot(matchee, providing=self.interface)
        mismatches = []
        for attribute in self.attr_list:
            if hasattr(snapshot, attribute):
                mismatches.append(WasSnapshotted(matchee, attribute))

        if len(mismatches) == 0:
            return None
        else:
            return MismatchesAll(mismatches)


def DocTestMatches(example):
    """See if a string matches a doctest example.

    Uses the default doctest flags used across Launchpad.
    """
    from lp.testing.systemdocs import default_optionflags
    return OriginalDocTestMatches(example, default_optionflags)


class SoupMismatch(Mismatch):

    def __init__(self, widget_id, soup_content):
        self.widget_id = widget_id
        self.soup_content = soup_content

    def get_details(self):
        return {'content': self.soup_content}


class MissingElement(SoupMismatch):

    def describe(self):
        return 'No HTML element found with id %r' % self.widget_id


class MultipleElements(SoupMismatch):

    def describe(self):
        return 'HTML id %r found multiple times in document' % self.widget_id


class MatchesTagText(Matcher):
    """Match against the extracted text of the tag."""

    def __init__(self, soup_content, tag_id):
        """Construct the matcher with the soup content."""
        self.soup_content = soup_content
        self.tag_id = tag_id

    def __str__(self):
        return "matches widget %r text" % self.tag_id

    def match(self, matchee):
        # Here to avoid circular dependancies.
        from lp.testing.pages import extract_text
        widgets = self.soup_content.findAll(id=self.tag_id)
        if len(widgets) == 0:
            return MissingElement(self.tag_id, self.soup_content)
        elif len(widgets) > 1:
            return MultipleElements(self.tag_id, self.soup_content)
        widget = widgets[0]
        text_matcher = DocTestMatches(extract_text(widget))
        return text_matcher.match(matchee)


class MatchesPickerText(Matcher):
    """Match against the text in a widget."""

    def __init__(self, soup_content, widget_id):
        """Construct the matcher with the soup content."""
        self.soup_content = soup_content
        self.widget_id = widget_id

    def __str__(self):
        return "matches widget %r text" % self.widget_id

    def match(self, matchee):
        # Here to avoid circular dependancies.
        from lp.testing.pages import extract_text
        widgets = self.soup_content.findAll(id=self.widget_id)
        if len(widgets) == 0:
            return MissingElement(self.widget_id, self.soup_content)
        elif len(widgets) > 1:
            return MultipleElements(self.widget_id, self.soup_content)
        widget = widgets[0]
        text = widget.findAll(attrs={'class': 'yui3-activator-data-box'})[0]
        text_matcher = DocTestMatches(extract_text(text))
        return text_matcher.match(matchee)


class EqualsIgnoringWhitespace(Equals):
    """Compare equality, ignoring whitespace in strings.

    Whitespace in strings is normalized before comparison. All other objects
    are compared as they come.
    """

    def __init__(self, expected):
        if isinstance(expected, (str, unicode)):
            expected = normalize_whitespace(expected)
        super(EqualsIgnoringWhitespace, self).__init__(expected)

    def match(self, observed):
        if isinstance(observed, (str, unicode)):
            observed = normalize_whitespace(observed)
        return super(EqualsIgnoringWhitespace, self).match(observed)
