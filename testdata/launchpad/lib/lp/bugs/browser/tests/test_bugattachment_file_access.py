# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import re
from urlparse import (
    parse_qs,
    urlparse,
    )

from lazr.restfulclient.errors import NotFound as RestfulNotFound
import transaction
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.publisher.interfaces import NotFound
from zope.security.interfaces import Unauthorized
from zope.security.management import endInteraction

from lp.bugs.browser.bugattachment import BugAttachmentFileNavigation
from lp.services.librarian.interfaces import ILibraryFileAliasWithParent
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import RedirectionView
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    launchpadlib_for,
    login_person,
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.layers import (
    AppServerLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.pages import LaunchpadWebServiceCaller


class TestAccessToBugAttachmentFiles(TestCaseWithFactory):
    """Tests of traversal to and access of files of bug attachments."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestAccessToBugAttachmentFiles, self).setUp()
        self.bug_owner = self.factory.makePerson()
        getUtility(ILaunchBag).clear()
        login_person(self.bug_owner)
        self.bug = self.factory.makeBug(owner=self.bug_owner)
        self.bugattachment = self.factory.makeBugAttachment(
            bug=self.bug, filename='foo.txt', data='file content')

    def test_traversal_to_lfa_of_bug_attachment(self):
        # Traversing to the URL provided by a ProxiedLibraryFileAlias of a
        # bug attachament returns a RedirectionView.
        request = LaunchpadTestRequest()
        request.setTraversalStack(['foo.txt'])
        navigation = BugAttachmentFileNavigation(
            self.bugattachment, request)
        view = navigation.publishTraverse(request, '+files')
        self.assertIsInstance(view, RedirectionView)

    def test_traversal_to_lfa_of_bug_attachment_wrong_filename(self):
        # If the filename provided in the URL does not match the
        # filename of the LibraryFileAlias, a NotFound error is raised.
        request = LaunchpadTestRequest()
        request.setTraversalStack(['nonsense'])
        navigation = BugAttachmentFileNavigation(self.bugattachment, request)
        self.assertRaises(
            NotFound, navigation.publishTraverse, request, '+files')

    def test_access_to_unrestricted_file(self):
        # Requests of unrestricted files are redirected to Librarian URLs.
        request = LaunchpadTestRequest()
        request.setTraversalStack(['foo.txt'])
        navigation = BugAttachmentFileNavigation(
            self.bugattachment, request)
        view = navigation.publishTraverse(request, '+files')
        mo = re.match('^http://.*/\d+/foo.txt$', view.target)
        self.assertIsNot(None, mo)

    def test_access_to_restricted_file(self):
        # Requests of restricted files are redirected to librarian URLs
        # with tokens.
        lfa_with_parent = getMultiAdapter(
            (self.bugattachment.libraryfile, self.bugattachment),
            ILibraryFileAliasWithParent)
        lfa_with_parent.restricted = True
        self.bug.setPrivate(True, self.bug_owner)
        transaction.commit()
        request = LaunchpadTestRequest()
        request.setTraversalStack(['foo.txt'])
        navigation = BugAttachmentFileNavigation(self.bugattachment, request)
        view = navigation.publishTraverse(request, '+files')
        mo = re.match(
            '^https://.*.restricted.*/\d+/foo.txt\?token=.*$', view.target)
        self.assertIsNot(None, mo)

    def test_access_to_restricted_file_unauthorized(self):
        # If a user cannot access the bug attachment itself, he can neither
        # access the restricted Librarian file.
        lfa_with_parent = getMultiAdapter(
            (self.bugattachment.libraryfile, self.bugattachment),
            ILibraryFileAliasWithParent)
        lfa_with_parent.restricted = True
        self.bug.setPrivate(True, self.bug_owner)
        transaction.commit()
        user = self.factory.makePerson()
        login_person(user)
        self.assertRaises(Unauthorized, getattr, self.bugattachment, 'title')
        request = LaunchpadTestRequest()
        request.setTraversalStack(['foo.txt'])
        navigation = BugAttachmentFileNavigation(self.bugattachment, request)
        self.assertRaises(
            Unauthorized, navigation.publishTraverse, request, '+files')


class TestWebserviceAccessToBugAttachmentFiles(TestCaseWithFactory):
    """Tests access to bug attachments via the webservice."""

    layer = AppServerLayer

    def setUp(self):
        super(TestWebserviceAccessToBugAttachmentFiles, self).setUp()
        self.bug_owner = self.factory.makePerson()
        getUtility(ILaunchBag).clear()
        login_person(self.bug_owner)
        self.bug = self.factory.makeBug(owner=self.bug_owner)
        self.bugattachment = self.factory.makeBugAttachment(
            bug=self.bug, filename='foo.txt', data='file content')

    def test_anon_access_to_public_bug_attachment(self):
        # Attachments of public bugs can be accessed by anonymous users.
        #
        # Need to endInteraction() because launchpadlib_for_anonymous() will
        # setup a new one.
        endInteraction()
        launchpad = launchpadlib_for('test', None, version='devel')
        ws_bug = ws_object(launchpad, self.bug)
        ws_bugattachment = ws_bug.attachments[0]
        self.assertEqual(
            'file content', ws_bugattachment.data.open().read())

    def test_user_access_to_private_bug_attachment(self):
        # Users having access to private bugs can also read attachments
        # of these bugs.
        self.bug.setPrivate(True, self.bug_owner)
        other_user = self.factory.makePerson()
        launchpad = launchpadlib_for('test', self.bug_owner, version='devel')
        ws_bug = ws_object(launchpad, self.bug)
        ws_bugattachment = ws_bug.attachments[0]

        # The attachment contains a link to a HostedBytes resource;
        # the response to a GET request of this URL is a redirect to a
        # Librarian URL.  We cannot simply access these Librarian URLs
        # for restricted Librarian files because the host name used in
        # the URLs is different for each file, and our test envireonment
        # does not support wildcard DNS, and because the Launchpadlib
        # browser automatically follows redirects.
        # LaunchpadWebServiceCaller, on the other hand, gives us
        # access to a raw HTTPResonse object.
        webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')
        response = webservice.get(ws_bugattachment.data._wadl_resource._url)
        self.assertEqual(303, response.status)

        # The Librarian URL has, for our test case, the form
        # "https://NNNN.restricted.launchpad.dev:PORT/NNNN/foo.txt?token=..."
        # where NNNN and PORT are integers.
        parsed_url = urlparse(response.getHeader('location'))
        self.assertEqual('https', parsed_url.scheme)
        mo = re.search(
            r'^i\d+\.restricted\..+:\d+$', parsed_url.netloc)
        self.assertIsNot(None, mo, parsed_url.netloc)
        mo = re.search(r'^/\d+/foo\.txt$', parsed_url.path)
        self.assertIsNot(None, mo)
        params = parse_qs(parsed_url.query)
        self.assertEqual(['token'], params.keys())

        # If a user which cannot access the private bug itself tries to
        # to access the attachment, an NotFound error is raised.
        other_launchpad = launchpadlib_for(
            'test_unauthenticated', other_user, version='devel')
        self.assertRaises(
            RestfulNotFound, other_launchpad._browser.get,
            ws_bugattachment.data._wadl_resource._url)
