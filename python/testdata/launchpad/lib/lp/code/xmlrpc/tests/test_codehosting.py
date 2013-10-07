# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the internal codehosting API."""

__metaclass__ = type

import datetime
import os
import unittest

from bzrlib import bzrdir
from bzrlib.tests import multiply_tests
from bzrlib.urlutils import escape
import pytz
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.errors import NotFoundError
from lp.code.bzr import (
    BranchFormat,
    ControlFormat,
    RepositoryFormat,
    )
from lp.code.enums import BranchType
from lp.code.errors import UnknownBranchTypeError
from lp.code.interfaces.branch import BRANCH_NAME_VALIDATION_ERROR_MESSAGE
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codehosting import (
    BRANCH_ALIAS_PREFIX,
    branch_id_alias,
    BRANCH_ID_ALIAS_PREFIX,
    BRANCH_TRANSPORT,
    CONTROL_TRANSPORT,
    )
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.code.model.tests.test_branchpuller import AcquireBranchToPullTests
from lp.code.xmlrpc.codehosting import (
    CodehostingAPI,
    LAUNCHPAD_ANONYMOUS,
    LAUNCHPAD_SERVICES,
    run_with_login,
    )
from lp.codehosting.inmemory import InMemoryFrontend
from lp.services.database.constants import UTC_NOW
from lp.services.scripts.interfaces.scriptactivity import IScriptActivitySet
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.xmlrpc import faults


UTC = pytz.timezone('UTC')


def get_logged_in_username(requester=None):
    """Return the username of the logged in person.

    Used by `TestRunWithLogin`.
    """
    user = getUtility(ILaunchBag).user
    if user is None:
        return None
    return user.name


class TestRunWithLogin(TestCaseWithFactory):
    """Tests for the `run_with_login` decorator."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestRunWithLogin, self).setUp()
        self.person = self.factory.makePerson()

    def test_loginAsRequester(self):
        # run_with_login logs in as user given as the first argument
        # to the method being decorated.
        username = run_with_login(self.person.id, get_logged_in_username)
        # person.name is a protected field so we must be logged in before
        # attempting to access it.
        login(ANONYMOUS)
        self.assertEqual(self.person.name, username)
        logout()

    def test_loginAsRequesterName(self):
        # run_with_login can take a username as well as user id.
        username = run_with_login(self.person.name, get_logged_in_username)
        login(ANONYMOUS)
        self.assertEqual(self.person.name, username)
        logout()

    def test_logoutAtEnd(self):
        # run_with_login logs out once the decorated method is
        # finished.
        run_with_login(self.person.id, get_logged_in_username)
        self.assertEqual(None, get_logged_in_username())

    def test_logoutAfterException(self):
        # run_with_login logs out even if the decorated method raises
        # an exception.
        def raise_exception(requester, exc_factory, *args):
            raise exc_factory(*args)
        self.assertRaises(
            RuntimeError, run_with_login, self.person.id, raise_exception,
            RuntimeError, 'error message')
        self.assertEqual(None, get_logged_in_username())

    def test_passesRequesterInAsPerson(self):
        # run_with_login passes in the Launchpad Person object of the
        # requesting user.
        user = run_with_login(self.person.id, lambda x: x)
        login(ANONYMOUS)
        self.assertEqual(self.person.name, user.name)
        logout()

    def test_invalidRequester(self):
        # A method wrapped with run_with_login raises NotFoundError if
        # there is no person with the passed in id.
        self.assertRaises(
            NotFoundError, run_with_login, -1, lambda x: None)

    def test_cheatsForLaunchpadServices(self):
        # Various Launchpad services need to use the authserver to get
        # information about branches, unencumbered by petty
        # restrictions of ownership or privacy. `run_with_login`
        # detects the special username `LAUNCHPAD_SERVICES` and passes
        # that through to the decorated function without logging in.
        username = run_with_login(LAUNCHPAD_SERVICES, lambda x: x)
        self.assertEqual(LAUNCHPAD_SERVICES, username)
        login_id = run_with_login(LAUNCHPAD_SERVICES, get_logged_in_username)
        self.assertEqual(None, login_id)


class CodehostingTest(TestCaseWithFactory):
    """Tests for the implementation of `ICodehostingAPI`.

    :ivar frontend: A nullary callable that returns an object that implements
        getCodehostingEndpoint, getLaunchpadObjectFactory and getBranchLookup.
    """

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        frontend = self.frontend()
        self.codehosting_api = frontend.getCodehostingEndpoint()
        self.factory = frontend.getLaunchpadObjectFactory()
        self.branch_lookup = frontend.getBranchLookup()
        self.getLastActivity = frontend.getLastActivity

    def assertMirrorFailed(self, branch, failure_message, num_failures=1):
        """Assert that `branch` failed to mirror.

        :param branch: The branch that failed to mirror.
        :param failure_message: The last message that the branch failed with.
        :param num_failures: The number of times this branch has failed to
            mirror. Defaults to one.
        """
        self.assertSqlAttributeEqualsDate(
            branch, 'last_mirror_attempt', UTC_NOW)
        self.assertIs(None, branch.last_mirrored)
        self.assertEqual(num_failures, branch.mirror_failures)
        self.assertEqual(failure_message, branch.mirror_status_message)

    def assertMirrorSucceeded(self, branch, revision_id):
        """Assert that `branch` mirrored to `revision_id`."""
        self.assertSqlAttributeEqualsDate(
            branch, 'last_mirror_attempt', UTC_NOW)
        self.assertSqlAttributeEqualsDate(
            branch, 'last_mirrored', UTC_NOW)
        self.assertEqual(0, branch.mirror_failures)
        self.assertEqual(revision_id, branch.last_mirrored_id)

    def assertUnmirrored(self, branch):
        """Assert that `branch` has not yet been mirrored.

        Asserts that last_mirror_attempt, last_mirrored and
        mirror_status_message are all None, and that mirror_failures is 0.
        """
        self.assertIs(None, branch.last_mirror_attempt)
        self.assertIs(None, branch.last_mirrored)
        self.assertEqual(0, branch.mirror_failures)
        self.assertIs(None, branch.mirror_status_message)

    def getUnusedBranchID(self):
        """Return a branch ID that isn't in the database."""
        branch_id = 999
        # We can't be sure until the sample data is gone.
        self.assertIs(self.branch_lookup.get(branch_id), None)
        return branch_id

    def test_mirrorFailed(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        self.assertUnmirrored(branch)

        branch.requestMirror()
        self.assertEquals(
            branch.id, self.codehosting_api.acquireBranchToPull([])[0])

        failure_message = self.factory.getUniqueString()
        success = self.codehosting_api.mirrorFailed(
            branch.id, failure_message)
        self.assertEqual(True, success)
        self.assertMirrorFailed(branch, failure_message)

    def test_mirrorFailedWithNotBranchID(self):
        branch_id = self.getUnusedBranchID()
        failure_message = self.factory.getUniqueString()
        fault = self.codehosting_api.mirrorFailed(branch_id, failure_message)
        self.assertEqual(faults.NoBranchWithID(branch_id), fault)

    def test_recordSuccess(self):
        # recordSuccess must insert the given data into ScriptActivity.
        started = datetime.datetime(2007, 07, 05, 19, 32, 1, tzinfo=UTC)
        completed = datetime.datetime(2007, 07, 05, 19, 34, 24, tzinfo=UTC)
        started_tuple = tuple(started.utctimetuple())
        completed_tuple = tuple(completed.utctimetuple())
        success = self.codehosting_api.recordSuccess(
            'test-recordsuccess', 'server-name',
            started_tuple, completed_tuple)
        self.assertEqual(True, success)

        activity = self.getLastActivity('test-recordsuccess')
        self.assertEqual('server-name', activity.hostname)
        self.assertEqual(started, activity.date_started)
        self.assertEqual(completed, activity.date_completed)

    def test_createBranch(self):
        # createBranch creates a branch with the supplied details and the
        # caller as registrant.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        name = self.factory.getUniqueString()
        branch_id = self.codehosting_api.createBranch(
            owner.id, escape('/~%s/%s/%s' % (owner.name, product.name, name)))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(owner, branch.owner)
        self.assertEqual(product, branch.product)
        self.assertEqual(name, branch.name)
        self.assertEqual(owner, branch.registrant)
        self.assertEqual(BranchType.HOSTED, branch.branch_type)

    def test_createBranch_no_preceding_slash(self):
        requester = self.factory.makePerson()
        path = escape(u'invalid')
        fault = self.codehosting_api.createBranch(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(faults.InvalidPath(path), fault)

    def test_createBranch_junk(self):
        # createBranch can create +junk branches.
        owner = self.factory.makePerson()
        name = self.factory.getUniqueString()
        branch_id = self.codehosting_api.createBranch(
            owner.id, escape('/~%s/%s/%s' % (owner.name, '+junk', name)))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(owner, branch.owner)
        self.assertEqual(None, branch.product)
        self.assertEqual(name, branch.name)
        self.assertEqual(owner, branch.registrant)
        self.assertEqual(BranchType.HOSTED, branch.branch_type)

    def test_createBranch_team_junk(self):
        # createBranch can create +junk branches on teams.
        registrant = self.factory.makePerson()
        team = self.factory.makeTeam(registrant)
        name = self.factory.getUniqueString()
        branch_id = self.codehosting_api.createBranch(
            registrant.id, escape('/~%s/+junk/%s' % (team.name, name)))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(team, branch.owner)
        self.assertEqual(None, branch.product)
        self.assertEqual(name, branch.name)
        self.assertEqual(registrant, branch.registrant)
        self.assertEqual(BranchType.HOSTED, branch.branch_type)

    def test_createBranch_bad_product(self):
        # Creating a branch for a non-existant product fails.
        owner = self.factory.makePerson()
        name = self.factory.getUniqueString()
        message = "Project 'no-such-product' does not exist."
        fault = self.codehosting_api.createBranch(
            owner.id, escape('/~%s/no-such-product/%s' % (owner.name, name)))
        self.assertEqual(faults.NotFound(message), fault)

    def test_createBranch_invalid_product(self):
        # Creating a branch with an invalid product name fails.
        owner = self.factory.makePerson()
        name = self.factory.getUniqueString()
        from lp.code.interfaces.codehosting import BRANCH_ALIAS_PREFIX
        branch_name = "/%s/fiz:buzz/%s" % (BRANCH_ALIAS_PREFIX, name)
        fault = self.codehosting_api.createBranch(
            owner.id, branch_name)
        self.assertEqual(faults.InvalidProductName(escape('fiz:buzz')), fault)

    def test_createBranch_other_user(self):
        # Creating a branch under another user's directory fails.
        creator = self.factory.makePerson()
        other_person = self.factory.makePerson()
        product = self.factory.makeProduct()
        name = self.factory.getUniqueString()
        message = ("%s cannot create branches owned by %s"
                   % (creator.displayname, other_person.displayname))
        fault = self.codehosting_api.createBranch(
            creator.id,
            escape('/~%s/%s/%s' % (other_person.name, product.name, name)))
        self.assertEqual(faults.PermissionDenied(message), fault)

    def test_createBranch_bad_name(self):
        # Creating a branch with an invalid name fails.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        invalid_name = 'invalid name!'
        # LaunchpadValidationError unfortunately assumes its output is
        # always HTML, so it ends up double-escaped in XML-RPC faults.
        message = html_escape(
            "Invalid branch name '%s'. %s"
            % (invalid_name, BRANCH_NAME_VALIDATION_ERROR_MESSAGE))
        fault = self.codehosting_api.createBranch(
            owner.id, escape(
                '/~%s/%s/%s' % (owner.name, product.name, invalid_name)))
        self.assertEqual(faults.PermissionDenied(message), fault)

    def test_createBranch_unicode_name(self):
        # Creating a branch with an invalid name fails.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        invalid_name = u'invalid\N{LATIN SMALL LETTER E WITH ACUTE}'
        # LaunchpadValidationError unfortunately assumes its output is
        # always HTML, so it ends up double-escaped in XML-RPC faults.
        message = html_escape(
            "Invalid branch name '%s'. %s"
            % (invalid_name, BRANCH_NAME_VALIDATION_ERROR_MESSAGE)
            ).encode('utf-8')
        fault = self.codehosting_api.createBranch(
            owner.id, escape(
                '/~%s/%s/%s' % (owner.name, product.name, invalid_name)))
        self.assertEqual(
            faults.PermissionDenied(message), fault)

    def test_createBranch_bad_user(self):
        # Creating a branch under a non-existent user fails.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        name = self.factory.getUniqueString()
        message = "User/team 'no-one' does not exist."
        fault = self.codehosting_api.createBranch(
            owner.id, escape('/~no-one/%s/%s' % (product.name, name)))
        self.assertEqual(faults.NotFound(message), fault)

    def test_createBranch_bad_user_bad_product(self):
        # If both the user and the product are not found, then the missing
        # user "wins" the error reporting race (as the url reads
        # ~user/product/branch).
        owner = self.factory.makePerson()
        name = self.factory.getUniqueString()
        message = "User/team 'no-one' does not exist."
        fault = self.codehosting_api.createBranch(
            owner.id, escape('/~no-one/no-product/%s' % (name,)))
        self.assertEqual(faults.NotFound(message), fault)

    def test_createBranch_not_branch(self):
        # Trying to create a branch at a path that's not valid for branches
        # raises a PermissionDenied fault.
        owner = self.factory.makePerson()
        path = escape('/~%s' % owner.name)
        fault = self.codehosting_api.createBranch(owner.id, path)
        message = "Cannot create branch at '%s'" % path
        self.assertEqual(faults.PermissionDenied(message), fault)

    def test_createBranch_source_package(self):
        # createBranch can take the path to a source package branch and create
        # it with all the right attributes.
        owner = self.factory.makePerson()
        sourcepackage = self.factory.makeSourcePackage()
        branch_name = self.factory.getUniqueString()
        unique_name = '/~%s/%s/%s/%s/%s' % (
            owner.name,
            sourcepackage.distribution.name,
            sourcepackage.distroseries.name,
            sourcepackage.sourcepackagename.name,
            branch_name)
        branch_id = self.codehosting_api.createBranch(
            owner.id, escape(unique_name))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(owner, branch.owner)
        self.assertEqual(sourcepackage.distroseries, branch.distroseries)
        self.assertEqual(
            sourcepackage.sourcepackagename, branch.sourcepackagename)
        self.assertEqual(branch_name, branch.name)
        self.assertEqual(owner, branch.registrant)
        self.assertEqual(BranchType.HOSTED, branch.branch_type)

    def test_createBranch_invalid_distro(self):
        # If createBranch is called with the path to a non-existent distro, it
        # will return a Fault saying so in plain English.
        owner = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        sourcepackagename = self.factory.makeSourcePackageName()
        branch_name = self.factory.getUniqueString()
        unique_name = '/~%s/ningnangnong/%s/%s/%s' % (
            owner.name, distroseries.name, sourcepackagename.name,
            branch_name)
        fault = self.codehosting_api.createBranch(
            owner.id, escape(unique_name))
        message = "No such distribution: 'ningnangnong'."
        self.assertEqual(faults.NotFound(message), fault)

    def test_createBranch_invalid_distroseries(self):
        # If createBranch is called with the path to a non-existent
        # distroseries, it will return a Fault saying so.
        owner = self.factory.makePerson()
        distribution = self.factory.makeDistribution()
        sourcepackagename = self.factory.makeSourcePackageName()
        branch_name = self.factory.getUniqueString()
        unique_name = '/~%s/%s/ningnangnong/%s/%s' % (
            owner.name, distribution.name, sourcepackagename.name,
            branch_name)
        fault = self.codehosting_api.createBranch(
            owner.id, escape(unique_name))
        message = "No such distribution series: 'ningnangnong'."
        self.assertEqual(faults.NotFound(message), fault)

    def test_createBranch_missing_sourcepackagename(self):
        # If createBranch is called with the path to a missing source
        # package, it will create the source package.
        owner = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        branch_name = self.factory.getUniqueString()
        unique_name = '/~%s/%s/%s/ningnangnong/%s' % (
            owner.name, distroseries.distribution.name, distroseries.name,
            branch_name)
        branch_id = self.codehosting_api.createBranch(
            owner.id, escape(unique_name))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(owner, branch.owner)
        self.assertEqual(distroseries, branch.distroseries)
        self.assertEqual(
            'ningnangnong', branch.sourcepackagename.name)
        self.assertEqual(branch_name, branch.name)
        self.assertEqual(owner, branch.registrant)
        self.assertEqual(BranchType.HOSTED, branch.branch_type)

    def test_createBranch_invalid_sourcepackagename(self):
        # If createBranch is called with an invalid path, it will fault.
        owner = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        branch_name = self.factory.getUniqueString()
        unique_name = '/~%s/%s/%s/ningn%%20angnong/%s' % (
            owner.name, distroseries.distribution.name, distroseries.name,
            branch_name)
        fault = self.codehosting_api.createBranch(
            owner.id, escape(unique_name))
        self.assertEqual(
            faults.InvalidSourcePackageName('ningn%20angnong'), fault)

    def test_createBranch_using_branch_alias(self):
        # Branches can be created using the branch alias and the full unique
        # name of the branch.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch_name = self.factory.getUniqueString('branch-name')
        unique_name = u'~%s/%s/%s' % (owner.name, product.name, branch_name)
        path = u'/%s/%s' % (BRANCH_ALIAS_PREFIX, unique_name)
        branch_id = self.codehosting_api.createBranch(owner.id, escape(path))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(unique_name, branch.unique_name)

    def test_createBranch_using_branch_alias_then_lookup(self):
        # A branch newly created using createBranch is immediately traversable
        # using translatePath.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch_name = self.factory.getUniqueString('branch-name')
        unique_name = u'~%s/%s/%s' % (owner.name, product.name, branch_name)
        path = escape(u'/%s/%s' % (BRANCH_ALIAS_PREFIX, unique_name))
        branch_id = self.codehosting_api.createBranch(owner.id, path)
        login(ANONYMOUS)
        translation = self.codehosting_api.translatePath(owner.id, path)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch_id, 'writable': True}, ''),
            translation)

    def test_createBranch_using_branch_alias_product(self):
        # If the person creating the branch has permission to link the new
        # branch to the alias, then they are able to create a branch and link
        # it.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        path = u'/%s/%s' % (BRANCH_ALIAS_PREFIX, product.name)
        branch_id = self.codehosting_api.createBranch(owner.id, escape(path))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(owner, branch.owner)
        self.assertEqual('trunk', branch.name)
        self.assertEqual(product, branch.product)
        self.assertEqual(ICanHasLinkedBranch(product).branch, branch)

    def test_createBranch_using_branch_alias_product_then_lookup(self):
        # A branch newly created using createBranch using a product alias is
        # immediately traversable using translatePath.
        product = self.factory.makeProduct()
        owner = product.owner
        path = escape(u'/%s/%s' % (BRANCH_ALIAS_PREFIX, product.name))
        branch_id = self.codehosting_api.createBranch(owner.id, path)
        login(ANONYMOUS)
        translation = self.codehosting_api.translatePath(owner.id, path)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch_id, 'writable': True}, ''),
            translation)

    def test_createBranch_using_branch_alias_product_not_auth(self):
        # If the person creating the branch does not have permission to link
        # the new branch to the alias, then can't create the branch.
        owner = self.factory.makePerson(name='eric')
        product = self.factory.makeProduct('wibble')
        path = u'/%s/%s' % (BRANCH_ALIAS_PREFIX, product.name)
        fault = self.codehosting_api.createBranch(owner.id, escape(path))
        message = "Cannot create linked branch at 'wibble'."
        self.assertEqual(faults.PermissionDenied(message), fault)
        # Make sure that the branch doesn't exist.
        login(ANONYMOUS)
        branch = self.branch_lookup.getByUniqueName('~eric/wibble/trunk')
        self.assertIs(None, branch)

    def test_createBranch_using_branch_alias_product_not_exist(self):
        # If the product doesn't exist, we don't (yet) create one.
        owner = self.factory.makePerson()
        path = u'/%s/foible' % (BRANCH_ALIAS_PREFIX,)
        fault = self.codehosting_api.createBranch(owner.id, escape(path))
        message = "Project 'foible' does not exist."
        self.assertEqual(faults.NotFound(message), fault)

    def test_createBranch_using_branch_alias_productseries(self):
        # If the person creating the branch has permission to link the new
        # branch to the alias, then they are able to create a branch and link
        # it.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        series = self.factory.makeProductSeries(product=product)
        path = u'/%s/%s/%s' % (BRANCH_ALIAS_PREFIX, product.name, series.name)
        branch_id = self.codehosting_api.createBranch(owner.id, escape(path))
        login(ANONYMOUS)
        branch = self.branch_lookup.get(branch_id)
        self.assertEqual(owner, branch.owner)
        self.assertEqual('trunk', branch.name)
        self.assertEqual(product, branch.product)
        self.assertEqual(ICanHasLinkedBranch(series).branch, branch)

    def test_createBranch_using_branch_alias_productseries_not_auth(self):
        # If the person creating the branch does not have permission to link
        # the new branch to the alias, then can't create the branch.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(name='wibble')
        self.factory.makeProductSeries(product=product, name='nip')
        path = u'/%s/wibble/nip' % (BRANCH_ALIAS_PREFIX,)
        fault = self.codehosting_api.createBranch(owner.id, escape(path))
        message = "Cannot create linked branch at 'wibble/nip'."
        self.assertEqual(faults.PermissionDenied(message), fault)

    def test_createBranch_using_branch_alias_productseries_not_exist(self):
        # If the product series doesn't exist, we don't (yet) create it.
        owner = self.factory.makePerson()
        self.factory.makeProduct(name='wibble')
        path = u'/%s/wibble/nip' % (BRANCH_ALIAS_PREFIX,)
        fault = self.codehosting_api.createBranch(owner.id, escape(path))
        message = "No such product series: 'nip'."
        self.assertEqual(faults.NotFound(message), fault)

    def test_requestMirror(self):
        # requestMirror should set the next_mirror_time field to be the
        # current time.
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        self.codehosting_api.requestMirror(requester.id, branch.id)
        self.assertSqlAttributeEqualsDate(
            branch, 'next_mirror_time', UTC_NOW)

    def test_requestMirror_private(self):
        # requestMirror can be used to request the mirror of a private branch.
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            owner=requester, branch_type=BranchType.MIRRORED,
            information_type=InformationType.USERDATA)
        branch = removeSecurityProxy(branch)
        self.codehosting_api.requestMirror(requester.id, branch.id)
        self.assertSqlAttributeEqualsDate(
            branch, 'next_mirror_time', UTC_NOW)

    def getFormatStringsForFormatName(self, format_name):
        default_format = bzrdir.format_registry.get(format_name)()
        control_string = default_format.get_format_string()
        branch_string = default_format.get_branch_format().get_format_string()
        repository_string = \
            default_format.repository_format.get_format_string()
        return (control_string, branch_string, repository_string)

    @property
    def arbitrary_format_strings(self):
        return self.getFormatStringsForFormatName('default')

    def test_branchChanged_sets_last_mirrored_id(self):
        # branchChanged does many things but lets just check the setting of
        # last_mirrored_id here.  The other things are tested in unit tests.
        revid = self.factory.getUniqueString()
        branch = self.factory.makeAnyBranch()
        self.codehosting_api.branchChanged(
            branch.owner.id, branch.id, '', revid,
            *self.arbitrary_format_strings)
        login(ANONYMOUS)
        self.assertEqual(revid, branch.last_mirrored_id)

    def test_branchChanged_with_LAUNCHPAD_SERVICES(self):
        # If you pass LAUNCHPAD_SERVICES as the user id to branchChanged, it
        # edits any branch.
        revid = self.factory.getUniqueString()
        branch = self.factory.makeAnyBranch()
        self.codehosting_api.branchChanged(
            LAUNCHPAD_SERVICES, branch.id, '', revid,
            *self.arbitrary_format_strings)
        login(ANONYMOUS)
        self.assertEqual(revid, branch.last_mirrored_id)

    def test_branchChanged_fault_on_unknown_id(self):
        # If the id passed in doesn't match an existing branch, the fault
        # "NoBranchWithID" is returned.
        unused_id = -1
        expected_fault = faults.NoBranchWithID(unused_id)
        received_fault = self.codehosting_api.branchChanged(
            1, unused_id, '', '', *self.arbitrary_format_strings)
        login(ANONYMOUS)
        self.assertEqual(
            (expected_fault.faultCode, expected_fault.faultString),
            (received_fault.faultCode, received_fault.faultString))

    def test_branchChanged_2a_format(self):
        branch = self.factory.makeAnyBranch()
        self.codehosting_api.branchChanged(
            branch.owner.id, branch.id, '', 'rev1',
            *self.getFormatStringsForFormatName('2a'))
        login(ANONYMOUS)
        self.assertEqual(
            (ControlFormat.BZR_METADIR_1, BranchFormat.BZR_BRANCH_7,
             RepositoryFormat.BZR_CHK_2A),
            (branch.control_format, branch.branch_format,
             branch.repository_format))

    def test_branchChanged_packs_format(self):
        branch = self.factory.makeAnyBranch()
        self.codehosting_api.branchChanged(
            branch.owner.id, branch.id, '', 'rev1',
            *self.getFormatStringsForFormatName('pack-0.92'))
        login(ANONYMOUS)
        self.assertEqual(
            (ControlFormat.BZR_METADIR_1, BranchFormat.BZR_BRANCH_6,
             RepositoryFormat.BZR_KNITPACK_1),
            (branch.control_format, branch.branch_format,
             branch.repository_format))

    def test_branchChanged_knits_format(self):
        branch = self.factory.makeAnyBranch()
        self.codehosting_api.branchChanged(
            branch.owner.id, branch.id, '', 'rev1',
            *self.getFormatStringsForFormatName('knit'))
        login(ANONYMOUS)
        self.assertEqual(
            (ControlFormat.BZR_METADIR_1, BranchFormat.BZR_BRANCH_5,
             RepositoryFormat.BZR_KNIT_1),
            (branch.control_format, branch.branch_format,
             branch.repository_format))

    def assertNotFound(self, requester, path):
        """Assert that the given path cannot be found."""
        if requester not in [LAUNCHPAD_ANONYMOUS, LAUNCHPAD_SERVICES]:
            requester = requester.id
        fault = self.codehosting_api.translatePath(requester, path)
        self.assertEqual(faults.PathTranslationError(path), fault)

    def assertPermissionDenied(self, requester, path):
        """Assert that looking at the given path gives permission denied."""
        if requester not in [LAUNCHPAD_ANONYMOUS, LAUNCHPAD_SERVICES]:
            requester = requester.id
        fault = self.codehosting_api.translatePath(requester, path)
        self.assertEqual(faults.PermissionDenied(), fault)

    def _makeProductWithDevFocus(self, private=False):
        """Make a stacking-enabled product with a development focus.

        :param private: Whether the development focus branch should be
            private.
        :return: The new Product and the new Branch.
        """
        product = self.factory.makeProduct()
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        branch = self.factory.makeProductBranch(
            information_type=information_type)
        self.factory.enableDefaultStackingForProduct(product, branch)
        target = IBranchTarget(removeSecurityProxy(product))
        self.assertEqual(target.default_stacked_on_branch, branch)
        return product, branch

    def test_translatePath_cannot_translate(self):
        # Sometimes translatePath will not know how to translate a path. When
        # this happens, it returns a Fault saying so, including the path it
        # couldn't translate.
        requester = self.factory.makePerson()
        path = escape(u'/untranslatable')
        self.assertNotFound(requester, path)

    def test_translatePath_no_preceding_slash(self):
        requester = self.factory.makePerson()
        path = escape(u'invalid')
        fault = self.codehosting_api.translatePath(requester.id, path)
        self.assertEqual(faults.InvalidPath(path), fault)

    def test_translatePath_branch(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_branch_with_trailing_slash(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        path = escape(u'/%s/' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_path_in_branch(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        path = escape(u'/%s/child' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, 'child'),
            translation)

    def test_translatePath_nested_path_in_branch(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        path = escape(u'/%s/a/b' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, 'a/b'),
            translation)

    def test_translatePath_preserves_escaping(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch()
        child_path = u'a@b'
        # This test is only meaningful if the path isn't the same when
        # escaped.
        self.assertNotEqual(escape(child_path), child_path.encode('utf-8'))
        path = escape(u'/%s/%s' % (branch.unique_name, child_path))
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT,
             {'id': branch.id, 'writable': False},
             escape(child_path)), translation)

    def test_translatePath_no_such_junk_branch(self):
        requester = self.factory.makePerson()
        path = '/~%s/+junk/.bzr/branch-format' % (requester.name,)
        self.assertNotFound(requester, path)

    def test_translatePath_branches_in_parent_dirs_not_found(self):
        requester = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = '/~%s/%s/.bzr/branch-format' % (requester.name, product.name)
        self.assertNotFound(requester, path)

    def test_translatePath_no_such_branch(self):
        requester = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = '/~%s/%s/no-such-branch' % (requester.name, product.name)
        self.assertNotFound(requester, path)

    def test_translatePath_no_such_branch_non_ascii(self):
        requester = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = u'/~%s/%s/non-asci\N{LATIN SMALL LETTER I WITH DIAERESIS}' % (
            requester.name, product.name)
        self.assertNotFound(requester, escape(path))

    def test_translatePath_private_branch(self):
        requester = self.factory.makePerson()
        branch = removeSecurityProxy(
            self.factory.makeAnyBranch(
                branch_type=BranchType.HOSTED, owner=requester,
                information_type=InformationType.USERDATA))
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': True}, ''),
            translation)

    def test_translatePath_cant_see_private_branch(self):
        requester = self.factory.makePerson()
        branch = removeSecurityProxy(self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA))
        path = escape(u'/%s' % branch.unique_name)
        self.assertPermissionDenied(requester, path)

    def test_translatePath_remote_branch(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(branch_type=BranchType.REMOTE)
        path = escape(u'/%s' % branch.unique_name)
        self.assertNotFound(requester, path)

    def test_translatePath_launchpad_services_private(self):
        branch = removeSecurityProxy(self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA))
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(
            LAUNCHPAD_SERVICES, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_anonymous_cant_see_private_branch(self):
        branch = removeSecurityProxy(self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA))
        path = escape(u'/%s' % branch.unique_name)
        self.assertPermissionDenied(LAUNCHPAD_ANONYMOUS, path)

    def test_translatePath_anonymous_public_branch(self):
        branch = self.factory.makeAnyBranch()
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(
            LAUNCHPAD_ANONYMOUS, path)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_owned(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.HOSTED, owner=requester)
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': True}, ''),
            translation)

    def test_translatePath_team_owned(self):
        requester = self.factory.makePerson()
        team = self.factory.makeTeam(requester)
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.HOSTED, owner=team)
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': True}, ''),
            translation)

    def test_translatePath_team_unowned(self):
        requester = self.factory.makePerson()
        team = self.factory.makeTeam(self.factory.makePerson())
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.HOSTED, owner=team)
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_owned_mirrored(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED, owner=requester)
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_owned_imported(self):
        requester = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.IMPORTED, owner=requester)
        path = escape(u'/%s' % branch.unique_name)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_branch_alias_short_name(self):
        # translatePath translates the short name of a branch if it's prefixed
        # by +branch.
        requester = self.factory.makePerson()
        branch = self.factory.makeProductBranch()
        removeSecurityProxy(branch.product.development_focus).branch = branch
        short_name = ICanHasLinkedBranch(branch.product).bzr_path
        path_in_branch = '.bzr/branch-format'
        path = escape(u'/%s' % os.path.join(
                BRANCH_ALIAS_PREFIX, short_name, path_in_branch))
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False},
             path_in_branch), translation)

    def test_translatePath_branch_alias_unique_name(self):
        # translatePath translates +branch paths that are followed by the
        # unique name as if they didn't have the prefix at all.
        requester = self.factory.makePerson()
        branch = self.factory.makeBranch()
        path_in_branch = '.bzr/branch-format'
        path = escape(u'/%s' % os.path.join(
                BRANCH_ALIAS_PREFIX, branch.unique_name, path_in_branch))
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False},
             path_in_branch), translation)

    def test_translatePath_branch_alias_no_such_branch(self):
        # translatePath returns a not found when there's no such branch, given
        # a unique name after +branch.
        requester = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = '/%s/~%s/%s/doesntexist' % (
            BRANCH_ALIAS_PREFIX, requester.name, product.name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_no_such_person(self):
        # translatePath returns a not found when there's no such person, given
        # a unique name after +branch.
        requester = self.factory.makePerson()
        path = '/%s/~doesntexist/dontcare/noreally' % (BRANCH_ALIAS_PREFIX,)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_no_such_product(self):
        # translatePath returns a not found when there's no such product,
        # given a unique name after +branch.
        requester = self.factory.makePerson()
        path = '/%s/~%s/doesntexist/branchname' % (
            BRANCH_ALIAS_PREFIX, requester.name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_no_such_distro(self):
        # translatePath returns a not found when there's no such distro, given
        # a unique name after +branch.
        requester = self.factory.makePerson()
        path = '/%s/~%s/doesntexist/lucid/openssh/branchname' % (
            BRANCH_ALIAS_PREFIX, requester.name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_no_such_distroseries(self):
        # translatePath returns a not found when there's no such distroseries,
        # given a unique name after +branch.
        requester = self.factory.makePerson()
        distro = self.factory.makeDistribution()
        path = '/%s/~%s/%s/doesntexist/openssh/branchname' % (
            BRANCH_ALIAS_PREFIX, requester.name, distro.name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_no_such_sourcepackagename(self):
        # translatePath returns a not found when there's no such
        # sourcepackagename, given a unique name after +branch.
        requester = self.factory.makePerson()
        distroseries = self.factory.makeDistroSeries()
        distro = distroseries.distribution
        path = '/%s/~%s/%s/%s/doesntexist/branchname' % (
            BRANCH_ALIAS_PREFIX, requester.name, distro.name,
            distroseries.name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_product_with_no_branch(self):
        # translatePath returns a not found when we look up a product that has
        # no linked branch.
        requester = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = '/%s/%s' % (BRANCH_ALIAS_PREFIX, product.name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_no_linked_sourcepackage_branch(self):
        # translatePath returns a not found when there's no linked branch for
        # a distro series source package.
        requester = self.factory.makePerson()
        sourcepackage = self.factory.makeSourcePackage()
        distro = sourcepackage.distribution
        path = '/%s/%s/%s' % (
            BRANCH_ALIAS_PREFIX, distro.name, sourcepackage.sourcepackagename)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_invalid_product_name(self):
        # translatePath returns a not found when there is an invalid product
        # name.
        requester = self.factory.makePerson()
        invalid_name = '_' + self.factory.getUniqueString()
        path = '/%s/%s' % (BRANCH_ALIAS_PREFIX, invalid_name)
        self.assertNotFound(requester, path)

    def test_translatePath_branch_alias_bzrdir_content(self):
        # translatePath('/+branch/.bzr/.*') *must* return not found, otherwise
        # bzr will look for it and we don't have a global bzr dir.
        requester = self.factory.makePerson()
        self.assertNotFound(
            requester, '/%s/.bzr/branch-format' % BRANCH_ALIAS_PREFIX)

    def test_translatePath_branch_alias_bzrdir(self):
        # translatePath('/+branch/.bzr') *must* return not found, otherwise
        # bzr will look for it and we don't have a global bzr dir.
        requester = self.factory.makePerson()
        self.assertNotFound(requester, '/%s/.bzr' % BRANCH_ALIAS_PREFIX)

    def test_translatePath_branch_id_alias_bzrdir_content(self):
        # translatePath('/+branch-id/.bzr/.*') *must* return not found,
        # otherwise bzr will look for it and we don't have a global bzr dir.
        requester = self.factory.makePerson()
        self.assertNotFound(
            requester, '/%s/.bzr/branch-format' % BRANCH_ID_ALIAS_PREFIX)

    def test_translatePath_branch_id_alias_bzrdir(self):
        # translatePath('/+branch-id/.bzr') *must* return not found, otherwise
        # bzr will look for it and we don't have a global bzr dir.
        requester = self.factory.makePerson()
        self.assertNotFound(requester, '/%s/.bzr' % BRANCH_ID_ALIAS_PREFIX)

    def test_translatePath_branch_id_alias_trailing(self):
        # Make sure the trailing path is returned.
        requester = self.factory.makePerson()
        branch = removeSecurityProxy(self.factory.makeAnyBranch())
        path = escape(u'%s/foo/bar' % branch_id_alias(branch))
        translation = self.codehosting_api.translatePath(requester.id, path)
        expected = (
            BRANCH_TRANSPORT,
            {'id': branch.id, 'writable': False},
            'foo/bar',
            )
        self.assertEqual(expected, translation)

    def test_translatePath_branch_id_alias_owned(self):
        # Even if the requester is the owner, the branch is read only.
        requester = self.factory.makePerson()
        branch = removeSecurityProxy(
            self.factory.makeAnyBranch(
                branch_type=BranchType.HOSTED, owner=requester))
        path = escape(branch_id_alias(branch))
        translation = self.codehosting_api.translatePath(requester.id, path)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_branch_id_alias_private_branch(self):
        # Private branches are accessible but read-only even if you are the
        # owner.
        requester = self.factory.makePerson()
        branch = removeSecurityProxy(
            self.factory.makeAnyBranch(
                branch_type=BranchType.HOSTED, owner=requester,
                information_type=InformationType.USERDATA))
        path = escape(branch_id_alias(branch))
        translation = self.codehosting_api.translatePath(requester.id, path)
        self.assertEqual(
            (BRANCH_TRANSPORT, {'id': branch.id, 'writable': False}, ''),
            translation)

    def test_translatePath_branch_id_alias_private_branch_no_access(self):
        # Private branches you don't have access to raise permission denied.
        requester = self.factory.makePerson()
        branch = removeSecurityProxy(
            self.factory.makeAnyBranch(
                branch_type=BranchType.HOSTED,
                information_type=InformationType.USERDATA))
        path = escape(branch_id_alias(branch))
        self.assertPermissionDenied(requester, path)

    def assertTranslationIsControlDirectory(self, translation,
                                            default_stacked_on,
                                            trailing_path):
        """Assert that 'translation' points to the right control transport."""
        expected_translation = (
            CONTROL_TRANSPORT,
            {'default_stack_on': escape(default_stacked_on)}, trailing_path)
        self.assertEqual(expected_translation, translation)

    def test_translatePath_control_directory(self):
        requester = self.factory.makePerson()
        product, branch = self._makeProductWithDevFocus()
        path = escape(u'/~%s/%s/.bzr' % (requester.name, product.name))
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertTranslationIsControlDirectory(
            translation,
            default_stacked_on=branch_id_alias(branch),
            trailing_path='.bzr')

    def test_translatePath_control_directory_no_stacked_set(self):
        # When there's no default stacked-on branch set for the project, we
        # don't even bother translating control directory paths.
        requester = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = escape(u'/~%s/%s/.bzr/' % (requester.name, product.name))
        self.assertNotFound(requester, path)

    def test_translatePath_control_directory_invisble_branch(self):
        requester = self.factory.makePerson()
        product, branch = self._makeProductWithDevFocus(private=True)
        path = escape(u'/~%s/%s/.bzr/' % (requester.name, product.name))
        self.assertNotFound(requester, path)

    def test_translatePath_control_directory_private_branch(self):
        product, branch = self._makeProductWithDevFocus(private=True)
        branch = removeSecurityProxy(branch)
        requester = branch.owner
        path = escape(u'/~%s/%s/.bzr/' % (requester.name, product.name))
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertTranslationIsControlDirectory(
            translation,
            default_stacked_on=branch_id_alias(branch),
            trailing_path='.bzr')

    def test_translatePath_control_directory_other_owner(self):
        requester = self.factory.makePerson()
        product, branch = self._makeProductWithDevFocus()
        owner = self.factory.makePerson()
        path = escape(u'/~%s/%s/.bzr' % (owner.name, product.name))
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertTranslationIsControlDirectory(
            translation,
            default_stacked_on=branch_id_alias(branch),
            trailing_path='.bzr')

    def test_translatePath_control_directory_package_no_focus(self):
        # If the package has no default stacked-on branch, then don't show the
        # control directory.
        requester = self.factory.makePerson()
        package = self.factory.makeSourcePackage()
        self.assertIs(None, IBranchTarget(package).default_stacked_on_branch)
        path = '/~%s/%s/.bzr/' % (requester.name, package.path)
        self.assertNotFound(requester, path)

    def test_translatePath_control_directory_package(self):
        # If the package has a default stacked-on branch, then show the
        # control directory.
        requester = self.factory.makePerson()
        package = self.factory.makeSourcePackage()
        branch = self.factory.makePackageBranch(sourcepackage=package)
        self.factory.enableDefaultStackingForPackage(package, branch)
        self.assertIsNot(
            None, IBranchTarget(package).default_stacked_on_branch)
        path = '/~%s/%s/.bzr/' % (requester.name, package.path)
        translation = self.codehosting_api.translatePath(requester.id, path)
        login(ANONYMOUS)
        self.assertTranslationIsControlDirectory(
            translation,
            default_stacked_on=branch_id_alias(branch),
            trailing_path='.bzr')


class AcquireBranchToPullTestsViaEndpoint(TestCaseWithFactory,
                                          AcquireBranchToPullTests):
    """Tests for `acquireBranchToPull` method of `ICodehostingAPI`."""

    def setUp(self):
        super(AcquireBranchToPullTestsViaEndpoint, self).setUp()
        frontend = self.frontend()
        self.codehosting_api = frontend.getCodehostingEndpoint()
        self.factory = frontend.getLaunchpadObjectFactory()

    def assertNoBranchIsAcquired(self, *branch_types):
        """See `AcquireBranchToPullTests`."""
        branch_types = tuple(branch_type.name for branch_type in branch_types)
        pull_info = self.codehosting_api.acquireBranchToPull(branch_types)
        self.assertEqual((), pull_info)

    def assertBranchIsAcquired(self, branch, *branch_types):
        """See `AcquireBranchToPullTests`."""
        branch = removeSecurityProxy(branch)
        branch_types = tuple(branch_type.name for branch_type in branch_types)
        pull_info = self.codehosting_api.acquireBranchToPull(branch_types)
        default_branch = branch.target.default_stacked_on_branch
        if default_branch:
            default_branch_name = default_branch
        else:
            default_branch_name = ''
        self.assertEqual(
            pull_info,
            (branch.id, branch.getPullURL(), branch.unique_name,
             default_branch_name, branch.branch_type.name))
        self.assertIsNot(None, branch.last_mirror_attempt)
        self.assertIs(None, branch.next_mirror_time)

    def startMirroring(self, branch):
        """See `AcquireBranchToPullTests`."""
        # This is a bit random, but it works.  acquireBranchToPull marks the
        # branch it returns as started mirroring, but we should check that the
        # one we want is returned...
        self.assertBranchIsAcquired(branch, branch.branch_type)

    def test_branch_type_returned_mirrored(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        branch.requestMirror()
        pull_info = self.codehosting_api.acquireBranchToPull(())
        _, _, _, _, branch_type = pull_info
        self.assertEqual('MIRRORED', branch_type)

    def test_branch_type_returned_import(self):
        branch = self.factory.makeAnyBranch(branch_type=BranchType.IMPORTED)
        branch.requestMirror()
        pull_info = self.codehosting_api.acquireBranchToPull(())
        _, _, _, _, branch_type = pull_info
        self.assertEqual('IMPORTED', branch_type)

    def test_default_stacked_on_branch_returned(self):
        branch = self.factory.makeProductBranch(
            branch_type=BranchType.MIRRORED)
        self.factory.enableDefaultStackingForProduct(branch.product)
        branch.requestMirror()
        pull_info = self.codehosting_api.acquireBranchToPull(())
        _, _, _, default_stacked_on_branch, _ = pull_info
        self.assertEqual(
            default_stacked_on_branch,
            '/' + branch.target.default_stacked_on_branch.unique_name)

    def test_private_default_stacked_not_returned_for_mirrored_branch(self):
        # We don't stack mirrored branches on a private default stacked on
        # branch.
        product = self.factory.makeProduct()
        default_branch = self.factory.makeProductBranch(
            product=product, information_type=InformationType.USERDATA)
        self.factory.enableDefaultStackingForProduct(product, default_branch)
        mirrored_branch = self.factory.makeProductBranch(
            branch_type=BranchType.MIRRORED, product=product)
        mirrored_branch.requestMirror()
        pull_info = self.codehosting_api.acquireBranchToPull(())
        _, _, _, default_stacked_on_branch, _ = pull_info
        self.assertEqual(
            '', default_stacked_on_branch)

    def test_unknown_branch_type_name_raises(self):
        self.assertRaises(
            UnknownBranchTypeError, self.codehosting_api.acquireBranchToPull,
            ('NO_SUCH_TYPE',))


class LaunchpadDatabaseFrontend:
    """A 'frontend' to Launchpad's branch services.

    A 'frontend' here means something that provides access to the various
    XML-RPC endpoints, object factories and 'database' methods needed to write
    unit tests for XML-RPC endpoints.

    All of these methods are gathered together in this class so that
    alternative implementations can be provided, see `InMemoryFrontend`.
    """

    def getCodehostingEndpoint(self):
        """Return the branch filesystem endpoint for testing."""
        return CodehostingAPI(None, None)

    def getLaunchpadObjectFactory(self):
        """Return the Launchpad object factory for testing.

        See `LaunchpadObjectFactory`.
        """
        return LaunchpadObjectFactory()

    def getBranchLookup(self):
        """Return an implementation of `IBranchLookup`.

        Tests should use this to get the branch set they need, rather than
        using 'getUtility(IBranchSet)'. This allows in-memory implementations
        to work correctly.
        """
        return getUtility(IBranchLookup)

    def getLastActivity(self, activity_name):
        """Get the last script activity with 'activity_name'."""
        return getUtility(IScriptActivitySet).getLastActivity(activity_name)


def test_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    endpoint_tests = unittest.TestSuite(
        [loader.loadTestsFromTestCase(AcquireBranchToPullTestsViaEndpoint),
         loader.loadTestsFromTestCase(CodehostingTest),
         ])
    scenarios = [
        ('db', {'frontend': LaunchpadDatabaseFrontend,
                'layer': LaunchpadFunctionalLayer}),
        ('inmemory', {'frontend': InMemoryFrontend,
                      'layer': FunctionalLayer}),
        ]
    multiply_tests(endpoint_tests, scenarios, suite)
    suite.addTests(loader.loadTestsFromTestCase(TestRunWithLogin))
    return suite
