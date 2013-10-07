# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'LinkCheckerAPI',
    ]

import simplejson
from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.code.errors import (
    CannotHaveLinkedBranch,
    InvalidNamespace,
    NoLinkedBranch,
    NoSuchBranch,
    )
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.registry.interfaces.product import InvalidProductName
from lp.services.searchbuilder import any
from lp.services.webapp import LaunchpadView


class LinkCheckerAPI(LaunchpadView):
    """Validates Launchpad shortcut links.

    This class provides the endpoint of an Ajax call to .../+check-links.
    When invoked with a collection of links harvested from a page, it will
    check the validity of each one and send a response containing those that
    are invalid. Javascript on the page will set the style of invalid links to
    something appropriate.

    This initial implementation supports processing links like the following:
        /+branch/foo/bar

    The implementation can easily be extended to handle other forms by
    providing a method to handle the link type extracted from the json
    request.
    """

    def __init__(self, context, request):
        # We currently only use the request.
        # self.context = context
        self.request = request

        # Each link type has it's own validation method.
        self.link_checkers = dict(
            branch_links=self.check_branch_links,
            bug_links=self.check_bug_links,
        )

    def __call__(self):
        result = {}
        links_to_check_data = self.request.get('link_hrefs')
        if links_to_check_data is None:
            return simplejson.dumps(result)
        links_to_check = simplejson.loads(links_to_check_data)

        for link_type in links_to_check:
            links = links_to_check[link_type]
            link_info = self.link_checkers[link_type](links)
            result[link_type] = link_info

        self.request.response.setHeader('Content-type', 'application/json')
        return simplejson.dumps(result)

    def check_branch_links(self, links):
        """Check links of the form /+branch/foo/bar"""
        invalid_links = {}
        branch_lookup = getUtility(IBranchLookup)
        for link in links:
            path = link.strip('/')[len('+branch/'):]
            try:
                branch_lookup.getByLPPath(path)
            except (CannotHaveLinkedBranch, InvalidNamespace,
                    InvalidProductName, NoLinkedBranch, NoSuchBranch,
                    NotFoundError) as e:
                invalid_links[link] = self._error_message(e)
        return {'invalid': invalid_links}

    def check_bug_links(self, links):
        """Checks links of the form /bugs/100"""
        invalid_links = {}
        valid_links = {}
        user = self.user
        # List of all the bugs we are checking.
        bugs_ids = set([int(link[len('/bugs/'):]) for link in links])
        if bugs_ids:
            params = BugTaskSearchParams(
                user=user, status=None,
                bug=any(*bugs_ids))
            bugtasks = getUtility(IBugTaskSet).search(params)
            for task in bugtasks:
                valid_links['/bugs/' + str(task.bug.id)] = task.bug.title
                # Remove valid bugs from the list of all the bugs.
                if task.bug.id in bugs_ids:
                    bugs_ids.remove(task.bug.id)
            # We should now have only invalid bugs in bugs list
            for bug in bugs_ids:
                invalid_links['/bugs/%d' % bug] = (
                    "Bug %s cannot be found" % bug)
        return {'valid': valid_links, 'invalid': invalid_links}

    def _error_message(self, ex):
        if hasattr(ex, 'display_message'):
            return ex.display_message
        return str(ex)
