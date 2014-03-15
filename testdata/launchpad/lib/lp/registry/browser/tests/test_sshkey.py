# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for GPG key on the web."""

__metaclass__ = type

from zope.component import getUtility

from lp.registry.interfaces.ssh import ISSHKeySet
from lp.services.webapp import canonical_url
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tags_by_class,
    setupBrowserFreshLogin,
    )
from lp.testing.views import create_initialized_view


class TestCanonicalUrl(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_canonical_url(self):
        # The canonical URL of a GPG key is ssh-keys
        person = self.factory.makePerson()
        with person_logged_in(person):
            sshkey = self.factory.makeSSHKey(person)
            self.assertEqual(
                '%s/+ssh-keys/%s' % (
                    canonical_url(person, rootsite='api'), sshkey.id),
                canonical_url(sshkey))


class TestSSHKeyView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_escaped_message_when_removing_key(self):
        """Confirm that messages are escaped when removing keys."""
        person = self.factory.makePerson()
        url = '%s/+editsshkeys' % canonical_url(person)
        public_key = "ssh-rsa %s x<script>alert()</script>example.com" % (
            self.getUniqueString())
        with person_logged_in(person):
            # Add the key for the user here,
            # since we only care about testing removal.
            getUtility(ISSHKeySet).new(person, public_key)
            browser = setupBrowserFreshLogin(person)
            browser.open(url)
            browser.getControl('Remove').click()
            msg = 'Key "x&lt;script&gt;alert()&lt;/script&gt;example.com" removed'
            self.assertEqual(
                extract_text(find_tags_by_class(browser.contents, 'message')[0]),
                msg)

    def test_edit_ssh_keys_login_redirect(self):
        """+editsshkeys should redirect to force you to re-authenticate."""
        person = self.factory.makePerson()
        login_person(person)
        view = create_initialized_view(person, "+editsshkeys")
        response = view.request.response
        self.assertEqual(302, response.getStatus())
        expected_url = (
            '%s/+editsshkeys/+login?reauth=1' % canonical_url(person))
        self.assertEqual(expected_url, response.getHeader('location'))
