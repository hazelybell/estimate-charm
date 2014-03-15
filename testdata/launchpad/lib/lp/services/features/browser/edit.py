# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View and edit feature rules."""

__metaclass__ = type
__all__ = [
    'FeatureControlView',
    'IFeatureControlForm',
    ]


from difflib import unified_diff
import logging

from zope.formlib.widgets import TextAreaWidget
from zope.interface import Interface
from zope.schema import Text

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.browser.stringformatter import FormattersAPI
from lp.services.features.changelog import ChangeLog
from lp.services.features.rulesource import DuplicatePriorityError
from lp.services.webapp.authorization import check_permission


class IFeatureControlForm(Interface):
    """Interface specifically for editing a text form of feature rules"""

    def __init__(self, context):
        self.context = context

    feature_rules = Text(
        title=u"Feature rules",
        description=(
            u"Rules to control feature flags on Launchpad.  "
            u"On each line: (flag, scope, priority, value), "
            u"whitespace-separated.  Numerically higher "
            u"priorities match first."),
        required=False)
    comment = Text(
        title=u"Comment",
        description=(u"Who requested this change and why."),
        required=True)


class FeatureControlView(LaunchpadFormView):
    """Text view of feature rules.

    Presents a text area, either read-only or read-write, showing currently
    active rules.
    """

    schema = IFeatureControlForm
    page_title = label = 'Feature control'
    diff = None
    logger_name = 'lp.services.features'
    custom_widget('comment', TextAreaWidget, height=2)

    @property
    def field_names(self):
        if self.canSubmit(None):
            return ['feature_rules', 'comment']
        else:
            return []

    def canSubmit(self, action):
        """Is the user authorized to change the rules?"""
        return check_permission('launchpad.Admin', self.context)

    @action(u"Change", name="change", condition=canSubmit)
    def change_action(self, action, data):
        original_rules = self.request.features.rule_source.getAllRulesAsText()
        rules_text = data.get('feature_rules') or ''
        logger = logging.getLogger(self.logger_name)
        logger.warning("Change feature rules to: %s" % (rules_text,))
        logger.warning("Previous feature rules were: %s" % (original_rules,))
        self.request.features.rule_source.setAllRulesFromText(rules_text)
        # Why re-fetch the rules here?  This way we get them reformatted
        # (whitespace normalized) and ordered consistently so the diff is
        # minimal.
        new_rules = self.request.features.rule_source.getAllRulesAsText()
        diff = u'\n'.join(self.diff_rules(original_rules, new_rules))
        comment = data['comment']
        ChangeLog.append(diff, comment, self.user)
        self.diff = FormattersAPI(diff).format_diff()

    @staticmethod
    def diff_rules(rules1, rules2):
        # Just generate a one-block diff.
        lines_of_context = 999999
        diff = unified_diff(
            rules1.splitlines(),
            rules2.splitlines(),
            n=lines_of_context)
        # The three line header is meaningless here.
        return list(diff)[3:]

    @property
    def initial_values(self):
        return {
            'feature_rules':
                self.request.features.rule_source.getAllRulesAsText(),
        }

    def validate(self, data):
        # Try parsing the rules so we give a clean error: at the moment the
        # message is not great, but it's better than an oops.
        try:
            # Unfortunately if the field is '', zope leaves it out of data.
            self.request.features.rule_source.parseRules(
                data.get('feature_rules') or '')
        except (IndexError, TypeError, ValueError,
                DuplicatePriorityError) as e:
            self.setFieldError('feature_rules', 'Invalid rule syntax: %s' % e)
