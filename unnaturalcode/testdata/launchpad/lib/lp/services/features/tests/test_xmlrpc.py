# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for FeatureFlagApplication."""

__metaclass__ = type

import xmlrpclib

from lp.services import features
from lp.services.config import config
from lp.services.features.flags import FeatureController
from lp.services.features.rulesource import StormFeatureRuleSource
from lp.services.features.scopes import (
    DefaultScope,
    FixedScope,
    MultiScopeHandler,
    )
from lp.services.features.xmlrpc import FeatureFlagApplication
from lp.testing import (
    feature_flags,
    set_feature_flag,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.xmlrpc import XMLRPCTestTransport


class TestGetFeatureFlag(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.endpoint = FeatureFlagApplication()

    def installFeatureController(self, feature_controller):
        old_features = features.get_relevant_feature_controller()
        features.install_feature_controller(feature_controller)
        self.addCleanup(
            features.install_feature_controller, old_features)

    def test_getFeatureFlag_returns_None_by_default(self):
        self.assertIs(None, self.endpoint.getFeatureFlag(u'unknown'))

    def test_getFeatureFlag_returns_true_for_set_flag(self):
        flag_name = u'flag'
        with feature_flags():
            set_feature_flag(flag_name, u'1')
            self.assertEqual(u'1', self.endpoint.getFeatureFlag(flag_name))

    def test_getFeatureFlag_ignores_relevant_feature_controller(self):
        # getFeatureFlag should only consider the scopes it is asked to
        # consider, not any that happen to be active due to the XML-RPC
        # request itself.
        flag_name = u'flag'
        scope_name = u'scope'
        self.installFeatureController(
            FeatureController(
                MultiScopeHandler(
                    [DefaultScope(), FixedScope(scope_name)]).lookup,
                StormFeatureRuleSource()))
        set_feature_flag(flag_name, u'1', scope_name)
        self.assertEqual(None, self.endpoint.getFeatureFlag(flag_name))

    def test_getFeatureFlag_considers_supplied_scope(self):
        flag_name = u'flag'
        scope_name = u'scope'
        with feature_flags():
            set_feature_flag(flag_name, u'value', scope_name)
            self.assertEqual(
                u'value',
                self.endpoint.getFeatureFlag(flag_name, [scope_name]))

    def test_getFeatureFlag_turns_user_into_team_scope(self):
        flag_name = u'flag'
        person = self.factory.makePerson()
        team = self.factory.makeTeam(members=[person])
        with feature_flags():
            set_feature_flag(flag_name, u'value', u'team:' + team.name)
            self.assertEqual(
                u'value',
                self.endpoint.getFeatureFlag(
                    flag_name, ['user:' + person.name]))

    def test_xmlrpc_interface_unset(self):
        sp = xmlrpclib.ServerProxy(
            config.launchpad.feature_flags_endpoint,
            transport=XMLRPCTestTransport(), allow_none=True)
        self.assertEqual(None, sp.getFeatureFlag(u'flag'))

    def test_xmlrpc_interface_set(self):
        sp = xmlrpclib.ServerProxy(
            config.launchpad.feature_flags_endpoint,
            transport=XMLRPCTestTransport(), allow_none=True)
        flag_name = u'flag'
        with feature_flags():
            set_feature_flag(flag_name, u'1')
            self.assertEqual(u'1', sp.getFeatureFlag(flag_name))
