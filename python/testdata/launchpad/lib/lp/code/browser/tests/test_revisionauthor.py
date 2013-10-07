# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests related to `RevisionAuthor`."""

__metaclass__ = type

from lp.app.browser.tales import (
    PersonFormatterAPI,
    RevisionAuthorFormatterAPI,
    )
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.sampledata import USER_EMAIL


class TestRevisionAuthorFormatterAPI(TestCaseWithFactory):
    """Test `RevisionAuthor` link formatter."""

    layer = DatabaseFunctionalLayer

    def _formatAuthorLink(self, revision):
        """Format a link to `revision`'s author."""
        return RevisionAuthorFormatterAPI(revision.revision_author).link()

    def test_link_links_to_person_if_known(self):
        # When a RevisionAuthor is coupled to a Person, the link
        # formatter simply links to the Person.
        author = self.factory.makePerson()
        revision = self.factory.makeRevision(author=author)
        self.assertEqual(
            PersonFormatterAPI(author).link(None),
            self._formatAuthorLink(revision))

    def test_link_shows_name(self):
        # When a RevisionAuthor is not coupled to a Person but does have
        # a name attached to it, the link formatter shows the name.
        revision = self.factory.makeRevision(author="J.R. Hacker")
        self.assertEqual("J.R. Hacker", self._formatAuthorLink(revision))

    def test_link_shows_email_if_necessary(self):
        # If nothing else is available, the author link will show the
        # author's email address.
        login(USER_EMAIL)
        email = "%s@example.com" % self.factory.getUniqueString()
        revision = self.factory.makeRevision(author=email)
        self.assertEqual(email, self._formatAuthorLink(revision))

    def test_link_name_trumps_email(self):
        # If both a name and an email address are available, the email
        # address is not shown.
        name = self.factory.getUniqueString()
        email = "%s@example.com" % self.factory.getUniqueString()
        full_email = "%s <%s>" % (name, email)
        revision = self.factory.makeRevision(author=full_email)
        self.assertEqual(name, self._formatAuthorLink(revision))

    def test_email_is_never_shown_to_anonymous_users(self):
        # Even if only an email address is available, it will not be
        # shown to anonymous users.
        account = self.factory.getUniqueString()
        email = "%s@example.com" % account
        revision = self.factory.makeRevision(author=email)
        self.assertNotIn(account, self._formatAuthorLink(revision))
        self.assertNotIn('@', self._formatAuthorLink(revision))

    def test_empty_string_when_name_and_email_are_none(self):
        # When the RevisionAuthor name and email attrs are None, an
        # empty string is returned.
        revision = self.factory.makeRevision(author='')
        login(USER_EMAIL)
        self.assertEqual('', self._formatAuthorLink(revision))

    def test_name_is_escaped(self):
        # The author's name is HTML-escaped.
        revision = self.factory.makeRevision(author="apples & pears")
        self.assertEqual(
            "apples &amp; pears", self._formatAuthorLink(revision))

    def test_email_is_escaped(self):
        # The author's email address is HTML-escaped.
        login(USER_EMAIL)
        raw_email = "a&b@example.com"
        escaped_email = "a&amp;b@example.com"
        revision = self.factory.makeRevision(author=raw_email)
        self.assertEqual(escaped_email, self._formatAuthorLink(revision))
