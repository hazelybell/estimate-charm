# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for BranchURIField."""

__metaclass__ = type

from lp.app.validators import LaunchpadValidationError
from lp.code.interfaces.branch import (
    BranchURIField,
    get_blacklisted_hostnames,
    )
from lp.services.config import config
from lp.services.webapp.vhosts import allvhosts
from lp.testing import TestCase
from lp.testing.layers import LaunchpadZopelessLayer


class TestBranchURIField(TestCase):
    """Test the validation logic for Branch URI fields.

    Users can register their external Bazaar branches on Launchpad by
    providing a URI. Launchpad will then attempt to mirror those branches.

    Many valid URIs are not valid branch URIs. In particular, anything URI
    that points to Launchpad is invalid, because all of the URIs for branches
    on Launchpad are generated from database fields and are thus subject to
    change. Further, branches cannot be on the root of a site, nor are users
    allowed to register a branch that is already being mirrored.
    """
    layer = LaunchpadZopelessLayer

    def setUp(self):
        TestCase.setUp(self)
        self.field = BranchURIField()

    def listLaunchpadDomains(self):
        """Iterate over each of the configured domains of Launchpad."""
        mainsite = allvhosts.configs['mainsite'].hostname
        for vhost in allvhosts.configs.values():
            if vhost.hostname.endswith(mainsite):
                yield vhost.hostname

    def assertInvalid(self, uri):
        """Assert the given URL is considered invalid by BranchURIField."""
        self.assertRaises(LaunchpadValidationError, self.field.validate, uri)

    def test_notFromSupermirror(self):
        # Branches on the supermirror are already registered, so there is no
        # need to register them, again.
        self.assertInvalid(
            u'%s/~user/+junk/branch' % config.codehosting.supermirror_root)

    def test_notFromLaunchpad(self):
        # URIs from Launchpad itself are invalid, no matter what the
        # subdomain.
        for domain in self.listLaunchpadDomains():
            self.assertInvalid(u'http://%s/user/+junk/branch' % domain)

    def test_get_blacklisted_hostnames(self):
        self.pushConfig(
            'codehosting', blacklisted_hostnames='localhost,127.0.0.1')
        self.assertEqual(
            ['localhost', '127.0.0.1'], get_blacklisted_hostnames())

    def test_get_blacklisted_hostnames_empty(self):
        self.assertEqual([], get_blacklisted_hostnames())

    def test_notFromBlacklistedHostnames(self):
        # URIs with hosts in config.codehosting.blacklisted_hostnames are not
        # allowed to be registered.
        self.pushConfig(
            'codehosting', blacklisted_hostnames='localhost,127.0.0.1')
        self.assertInvalid(u'http://localhost/foo/bar')
        self.assertInvalid(u'http://127.0.0.1/foo/bar')
