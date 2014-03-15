#!/usr/bin/env python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
This script is here to help us discover what the text equivalent of a
Roundup numeric field is remotely, without access to the Roundup
database.

It does this by downloading all bugs from the remote bug tracker in
CSV format, which gives us numeric values for the fields we're
interested in (e.g. status and substatus).

It then discovers all distinct combinations of those fields then
downloads an example bug page for each. It scrapes the bug page to
find the text that corresponds to the numeric value we already have.

There is a race condition. Someone can edit the bug page between the
CSV download and the bug page download, so be sure to run this more
than once and compare the results.

To complicate matters, downloaded pages are cached. To redownload the
CSV or a bug page the cache file must be deleted. It is a completely
non-HTTP compliant cache! This is an aid during development when this
script is run many times, and also provides a measure of robustness
against errors; there's no need to start from the beginning every
time.

Perhaps the best way to make this work for a new Roundup instance is
to subclass RoundupSniffer and implement get_text_values() and
populate the class-level "fields" variable. See MplayerStatusSniffer
for an example.
"""

__metaclass__ = type

from base64 import urlsafe_b64encode
import csv
import optparse
from os import mkdir
from os.path import (
    exists,
    join,
    )
from pprint import pprint
import sys
from time import sleep
from urllib import urlencode
import urllib2

from BeautifulSoup import BeautifulSoup


class RoundupSniffer:
    """Sniffs the meaning of numeric fields in remote Roundups."""

    fields = ('status',)

    def __init__(self, base_url, cache_dir):
        self.base_url = base_url
        self.cache_dir = cache_dir
        if not exists(self.cache_dir):
            mkdir(self.cache_dir)

    def fetch(self, url):
        """Fetch the URL, consulting the cache first."""
        filename = join(self.cache_dir, urlsafe_b64encode(url))
        if not exists(filename):
            open(filename, 'wb').write(
                urllib2.urlopen(url).read())
        return open(filename, 'rb')

    def get_all_bugs(self):
        all_fields = ['id']
        all_fields.extend(self.fields)
        query = [
            ('@action', 'export_csv'),
            ('@columns', ','.join(all_fields)),
            ('@sort', 'activity'),
            ('@group', 'priority'),
            ('@pagesize', '50'),
            ('@startwith', '0'),
            ]
        url = '%s?%s' % (self.base_url, urlencode(query))
        bugs = csv.DictReader(self.fetch(url))
        return list(bugs)

    def get_text_values(self, bug):
        raise NotImplementedError(self.get_text_values.func_name)


class MplayerStatusSniffer(RoundupSniffer):
    """Sniffer for the Mplayer/FFMpeg Roundup.

    http://roundup.mplayerhq.hu/roundup/ffmpeg/

    This looks to be a mostly unmodified instance, so this sniffer may
    be useful in general.
    """

    fields = ('status', 'substatus')

    def get_text_values(self, bug):
        """Returns the text of status and substatus for the given bug.

        This is done by downloading the HTML bug page and scraping it.
        """
        url = '%s%s' % (self.base_url, bug['id'])
        page = self.fetch(url).read()
        soup = BeautifulSoup(page)
        return tuple(
            node.string for node in
            soup.find('th', text='Status').findNext('td').findAll('span'))


def get_distinct(things, fields):
    """Identify every distinct combination of fields.

    For each combination also return one example thing.
    """
    def key(thing):
        return tuple(thing[field] for field in fields)
    return dict((key(thing), thing) for thing in things)


def gen_mapping(sniffer):
    """Generate a mapping from raw field values to text values."""
    bugs = sniffer.get_all_bugs()
    distinct_bugs = get_distinct(bugs, sniffer.fields)
    for raw_values, bug in distinct_bugs.items():
        text_values = sniffer.get_text_values(bug)
        yield raw_values, text_values


def parse_args(args):
    parser = optparse.OptionParser()
    parser.add_option(
        "--base-url", dest="base_url",
        help="The base URL at the remote Roundup instance.",
        metavar="URL")
    parser.add_option(
        "--delay", dest="delay", type="int",
        help=("The number of seconds to wait between each page "
              "load [default: %default]."))
    parser.add_option(
        "--cache-dir", dest="cache_dir",
        help=("A directory in which to cache fetched resources "
              "[default: %default]."),
        metavar="DIR")
    parser.add_option(
        "--sniffer-class", dest="sniffer_class",
        help="The sniffer class to use [default: %default].",
        metavar="CLASSNAME")
    parser.set_defaults(
        delay=0, cache_dir="roundup_sniffer_cache",
        sniffer_class="MplayerStatusSniffer")

    options, args = parser.parse_args(args)

    if not options.base_url:
        parser.error("Please specify a base URL.")
    if len(args) > 0:
        parser.error("Positional arguments are not accepted: %s" %
                     ' '.join(args))

    return options


if __name__ == '__main__':
    options = parse_args(sys.argv[1:])
    sniffer = eval(options.sniffer_class)(
        options.base_url, options.cache_dir)
    mapping = {}
    for raw, text in gen_mapping(sniffer):
        mapping[raw] = text
        sleep(options.delay)
    pprint(mapping)
