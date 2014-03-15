# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View classes to handle signed Codes of Conduct."""

__metaclass__ = type

__all__ = [
    'SignedCodeOfConductSetNavigation',
    'CodeOfConductSetNavigation',
    'CodeOfConductOverviewMenu',
    'CodeOfConductSetOverviewMenu',
    'SignedCodeOfConductSetOverviewMenu',
    'SignedCodeOfConductOverviewMenu',
    'CodeOfConductView',
    'CodeOfConductDownloadView',
    'CodeOfConductSetView',
    'SignedCodeOfConductAddView',
    'SignedCodeOfConductAckView',
    'SignedCodeOfConductView',
    'SignedCodeOfConductAdminView',
    'SignedCodeOfConductActiveView',
    'SignedCodeOfConductDeactiveView',
    ]

from zope.component import getUtility

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.registry.interfaces.codeofconduct import (
    ICodeOfConduct,
    ICodeOfConductConf,
    ICodeOfConductSet,
    ISignedCodeOfConduct,
    ISignedCodeOfConductSet,
    )
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    enabled_with_permission,
    GetitemNavigation,
    LaunchpadView,
    Link,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import DataDownloadView


class SignedCodeOfConductSetNavigation(GetitemNavigation):

    usedfor = ISignedCodeOfConductSet


class CodeOfConductSetNavigation(GetitemNavigation):

    usedfor = ICodeOfConductSet


class CodeOfConductOverviewMenu(ApplicationMenu):

    usedfor = ICodeOfConduct
    facet = 'overview'
    links = ['sign', 'download']

    def sign(self):
        text = 'Sign it'
        if (self.context.current and
            self.user and
            not self.user.is_ubuntu_coc_signer):
            # Then...
            enabled = True
        else:
            enabled = False
        return Link('+sign', text, enabled=enabled, icon='edit')

    def download(self):
        text = 'Download this version'
        is_current = self.context.current
        return Link('+download', text, enabled=is_current, icon='download')


class CodeOfConductSetOverviewMenu(ApplicationMenu):

    usedfor = ICodeOfConductSet
    facet = 'overview'
    links = ['admin']

    @enabled_with_permission('launchpad.Admin')
    def admin(self):
        text = 'Administration console'
        return Link('console', text, icon='edit')


class SignedCodeOfConductSetOverviewMenu(ApplicationMenu):

    usedfor = ISignedCodeOfConductSet
    facet = 'overview'
    links = ['register']

    def register(self):
        text = "Register Someone's Signature"
        return Link('+new', text, icon='add')


class SignedCodeOfConductOverviewMenu(ApplicationMenu):

    usedfor = ISignedCodeOfConduct
    facet = 'overview'
    links = ['activation', 'adminconsole']

    def activation(self):
        if self.context.active:
            text = 'deactivate'
            return Link('+deactivate', text, icon='edit')
        else:
            text = 'activate'
            return Link('+activate', text, icon='edit')

    def adminconsole(self):
        text = 'Administration console'
        return Link('../', text, icon='info')


class CodeOfConductView(LaunchpadView):
    """Simple view class for CoC page."""

    @property
    def page_title(self):
        """See `LaunchpadView`."""
        # This page has no breadcrumbs, nor should it.
        return self.context.title


class CodeOfConductDownloadView(DataDownloadView):
    """Download view class for CoC page.

    This view provides a text file with "Content-disposition: attachment",
    causing browsers to download rather than display it.
    """

    content_type = 'text/plain'

    def getBody(self):
        # Use the context attribute 'content' as data to return.
        # Avoid open the CoC file again.
        return self.context.content

    @property
    def filename(self):
        # Build a fancy filename:
        # - Use title with no spaces and append '.txt'
        return self.context.title.replace(' ', '') + '.txt'


class CodeOfConductSetView(LaunchpadView):
    """Simple view class for CoCSet page."""

    page_title = 'Ubuntu Codes of Conduct'


class SignedCodeOfConductAddView(LaunchpadFormView):
    """Add a new SignedCodeOfConduct Entry."""
    schema = ISignedCodeOfConduct
    field_names = ['signedcode']

    @property
    def page_title(self):
        return 'Sign %s' % self.context.title

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        signedcode = data["signedcode"]
        signedcocset = getUtility(ISignedCodeOfConductSet)
        error_message = signedcocset.verifyAndStore(self.user, signedcode)
        # It'd be nice to do this validation before, but the method which does
        # the validation is also the one that stores the signed CoC, so we
        # need to do everything here.
        if error_message:
            self.addError(error_message)
            return
        self.next_url = canonical_url(self.user) + '/+codesofconduct'

    @property
    def current(self):
        """Return the current release of the Code of Conduct."""
        coc_conf = getUtility(ICodeOfConductConf)
        coc_set = getUtility(ICodeOfConductSet)
        return coc_set[coc_conf.currentrelease]


class SignedCodeOfConductAckView(LaunchpadFormView):
    """Acknowledge a Paper Submitted CoC."""
    schema = ISignedCodeOfConduct
    field_names = ['owner']
    label = 'Register a code of conduct signature'
    page_title = label

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @action('Register', name='add')
    def createAndAdd(self, action, data):
        """Verify and Add the Acknowledge SignedCoC entry."""
        self.context.acknowledgeSignature(
            user=data['owner'], recipient=self.user)


class SignedCodeOfConductView(CodeOfConductView):
    """Simple view class for SignedCoC page."""


class SignedCodeOfConductAdminView(LaunchpadView):
    """Admin Console for SignedCodeOfConduct Entries."""

    page_title = 'Administer Codes of Conduct'

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.bag = getUtility(ILaunchBag)
        self.results = None

    def search(self):
        """Search Signed CoC by Owner Displayname"""
        name = self.request.form.get('name')
        searchfor = self.request.form.get('searchfor')

        if (self.request.method != "POST" or
            self.request.form.get("search") != "Search"):
            return

        # use utility to query on SignedCoCs
        sCoC_util = getUtility(ISignedCodeOfConductSet)
        self.results = sCoC_util.searchByDisplayname(name,
                                                     searchfor=searchfor)

        return True


class SignedCodeOfConductActiveView(LaunchpadFormView):
    """Active a SignedCodeOfConduct Entry."""
    schema = ISignedCodeOfConduct
    field_names = ['admincomment']
    label = 'Activate code of conduct signature'
    page_title = label
    state = True

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    def _change(self, action, data):
        admincomment = data['admincomment']
        sCoC_util = getUtility(ISignedCodeOfConductSet)
        sCoC_util.modifySignature(
            sign_id=self.context.id, recipient=self.user,
            admincomment=admincomment, state=self.state)
        self.request.response.redirect(self.next_url)

    @action('Activate', name='change')
    def activate(self, action, data):
        self._change(action, data)


class SignedCodeOfConductDeactiveView(SignedCodeOfConductActiveView):
    """Deactivate a SignedCodeOfConduct Entry."""
    label = 'Deactivate code of conduct signature'
    page_title = label
    state = False

    @action('Deactivate', name='change')
    def deactivate(self, action, data):
        self._change(action, data)
