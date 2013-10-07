# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing registry-related xmlrpc calls."""

__metaclass__ = type

import xmlrpclib

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.enums import PersonVisibility
from lp.registry.interfaces.person import (
    IPersonSet,
    ISoftwareCenterAgentAPI,
    ISoftwareCenterAgentApplication,
    PersonCreationRationale,
    )
from lp.registry.xmlrpc.softwarecenteragent import SoftwareCenterAgentAPI
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.xmlrpc import XMLRPCTestTransport
from lp.xmlrpc.interfaces import IPrivateApplication


class TestSoftwareCenterAgentAPI(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSoftwareCenterAgentAPI, self).setUp()
        self.private_root = getUtility(IPrivateApplication)
        self.sca_api = SoftwareCenterAgentAPI(
            context=self.private_root.softwarecenteragent,
            request=LaunchpadTestRequest())

    def test_provides_interface(self):
        # The view interface is provided.
        self.assertProvides(self.sca_api, ISoftwareCenterAgentAPI)

    def test_getOrCreateSoftwareCenterCustomer(self):
        # The method returns the username of the person, and sets the
        # correct creation rational/comment.
        user_name = self.sca_api.getOrCreateSoftwareCenterCustomer(
            u'openid-ident', 'alice@b.com', 'Joe Blogs')

        self.assertEqual('alice', user_name)
        person = getUtility(IPersonSet).getByName(user_name)
        self.assertEqual(
            'openid-ident', removeSecurityProxy(
                person.account).openid_identifiers.any().identifier)
        self.assertEqual(
            PersonCreationRationale.SOFTWARE_CENTER_PURCHASE,
            person.creation_rationale)
        self.assertEqual(
            "when purchasing an application via Software Center.",
            person.creation_comment)


class TestSoftwareCenterAgentApplication(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestSoftwareCenterAgentApplication, self).setUp()
        self.private_root = getUtility(IPrivateApplication)
        self.rpc_proxy = xmlrpclib.ServerProxy(
            'http://xmlrpc-private.launchpad.dev:8087/softwarecenteragent',
            transport=XMLRPCTestTransport())

    def test_provides_interface(self):
        # The application is provided.
        self.assertProvides(
            self.private_root.softwarecenteragent,
            ISoftwareCenterAgentApplication)

    def test_getOrCreateSoftwareCenterCustomer_xmlrpc(self):
        # The method can be called via xmlrpc
        user_name = self.rpc_proxy.getOrCreateSoftwareCenterCustomer(
            u'openid-ident', 'a@b.com', 'Joe Blogs')
        person = getUtility(IPersonSet).getByName(user_name)
        self.assertEqual(
            u'openid-ident',
            removeSecurityProxy(
                person.account).openid_identifiers.any().identifier)

    def test_getOrCreateSoftwareCenterCustomer_xmlrpc_suspended(self):
        # A suspended account results in an appropriate xmlrpc fault.
        suspended_person = self.factory.makePerson(
            displayname='Joe Blogs', email='a@b.com',
            account_status=AccountStatus.SUSPENDED)
        openid_identifier = removeSecurityProxy(
            suspended_person.account).openid_identifiers.any().identifier

        # assertRaises doesn't let us check the type of Fault.
        fault_raised = False
        try:
            self.rpc_proxy.getOrCreateSoftwareCenterCustomer(
                openid_identifier, 'a@b.com', 'Joe Blogs')
        except xmlrpclib.Fault as e:
            fault_raised = True
            self.assertEqual(370, e.faultCode)
            self.assertIn(openid_identifier, e.faultString)

        self.assertTrue(fault_raised)

    def test_getOrCreateSoftwareCenterCustomer_xmlrpc_team(self):
        # A team email address results in an appropriate xmlrpc fault.
        self.factory.makeTeam(email='a@b.com')

        # assertRaises doesn't let us check the type of Fault.
        fault_raised = False
        try:
            self.rpc_proxy.getOrCreateSoftwareCenterCustomer(
                'foo', 'a@b.com', 'Joe Blogs')
        except xmlrpclib.Fault as e:
            fault_raised = True
            self.assertEqual(400, e.faultCode)
            self.assertIn('a@b.com', e.faultString)

        self.assertTrue(fault_raised)

    def test_not_available_on_public_api(self):
        # The person set api is not available on the public xmlrpc
        # service.
        public_rpc_proxy = xmlrpclib.ServerProxy(
            'http://test@canonical.com:test@'
            'xmlrpc.launchpad.dev/softwarecenteragent',
            transport=XMLRPCTestTransport())
        e = self.assertRaises(
            xmlrpclib.ProtocolError,
            public_rpc_proxy.getOrCreateSoftwareCenterCustomer,
            'openid-ident', 'a@b.com', 'Joe Blogs')
        self.assertEqual(404, e.errcode)


class TestCanonicalSSOApplication(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCanonicalSSOApplication, self).setUp()
        self.rpc_proxy = xmlrpclib.ServerProxy(
            'http://xmlrpc-private.launchpad.dev:8087/canonicalsso',
            transport=XMLRPCTestTransport())

    def test_getPersonDetailsByOpenIDIdentifier(self):
        person = self.factory.makePerson(time_zone='Australia/Melbourne')
        self.factory.makeTeam(
            name='pubteam', members=[person],
            visibility=PersonVisibility.PUBLIC)
        self.factory.makeTeam(
            name='privteam', members=[person],
            visibility=PersonVisibility.PRIVATE)
        openid_identifier = removeSecurityProxy(
            person.account).openid_identifiers.any().identifier
        result = self.rpc_proxy.getPersonDetailsByOpenIDIdentifier(
            openid_identifier)
        self.assertEqual(
            dict(
                name=person.name,
                time_zone=person.location.time_zone,
                teams={'pubteam': False, 'privteam': True}),
            result)

    def test_not_available_on_public_api(self):
        # The person set api is not available on the public xmlrpc
        # service.
        person = self.factory.makePerson()
        openid_identifier = removeSecurityProxy(
            person.account).openid_identifiers.any().identifier
        public_rpc_proxy = xmlrpclib.ServerProxy(
            'http://test@canonical.com:test@'
            'xmlrpc.launchpad.dev/canonicalsso',
            transport=XMLRPCTestTransport())
        e = self.assertRaises(
            xmlrpclib.ProtocolError,
            public_rpc_proxy.getPersonDetailsByOpenIDIdentifier,
            openid_identifier)
        self.assertEqual(404, e.errcode)
