# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""CVE views."""

__metaclass__ = type

__all__ = [
    'CveContextMenu',
    'CveIndexView',
    'CveLinkView',
    'CveSetContextMenu',
    'CveSetNavigation',
    'CveSetView',
    'CveUnlinkView',
    ]

from zope.component import getUtility

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.app.validators.cve import valid_cve
from lp.bugs.browser.buglinktarget import BugLinksListingView
from lp.bugs.interfaces.cve import (
    ICve,
    ICveSet,
    )
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    GetitemNavigation,
    LaunchpadView,
    Link,
    )
from lp.services.webapp.batching import BatchNavigator


class CveSetNavigation(GetitemNavigation):

    usedfor = ICveSet


class CveContextMenu(ContextMenu):

    usedfor = ICve
    links = ['linkbug', 'unlinkbug']

    def linkbug(self):
        text = 'Link to bug'
        return Link('+linkbug', text, icon='edit')

    def unlinkbug(self):
        enabled = bool(self.context.bugs)
        text = 'Remove bug link'
        return Link('+unlinkbug', text, icon='edit', enabled=enabled)


class CveSetContextMenu(ContextMenu):

    usedfor = ICveSet
    links = ['findcve', 'allcve']

    def allcve(self):
        text = 'All registered CVEs'
        return Link('+all', text)

    def findcve(self):
        text = 'Find CVEs'
        summary = 'Find CVEs in Launchpad'
        return Link('', text, summary)


class CveIndexView(BugLinksListingView):
    """CVE index page."""

    @property
    def page_title(self):
        return self.context.displayname


class CveLinkView(LaunchpadFormView):
    """This view will be used for objects that can be linked to a CVE,
    currently that is only IBug.
    """
    schema = ICve
    field_names = ['sequence']

    def validate(self, data):
        sequence = data.get('sequence')
        if sequence is None:
            # Don't attempt to look up this CVE; its number is not valid.
            return
        cve = getUtility(ICveSet)[sequence]
        if cve is None:
            self.addError('%s is not a known CVE sequence number.' % sequence)

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        cve = getUtility(ICveSet)[data['sequence']]
        self.context.bug.linkCVE(cve, self.user)
        self.request.response.addInfoNotification(
            'CVE-%s added.' % data['sequence'])

    label = 'Link to CVE report'

    page_title = label

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url


class CveUnlinkView(CveLinkView):
    """This view is used to unlink a CVE from a bug."""

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        cve = getUtility(ICveSet)[data['sequence']]
        self.context.bug.unlinkCVE(cve, self.user)
        self.request.response.addInfoNotification(
            'CVE-%s removed.' % data['sequence'])

    @property
    def label(self):
        return  'Bug # %s Remove link to CVE report' % self.context.bug.id

    page_title = label

    heading = 'Remove links to bug reports'


class CveSetView(LaunchpadView):

    def __init__(self, context, request):
        super(CveSetView, self).__init__(context, request)
        self.notices = []
        self.results = None
        self.text = self.request.form.get('text', None)
        self.searchrequested = False

        if self.text:
            self.pre_search()

    label = 'Launchpad CVE tracker'
    page_title = label

    def getAllBatched(self):
        return BatchNavigator(self.context.getAll(), self.request)

    def pre_search(self):
        # see if we have an exact match, and redirect if so; otherwise,
        # do a search for it.
        sequence = self.text
        if sequence[:4].lower() in ['cve-', 'can-']:
            sequence = sequence[4:].strip()
        if valid_cve(sequence):
            # try to find the CVE, and redirect to it if we do
            cveset = getUtility(ICveSet)
            cve = cveset[sequence]
            if cve:
                self.request.response.redirect(canonical_url(cve))
        self.searchrequested = True

    def searchresults(self):
        """Use searchtext to find the list of Products that match
        and then present those as a list. Only do this the first
        time the method is called, otherwise return previous results.
        """
        if self.results is None:
            self.results = self.context.search(text=self.text)
            self.matches = self.results.count()
        return self.results
