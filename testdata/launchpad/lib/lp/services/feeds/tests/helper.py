# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions for testing feeds."""

__metaclass__ = type
__all__ = [
    'IThing',
    'parse_entries',
    'parse_ids',
    'parse_links',
    'Thing',
    'ThingFeedView',
    'validate_feed',
    ]


import socket


original_timeout = socket.getdefaulttimeout()
import feedvalidator
if socket.getdefaulttimeout() != original_timeout:
    # feedvalidator's __init__ uses setdefaulttimeout promiscuously
    socket.setdefaulttimeout(original_timeout)
from cStringIO import StringIO
from textwrap import wrap

from zope.interface import (
    Attribute,
    implements,
    Interface,
    )
from BeautifulSoup import BeautifulStoneSoup as BSS
from BeautifulSoup import SoupStrainer

from lp.services.webapp.publisher import LaunchpadView


class IThing(Interface):
    value = Attribute('the value of the thing')


class Thing(object):
    implements(IThing)

    def __init__(self, value):
        self.value = value

        def __repr__(self):
            return "<Thing '%s'>" % self.value


class ThingFeedView(LaunchpadView):
    usedfor = IThing
    feedname = "thing-feed"
    def __call__(self):
        return "a feed view on an IThing"


def parse_entries(contents):
    """Define a helper function for parsing feed entries."""
    strainer = SoupStrainer('entry')
    entries = [tag for tag in BSS(contents,
                                  parseOnlyThese=strainer)]
    return entries


def parse_links(contents, rel):
    """Define a helper function for parsing feed links."""
    strainer = SoupStrainer('link', rel=rel)
    entries = [tag for tag in BSS(contents,
                                  parseOnlyThese=strainer,
                                  selfClosingTags=['link'])]
    return entries


def parse_ids(contents):
    """Define a helper function for parsing ids."""
    strainer = SoupStrainer('id')
    ids = [tag for tag in BSS(contents,
                              parseOnlyThese=strainer)]
    return ids


def validate_feed(content, content_type, base_uri):
    """Validate the content of an Atom, RSS, or KML feed.
    :param content: string containing xml feed
    :param content_type: Content-Type HTTP header
    :param base_uri: Feed URI for comparison with <link rel="self">

    Prints formatted list of warnings and errors for use in doctests.
    No return value.
    """
    lines = content.split('\n')
    result = feedvalidator.validateStream(
        StringIO(content),
        contentType=content_type,
        base=base_uri)

    errors = []
    for error_level in (feedvalidator.logging.Error,
                        feedvalidator.logging.Warning,
                        feedvalidator.logging.Info):
        for item in result['loggedEvents']:
            if isinstance(item, error_level):
                errors.append("-------- %s: %s --------"
                    % (error_level.__name__, item.__class__.__name__))
                for key, value in sorted(item.params.items()):
                    errors.append('%s: %s' % (key.title(), value))
                if 'line' not in item.params:
                    continue
                if isinstance(item,
                              feedvalidator.logging.SelfDoesntMatchLocation):
                    errors.append('Location: %s' % base_uri)
                error_line_number = item.params['line']
                column_number = item.params['column']
                errors.append('=')
                # Wrap the line with the error to make it clearer
                # which column contains the error.
                max_line_length = 66
                wrapped_column_number = column_number % max_line_length
                line_number_range = range(
                    max(error_line_number-2, 1),
                    min(error_line_number+3, len(lines)))
                for line_number in line_number_range:
                    unicode_line = unicode(
                        lines[line_number-1], 'ascii', 'replace')
                    ascii_line = unicode_line.encode('ascii', 'replace')
                    wrapped_lines = wrap(ascii_line, max_line_length)
                    if line_number == error_line_number:
                        # Point to the column where the error occurs, e.g.
                        # Error: <feed><entriez>
                        # Point: ~~~~~~~~~~~~~^~~~~~~~~~~~~~~
                        point_list = ['~'] * max_line_length
                        point_list[wrapped_column_number] = '^'
                        point_string = ''.join(point_list)
                        index = column_number/max_line_length + 1
                        wrapped_lines.insert(index, point_string)
                    errors.append(
                        "% 3d: %s" % (line_number,
                                      '\n   : '.join(wrapped_lines)))
                errors.append('=')
    if len(errors) == 0:
        print "No Errors"
    else:
        print '\n'.join(errors)
