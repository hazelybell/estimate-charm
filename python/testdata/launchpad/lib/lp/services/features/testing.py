# Copyright 2010,2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for writing tests that use feature flags."""

__metaclass__ = type
__all__ = ['FeatureFixture']


from fixtures import Fixture
from lazr.restful.utils import get_current_browser_request

from lp.services.features import (
    get_relevant_feature_controller,
    install_feature_controller,
    )
from lp.services.features.flags import FeatureController
from lp.services.features.rulesource import (
    Rule,
    StormFeatureRuleSource,
    )
from lp.services.features.scopes import ScopesFromRequest


class FeatureFixture(Fixture):
    """A fixture that sets a feature.

    The fixture takes a dictionary as its constructor argument. The keys of
    the dictionary are features to be set. All existing flags will be cleared.

    Call the fixture's `setUp()' method to install the features with the
    desired values.  Calling `cleanUp()' will restore the original values.
    You can also install this fixture by inheriting from
    `fixtures.TestWithFixtures' and then calling the TestCase's
    `self.useFixture()' method.

    The fixture can also be used as a context manager. The value of the
    feature within the context block is set to the dictionary's key's value.
    The values are restored when the block exits.
    """

    def __init__(self, features_dict, full_feature_rules=None,
            override_scope_lookup=None):
        """Constructor.

        :param features_dict: A dictionary-like object with keys and values
            that are flag names and those flags' settings.
        :param override_scope_lookup: If non-None, an argument that takes
            a scope name and returns True if it matches.  If not specified, 
            scopes are looked up from the current request.
        """
        self.desired_features = features_dict
        self.full_feature_rules = full_feature_rules
        self.override_scope_lookup = override_scope_lookup

    def setUp(self):
        """Set the feature flags that this fixture is responsible for."""
        super(FeatureFixture, self).setUp()

        rule_source = StormFeatureRuleSource()
        self.addCleanup(
            rule_source.setAllRules, rule_source.getAllRulesAsTuples())
        rule_source.setAllRules(self.makeNewRules())

        original_controller = get_relevant_feature_controller()

        def scope_lookup(scope_name):
            request = get_current_browser_request()
            return ScopesFromRequest(request).lookup(scope_name)

        if self.override_scope_lookup:
            scope_lookup = self.override_scope_lookup
        install_feature_controller(
            FeatureController(scope_lookup, rule_source))
        self.addCleanup(install_feature_controller, original_controller)

    def makeNewRules(self):
        """Make a set of new feature flag rules."""
        # Create a list of the new rules. Note that rules with a None
        # value are quietly dropped, since you can't assign None as a
        # feature flag value (it would come out as u'None') and setting
        # a flag to None essentially means turning it off anyway.
        #
        # Flags that are not present in the set of new rules will be deleted
        # by setAllRules().
        new_rules = [
            Rule(
                flag=flag_name,
                scope='default',
                priority=999,
                value=unicode(value))
            for flag_name, value in self.desired_features.iteritems()
                if value is not None]

        if self.full_feature_rules is not None:
            new_rules.extend(
                Rule(**rule_spec)
                for rule_spec in self.full_feature_rules)

        return new_rules
