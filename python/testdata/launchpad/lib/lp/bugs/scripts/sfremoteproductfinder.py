# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utilities for the sfremoteproductfinder cronscript"""

__metaclass__ = type
__all__ = [
    'SourceForgeRemoteProductFinder',
    ]

import urllib
from urllib2 import (
    HTTPError,
    urlopen,
    )

from BeautifulSoup import BeautifulSoup
from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.product import IProductSet
from lp.services.scripts.logger import log as default_log
from lp.services.webapp import (
    urlappend,
    urlsplit,
    )


class SourceForgeRemoteProductFinder:
    """Responsible for finding the remote product of SourceForge projects."""

    def __init__(self, txn, logger=None):
        self.txn = txn
        self.logger = logger
        if logger is None:
            self.logger = default_log

        # We use the SourceForge celebrity to make sure that we're
        # always going to use the right URLs.
        self.sourceforge_baseurl = getUtility(
            ILaunchpadCelebrities).sourceforge_tracker.baseurl

    def _getPage(self, page):
        """GET the specified page on the remote HTTP server."""
        page_url = urlappend(self.sourceforge_baseurl, page)
        return urlopen(page_url).read()

    def getRemoteProductFromSourceForge(self, sf_project):
        """Return the remote product of a SourceForge project.

        :return: The group_id and atid of the SourceForge project's bug
            tracker as an ampersand-separated string in the form
            'group_id&atid'.
        """
        # First, fetch the project page.
        try:
            soup = BeautifulSoup(self._getPage("projects/%s" % sf_project))
        except HTTPError as error:
            self.logger.error(
                "Error fetching project %s: %s" %
                (sf_project, error))
            return None

        # Find the Tracker link and fetch that.
        tracker_link = soup.find('a', text='Tracker')
        if tracker_link is None:
            self.logger.error(
                "No tracker link for project '%s'" % sf_project)
            return None

        tracker_url = tracker_link.findParent()['href']

        # Clean any leading '/' from tracker_url so that urlappend
        # doesn't choke on it.
        tracker_url = tracker_url.lstrip('/')
        try:
            soup = BeautifulSoup(self._getPage(tracker_url))
        except HTTPError as error:
            self.logger.error(
                "Error fetching project %s: %s" %
                (sf_project, error))
            return None

        # Extract the group_id and atid from the bug tracker link.
        bugtracker_link = soup.find('a', text='Bugs')
        if bugtracker_link is None:
            self.logger.error(
                "No bug tracker link for project '%s'" % sf_project)
            return None

        bugtracker_url = bugtracker_link.findParent()['href']

        # We need to replace encoded ampersands in the URL since
        # SourceForge usually encodes them.
        bugtracker_url = bugtracker_url.replace('&amp;', '&')
        schema, host, path, query, fragment = urlsplit(bugtracker_url)

        query_dict = {}
        query_bits = query.split('&')
        for bit in query_bits:
            key, value = urllib.splitvalue(bit)
            query_dict[key] = value

        try:
            atid = int(query_dict.get('atid', None))
            group_id = int(query_dict.get('group_id', None))
        except ValueError:
            # If anything goes wrong when int()ing the IDs, just return
            # None.
            return None

        return u'%s&%s' % (group_id, atid)

    def setRemoteProductsFromSourceForge(self):
        """Find and set the remote product for SF-linked Products."""
        products_to_update = getUtility(
            IProductSet).getSFLinkedProductsWithNoneRemoteProduct()

        if products_to_update.count() == 0:
            self.logger.info("No Products to update.")
            return

        self.logger.info(
            "Updating %s Products using SourceForge project data" %
            products_to_update.count())

        for product in products_to_update:
            self.txn.begin()
            self.logger.debug(
                "Updating remote_product for Product '%s'" % product.name)
            product.remote_product = self.getRemoteProductFromSourceForge(
                product.sourceforgeproject)
            self.txn.commit()
