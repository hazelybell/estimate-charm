# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for feature flags."""


__metaclass__ = type

import os

from lp.services.features import (
    getFeatureFlag,
    install_feature_controller,
    )
from lp.services.features.flags import FeatureController
from lp.services.features.rulesource import StormFeatureRuleSource
from lp.testing import (
    layers,
    TestCase,
    )


notification_name = 'notification.global.text'
notification_value = u'\N{SNOWMAN} stormy Launchpad weather ahead'


testdata = [
    (notification_name, 'beta_user', 100, notification_value),
    ('ui.icing', 'default', 100, u'3.0'),
    ('ui.icing', 'beta_user', 300, u'4.0'),
    ]


class TestFeatureFlags(TestCase):

    layer = layers.DatabaseFunctionalLayer

    def setUp(self):
        super(TestFeatureFlags, self).setUp()
        if os.environ.get("STORM_TRACE", None):
            from storm.tracer import debug
            debug(True)

    def makeControllerInScopes(self, scopes):
        """Make a controller that will report it's in the given scopes."""
        call_log = []

        def scope_cb(scope):
            call_log.append(scope)
            return scope in scopes
        controller = FeatureController(scope_cb, StormFeatureRuleSource())
        return controller, call_log

    def populateStore(self):
        StormFeatureRuleSource().setAllRules(testdata)

    def test_getFlag(self):
        self.populateStore()
        control, call_log = self.makeControllerInScopes(['default'])
        self.assertEqual(u'3.0',
            control.getFlag('ui.icing'))
        self.assertEqual(['beta_user', 'default'], call_log)

    def test_getItem(self):
        # for use in page templates, the flags can be treated as a dict
        self.populateStore()
        control, call_log = self.makeControllerInScopes(['default'])
        self.assertEqual(u'3.0',
            control['ui.icing'])
        self.assertEqual(['beta_user', 'default'], call_log)
        # after looking this up the value is known and the scopes are
        # positively and negatively cached
        self.assertEqual({'ui.icing': u'3.0'}, control.usedFlags())
        self.assertEqual(dict(beta_user=False, default=True),
            control.usedScopes())

    def test_currentScope(self):
        # currentScope() returns the scope of the matching rule with
        # the highest priority rule
        self.populateStore()
        # If only one scope matches, its name is returned.
        control, call_log = self.makeControllerInScopes(['default'])
        self.assertEqual('default', control.currentScope('ui.icing'))
        # If two scopes match, the one with the higer priority is returned.
        control, call_log = self.makeControllerInScopes(
            ['default', 'beta_user'])
        self.assertEqual('beta_user', control.currentScope('ui.icing'))

    def test_currentScope__undefined_feature(self):
        # currentScope() returns None for a non-existent flaeture flag.
        self.populateStore()
        control, call_log = self.makeControllerInScopes(['default'])
        self.assertIs(None, control.currentScope('undefined_feature'))

    def test_defaultFlagValue(self):
        # defaultFlagValue() returns the default value of a flag even if
        # another scopewith a higher priority matches.
        self.populateStore()
        control, call_log = self.makeControllerInScopes(
            ['default', 'beta_user'])
        self.assertEqual('3.0', control.defaultFlagValue('ui.icing'))

    def test_defaultFlagValue__undefined_feature(self):
        # defaultFlagValue() returns None if no default scope is defined
        # for a feature.
        self.populateStore()
        control, call_log = self.makeControllerInScopes(
            ['default', 'beta_user'])
        self.assertIs(None, control.defaultFlagValue('undefined_feature'))

    def test_getAllFlags(self):
        # can fetch all the active flags, and it gives back only the
        # highest-priority settings.  this may be expensive and shouldn't
        # normally be used.
        self.populateStore()
        control, call_log = self.makeControllerInScopes(
            ['beta_user', 'default'])
        self.assertEqual(
            {'ui.icing': '4.0',
             notification_name: notification_value},
            control.getAllFlags())
        # evaluates all necessary flags; in this test data beta_user shadows
        # default settings
        self.assertEqual(['beta_user'], call_log)

    def test_overrideFlag(self):
        # if there are multiple settings for a flag, and they match multiple
        # scopes, the priorities determine which is matched
        self.populateStore()
        default_control, call_log = self.makeControllerInScopes(['default'])
        self.assertEqual(
            u'3.0',
            default_control.getFlag('ui.icing'))
        beta_control, call_log = self.makeControllerInScopes(
            ['beta_user', 'default'])
        self.assertEqual(
            u'4.0',
            beta_control.getFlag('ui.icing'))

    def test_undefinedFlag(self):
        # if the flag is not defined, we get None
        self.populateStore()
        control, call_log = self.makeControllerInScopes(
            ['beta_user', 'default'])
        self.assertIs(None,
            control.getFlag('unknown_flag'))
        no_scope_flags, call_log = self.makeControllerInScopes([])
        self.assertIs(None,
            no_scope_flags.getFlag('ui.icing'))

    def test_threadGetFlag(self):
        self.populateStore()
        # the start-of-request handler will do something like this:
        controller, call_log = self.makeControllerInScopes(
            ['default', 'beta_user'])
        install_feature_controller(controller)
        try:
            # then application code can simply ask without needing a context
            # object
            self.assertEqual(u'4.0', getFeatureFlag('ui.icing'))
        finally:
            install_feature_controller(None)

    def test_threadGetFlagNoContext(self):
        # If there is no context, please don't crash. workaround for the root
        # cause in bug 631884.
        install_feature_controller(None)
        self.assertEqual(None, getFeatureFlag('ui.icing'))

    def testLazyScopeLookup(self):
        # feature scopes may be a bit expensive to look up, so we do it only
        # when it will make a difference to the result.
        self.populateStore()
        f, call_log = self.makeControllerInScopes(['beta_user'])
        self.assertEqual(u'4.0', f.getFlag('ui.icing'))
        # to calculate this it should only have had to check we're in the
        # beta_users scope; nothing else makes a difference
        self.assertEqual(dict(beta_user=True), f._known_scopes._known)

    def testUnknownFeature(self):
        # looking up an unknown feature gives you None
        self.populateStore()
        f, call_log = self.makeControllerInScopes([])
        self.assertEqual(None, f.getFlag('unknown'))
        # no scopes need to be checked because it's just not in the database
        # and there's no point checking
        self.assertEqual({}, f._known_scopes._known)
        self.assertEquals([], call_log)
        # however, this we have now negative-cached the flag
        self.assertEqual(dict(unknown=None), f.usedFlags())
        self.assertEqual(dict(), f.usedScopes())

    def testScopeDict(self):
        # can get scopes as a dict, for use by "feature_scopes/server.demo"
        f, call_log = self.makeControllerInScopes(['beta_user'])
        self.assertEqual(True, f.scopes['beta_user'])
        self.assertEqual(False, f.scopes['alpha_user'])
        self.assertEqual(True, f.scopes['beta_user'])
        self.assertEqual(['beta_user', 'alpha_user'], call_log)


test_rules_list = [
    (notification_name, 'beta_user', 100, notification_value),
    ('ui.icing', 'normal_user', 500, u'5.0'),
    ('ui.icing', 'beta_user', 300, u'4.0'),
    ('ui.icing', 'default', 100, u'3.0'),
    ]


class TestStormFeatureRuleSource(TestCase):

    layer = layers.DatabaseFunctionalLayer

    def test_getAllRulesAsTuples(self):
        source = StormFeatureRuleSource()
        source.setAllRules(test_rules_list)
        self.assertEquals(
            test_rules_list,
            list(source.getAllRulesAsTuples()))

    def test_getAllRulesAsText(self):
        source = StormFeatureRuleSource()
        source.setAllRules(test_rules_list)
        self.assertEquals(
            """\
%s\tbeta_user\t100\t%s
ui.icing\tnormal_user\t500\t5.0
ui.icing\tbeta_user\t300\t4.0
ui.icing\tdefault\t100\t3.0
""" % (notification_name, notification_value),
            source.getAllRulesAsText())

    def test_setAllRulesFromText(self):
        # We will overwrite existing data.
        source = StormFeatureRuleSource()
        source.setAllRules(test_rules_list)
        source.setAllRulesFromText("""

flag1   beta_user   200   alpha
flag1   default     100   gamma with spaces
flag2   default     0\ton
""")
        self.assertEquals({
            'flag1': [
                ('beta_user', 200, 'alpha'),
                ('default', 100, 'gamma with spaces'),
                ],
            'flag2': [
                ('default', 0, 'on'),
                ],
            },
            source.getAllRulesAsDict())
