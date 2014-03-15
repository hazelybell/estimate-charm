# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for the public codehosting API."""

__metaclass__ = type

import os
import xmlrpclib

from bzrlib import urlutils
from lazr.uri import URI
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.enums import BranchType
from lp.code.interfaces.codehosting import BRANCH_ALIAS_PREFIX
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.code.xmlrpc.branch import PublicCodehostingAPI
from lp.services.xmlrpc import LaunchpadFault
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.xmlrpc import faults


NON_ASCII_NAME = u'nam\N{LATIN SMALL LETTER E WITH ACUTE}'


class TestExpandURL(TestCaseWithFactory):
    """Test the way that URLs are expanded."""

    layer = DatabaseFunctionalLayer

    def makeProdutWithTrunk(self):
        """Make a new project with a trunk hosted branch."""
        product = self.factory.makeProduct()
        # BranchType is only signficiant insofar as it is not a REMOTE branch.
        trunk = self.factory.makeProductBranch(
            branch_type=BranchType.HOSTED, product=product)
        with person_logged_in(product.owner):
            ICanHasLinkedBranch(product).setBranch(trunk)
        return product, trunk

    def assertResolves(self, lp_url_path, public_branch_path, lp_path=None):
        """Assert that `lp_url_path` resolves to the specified paths.

        :param public_branch_path: The path that is accessible over http.
        :param lp_path: The short branch alias that will be resolved over
            bzr+ssh.  The branch alias prefix is prefixed to this path.
            If it is not set, the bzr+ssh resolved name will be checked
            against the public_branch_path instead.
        """
        api = PublicCodehostingAPI(None, None)
        results = api.resolve_lp_path(lp_url_path)
        if lp_path is None:
            ssh_branch_path = public_branch_path
        else:
            if lp_path.startswith('~'):
                ssh_branch_path = lp_path
            else:
                ssh_branch_path = '%s/%s' % (BRANCH_ALIAS_PREFIX, lp_path)
        # This improves the error message if results happens to be a fault.
        if isinstance(results, LaunchpadFault):
            raise results
        for url in results['urls']:
            uri = URI(url)
            if uri.scheme == 'http':
                self.assertEqual('/' + public_branch_path, uri.path)
            else:
                self.assertEqual('/' + ssh_branch_path, uri.path)

    def assertOnlyWritableResolves(self, lp_url_path):
        """Only the bzr+ssh url is returned."""
        self.assertResolves(lp_url_path, None, lp_url_path)

    def assertFault(self, lp_url_path, expected_fault):
        """Trying to resolve lp_url_path raises the expected fault."""
        api = PublicCodehostingAPI(None, None)
        fault = api.resolve_lp_path(lp_url_path)
        self.assertTrue(
            isinstance(fault, xmlrpclib.Fault),
            "resolve_lp_path(%r) returned %r, not a Fault."
            % (lp_url_path, fault))
        self.assertEqual(expected_fault.__class__, fault.__class__)
        self.assertEqual(expected_fault.faultString, fault.faultString)
        return fault

    def test_resultDict(self):
        # A given lp url path maps to a single branch available from a number
        # of URLs (mostly varying by scheme). resolve_lp_path returns a dict
        # containing a list of these URLs, with the faster and more featureful
        # URLs earlier in the list. We use a dict so we can easily add more
        # information in the future.
        product, trunk = self.makeProdutWithTrunk()
        api = PublicCodehostingAPI(None, None)
        results = api.resolve_lp_path(product.name)
        urls = [
            'bzr+ssh://bazaar.launchpad.dev/+branch/%s' % product.name,
            'http://bazaar.launchpad.dev/%s' % trunk.unique_name]
        self.assertEqual(dict(urls=urls), results)

    def test_resultDictForHotProduct(self):
        # If 'project-name' is in the config.codehosting.hot_products list,
        # lp:project-name will only resolve to the http url.
        product, trunk = self.makeProdutWithTrunk()
        self.pushConfig('codehosting', hot_products=product.name)
        api = PublicCodehostingAPI(None, None)
        results = api.resolve_lp_path(product.name)
        http_url = 'http://bazaar.launchpad.dev/%s' % trunk.unique_name
        self.assertEqual(dict(urls=[http_url]), results)

    def test_product_only(self):
        # lp:product expands to the branch associated with development focus
        # of the product for the anonymous public access, just to the aliased
        # short name for bzr+ssh access.
        product, trunk = self.makeProdutWithTrunk()
        lp_path = product.name
        self.assertResolves(lp_path, trunk.unique_name, lp_path)

    def test_product_explicit_dev_series(self):
        # lp:product/development_focus expands to the branch associated with
        # development focus of the product for the anonymous public access,
        # just to the aliased short name for bzr+ssh access.
        product, trunk = self.makeProdutWithTrunk()
        lp_path = '%s/%s' % (product.name, product.development_focus.name)
        self.assertResolves(lp_path, trunk.unique_name, lp_path)

    def test_target_doesnt_exist(self):
        # The resolver doesn't care if the product exists or not.
        self.assertOnlyWritableResolves('doesntexist')
        self.assertOnlyWritableResolves('doesntexist/trunk')

    def test_product_and_series(self):
        # lp:product/series expands to the writable alias for product/series
        # and to the branch associated with the product series 'series' on
        # 'product'.
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product)
        series = self.factory.makeProductSeries(
            product=product, branch=branch)
        lp_path = '%s/%s' % (product.name, series.name)
        self.assertResolves(lp_path, branch.unique_name, lp_path)

    def test_development_focus_has_no_branch(self):
        # A product with no trunk resolves to the writable alias.
        product = self.factory.makeProduct()
        self.assertOnlyWritableResolves(product.name)

    def test_series_has_no_branch(self):
        # A series with no branch resolves to the writable alias.
        series = self.factory.makeProductSeries(branch=None)
        self.assertOnlyWritableResolves(
            '%s/%s' % (series.product.name, series.name))

    def test_no_such_product_series_non_ascii(self):
        # lp:product/<non-ascii-string> resolves to the branch alias with the
        # name escaped.
        product = self.factory.makeProduct()
        lp_path = '%s/%s' % (product.name, NON_ASCII_NAME)
        escaped_name = urlutils.escape(lp_path)
        self.assertResolves(lp_path, None, escaped_name)

    def test_branch(self):
        # The unique name of a branch resolves to the unique name of the
        # branch.
        branch = self.factory.makeAnyBranch()
        self.assertResolves(branch.unique_name, branch.unique_name)

    def test_trunk_accessed_as_branch(self):
        # A branch that is the development focus for any product can also be
        # accessed through the branch's unique_name.
        _ignored, trunk = self.makeProdutWithTrunk()
        self.assertResolves(trunk.unique_name, trunk.unique_name)

    def test_mirrored_branch(self):
        # The unique name of a mirrored branch resolves to the unique name of
        # the branch.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        self.assertResolves(branch.unique_name, branch.unique_name)

    def test_no_such_branch_product(self):
        # Resolve paths to branches even if there is no branch of that name.
        # We do this so that users can push new branches to lp: URLs.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        nonexistent_branch = '~%s/%s/doesntexist' % (
            owner.name, product.name)
        self.assertResolves(nonexistent_branch, nonexistent_branch)

    def test_no_such_branch_product_non_ascii(self):
        # A path to a branch that contains non ascii characters will never
        # find a branch, but it still resolves rather than erroring.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        nonexistent_branch = u'~%s/%s/%s' % (
            owner.name, product.name, NON_ASCII_NAME)
        self.assertResolves(
            nonexistent_branch, urlutils.escape(nonexistent_branch))

    def test_no_such_branch_personal(self):
        # Resolve paths to junk branches.
        # This test added to make sure we don't raise a fault when looking for
        # the '+junk' project, which doesn't actually exist.
        owner = self.factory.makePerson()
        nonexistent_branch = '~%s/+junk/doesntexist' % owner.name
        self.assertResolves(nonexistent_branch, nonexistent_branch)

    def test_no_such_branch_package(self):
        # Resolve paths to package branches even if there's no branch of that
        # name, so that we can push new branches using lp: URLs.
        owner = self.factory.makePerson()
        sourcepackage = self.factory.makeSourcePackage()
        nonexistent_branch = '~%s/%s/doesntexist' % (
            owner.name, sourcepackage.path)
        self.assertResolves(nonexistent_branch, nonexistent_branch)

    def test_resolve_branch_with_no_such_product(self):
        # If we try to resolve a branch that refers to a non-existent product,
        # then we return a NoSuchProduct fault.
        owner = self.factory.makePerson()
        nonexistent_product_branch = "~%s/doesntexist/%s" % (
            owner.name, self.factory.getUniqueString())
        self.assertFault(
            nonexistent_product_branch, faults.NoSuchProduct('doesntexist'))

    def test_resolve_branch_with_no_such_owner(self):
        # If we try to resolve a branch that refers to a non-existent owner,
        # then we return a NoSuchPerson fault.
        nonexistent_owner_branch = "~doesntexist/%s/%s" % (
            self.factory.getUniqueString(), self.factory.getUniqueString())
        self.assertFault(
            nonexistent_owner_branch,
            faults.NoSuchPersonWithName('doesntexist'))

    def test_resolve_branch_with_no_such_owner_non_ascii(self):
        # lp:~<non-ascii-string>/product/name returns NoSuchPersonWithName
        # with the name escaped.
        nonexistent_owner_branch = u"~%s/%s/%s" % (
            NON_ASCII_NAME, self.factory.getUniqueString(),
            self.factory.getUniqueString())
        self.assertFault(
            nonexistent_owner_branch,
            faults.NoSuchPersonWithName(urlutils.escape(NON_ASCII_NAME)))

    def test_too_many_segments(self):
        # If we have more segments than are necessary to refer to a branch,
        # then attach these segments to the resolved url.
        # We do this so that users can do operations like 'bzr cat
        # lp:path/to/branch/README.txt'.
        arbitrary_branch = self.factory.makeAnyBranch()
        longer_path = os.path.join(arbitrary_branch.unique_name, 'qux')
        self.assertResolves(longer_path, longer_path)

    def test_too_many_segments_no_such_branch(self):
        # If we have more segments than are necessary to refer to a branch,
        # then attach these segments to the resolved url, even if there is no
        # branch corresponding to the start of the URL.
        # This means the users will probably get a normal Bazaar 'no such
        # branch' error when they try a command like 'bzr cat
        # lp:path/to/branch/README.txt', which probably is the least
        # surprising thing that we can do.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch_name = self.factory.getUniqueString()
        extra_path = self.factory.getUniqueString()
        longer_path = os.path.join(
            '~' + person.name, product.name, branch_name, extra_path)
        self.assertResolves(longer_path, longer_path)

    def test_empty_path(self):
        # An empty path is an invalid identifier.
        self.assertFault('', faults.InvalidBranchIdentifier(''))

    def test_too_short(self):
        # Return a nice fault if the unique name is too short.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = '%s/%s' % (owner.name, product.name)
        self.assertFault('~' + path, faults.InvalidBranchUniqueName(path))

    def test_all_slashes(self):
        # A path of all slashes is an invalid identifier.
        self.assertFault('///', faults.InvalidBranchIdentifier('///'))

    def test_trailing_slashes(self):
        # Trailing slashes are trimmed.
        # Trailing slashes on lp:product//
        product, trunk = self.makeProdutWithTrunk()
        self.assertResolves(
            product.name + '/', trunk.unique_name, product.name)
        self.assertResolves(
            product.name + '//', trunk.unique_name, product.name)

        # Trailing slashes on lp:~owner/product/branch//
        branch = self.factory.makeAnyBranch()
        self.assertResolves(branch.unique_name + '/', branch.unique_name)
        self.assertResolves(branch.unique_name + '//', branch.unique_name)

    def test_private_branch(self):
        # Invisible branches are resolved as if they didn't exist, so that we
        # reveal the least possile amount of information about them.
        # For fully specified branch names, this means resolving the lp url.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        # Removing security proxy to get at the unique_name attribute of a
        # private branch, and tests are currently running as an anonymous
        # user.
        unique_name = removeSecurityProxy(branch).unique_name
        self.assertOnlyWritableResolves(unique_name)

    def test_private_branch_on_series(self):
        # We resolve private linked branches using the writable alias.
        #
        # Removing security proxy because we need to be able to get at
        # attributes of a private branch and these tests are running as an
        # anonymous user.
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        series = self.factory.makeProductSeries(branch=branch)
        lp_path = '%s/%s' % (series.product.name, series.name)
        self.assertOnlyWritableResolves(lp_path)

    def test_private_branch_as_development_focus(self):
        # We resolve private linked branches using the writable alias.
        product, trunk = self.makeProdutWithTrunk()
        removeSecurityProxy(trunk).information_type = (
            InformationType.USERDATA)
        self.assertOnlyWritableResolves(product.name)

    def test_private_branch_as_user(self):
        # We resolve private branches as if they don't exist.
        #
        # References to a product resolve to the branch associated with the
        # development focus. If that branch is private, other views will
        # indicate that there is no branch on the development focus. We do the
        # same.
        #
        # Create the owner explicitly so that we can get its email without
        # resorting to removeSecurityProxy.
        owner = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            owner=owner, information_type=InformationType.USERDATA)
        path = removeSecurityProxy(branch).unique_name
        self.assertOnlyWritableResolves(path)

    def test_remote_branch(self):
        # For remote branches, return results that link to the actual remote
        # branch URL.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.REMOTE)
        api = PublicCodehostingAPI(None, None)
        result = api.resolve_lp_path(branch.unique_name)
        self.assertEqual([branch.url], result['urls'])

    def test_remote_branch_no_url(self):
        # Raise a Fault for remote branches with no URL.
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.REMOTE, url=None)
        self.assertFault(
            branch.unique_name,
            faults.NoUrlForBranch(branch.unique_name))
