# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XMLRPC self-test api.
"""

import xmlrpclib

from zope.component import getUtility

from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import (
    anonymous_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.xmlrpc import XMLRPCTestTransport
from lp.xmlrpc.application import (
    ISelfTest,
    SelfTest,
    )


class TestXMLRPCSelfTest(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def make_proxy(self):
        return xmlrpclib.ServerProxy(
            'http://xmlrpc.launchpad.dev/', transport=XMLRPCTestTransport())

    def make_logged_in_proxy(self):
        return xmlrpclib.ServerProxy(
            'http://test@canonical.com:test@xmlrpc.launchpad.dev/',
            transport=XMLRPCTestTransport())

    def test_launchpad_root_object(self):
        """The Launchpad root object has a simple XMLRPC API to show that
        XMLRPC works.
        """
        selftestview = SelfTest('somecontext', 'somerequest')
        self.assertTrue(verifyObject(ISelfTest, selftestview))
        self.assertEqual(u'foo bar', selftestview.concatenate('foo', 'bar'))
        fault = selftestview.make_fault()
        self.assertEqual("<Fault 666: 'Yoghurt and spanners.'>", str(fault))

    def test_custom_transport(self):
        """We can test our XMLRPC APIs using xmlrpclib, using a custom
        Transport which talks with the publisher directly.
        """
        selftest = self.make_proxy()
        self.assertEqual('foo bar', selftest.concatenate('foo', 'bar'))
        fault = self.assertRaises(xmlrpclib.Fault, selftest.make_fault)
        self.assertEqual("<Fault 666: 'Yoghurt and spanners.'>", str(fault))

    def test_unexpected_exception(self):
        """Sometimes an XML-RPC method will be buggy, and raise an exception
        other than xmlrpclib.Fault.  We have such a method on the self test
        view.
        """
        selftestview = SelfTest('somecontext', 'somerequest')
        self.assertRaises(RuntimeError, selftestview.raise_exception)

    def test_exception_converted_to_fault(self):
        """As with normal browser requests, we don't want to expose these error
        messages to the user since they could contain confidential information.
        Such exceptions get converted to a fault listing the OOPS ID (assuming
        one was generated):
        """
        selftest = self.make_proxy()
        e = self.assertRaises(xmlrpclib.Fault, selftest.raise_exception)
        self.assertStartsWith(str(e), "<Fault -1: 'OOPS-")

    def test_anonymous_authentication(self):
        """hello() returns Anonymous because we haven't logged in."""
        selftest = self.make_proxy()
        self.assertEqual('Hello Anonymous.', selftest.hello())

    def test_user_pass_authentication(self):
        """If we provide a username and password, hello() will
        include the name of the logged in user.

        The interactions in this test, and the interaction in the XMLRPC
        methods are different, so we still have an anonymous interaction in
        this test.
        """
        with anonymous_logged_in():
            self.assertIs(None, getUtility(ILaunchBag).user)
            selftest = self.make_logged_in_proxy()
            self.assertEqual('Hello Sample Person.', selftest.hello())

    def test_login_differences(self):
        """Even if we log in as Foo Bar here, the XMLRPC method will see Sample
        Person as the logged in user.
        """
        person = self.factory.makePerson()
        with person_logged_in(person):
            selftest = self.make_logged_in_proxy()
            self.assertEqual('Hello Sample Person.', selftest.hello())
            self.assertEqual(person.displayname,
                             getUtility(ILaunchBag).user.displayname)
