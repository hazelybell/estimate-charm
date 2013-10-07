# Copyright 2010-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'FeatureController',
    'flag_info',
    'NullFeatureController',
    'undocumented_flags',
    'value_domain_info',
    ]


import logging

from lp.services.features.rulesource import (
    NullFeatureRuleSource,
    StormFeatureRuleSource,
    )


__metaclass__ = type


logger = logging.getLogger('lp.services.features')

value_domain_info = sorted([
    ('boolean',
     'Any non-empty value is true; an empty value is false.'),
    ('float',
     'The flag value is set to the given floating point number.'),
    ('int',
     "An integer."),
    ('space delimited',
     'Space-delimited strings.'),
    ('datetime',
     'ISO 8601 datetime'),
    ])

# Data for generating web-visible feature flag documentation.
#
# Entries for each flag are:
# 1. flag name
# 2. value domain
# 3. prose documentation
# 4. default behaviour
# 5. title
# 6. URL to a page with more information about the feature.
#
# Value domain as in value_domain_info above.
#
# NOTE: "default behaviour" does not specify a default value.  It
# merely documents the code's behaviour if no value is specified.
flag_info = sorted([
    ('baselayout.careers_link.disabled',
     'boolean',
     'Hide the link to the Canonical Careers site.',
     '',
     '',
     ''),
    ('bugs.affected_count_includes_dupes.disabled',
     'boolean',
     ("Disable adding up affected users across all duplicate bugs."),
     '',
     '',
     'https://bugs.launchpad.net/launchpad/+bug/678090'),
    ('bugs.bugtracker_components.enabled',
     'boolean',
     ('Enables the display of bugtracker components.'),
     '',
     '',
     ''),
    ('bugs.dynamic_bug_listings.pre_fetch',
     'boolean',
     ('Enables pre-fetching bug listing results.'),
     '',
     'Listing pre-fetching',
     'https://bugs.launchpad.net/launchpad/+bug/888756'),
    ('bugs.heat_updates.cutoff',
     'timestamp',
     ('Set the oldest that a bug\'s heat can be before it is '
      'considered outdated.'),
     '',
     '',
     ''),
    ('code.ajax_revision_diffs.enabled',
     'boolean',
     ("Offer expandable inline diffs for branch revisions."),
     '',
     '',
     ''),
    ('code.branchmergequeue',
     'boolean',
     'Enables merge queue pages and lists them on branch pages.',
     '',
     '',
     ''),
    ('code.incremental_diffs.enabled',
     'boolean',
     'Shows incremental diffs on merge proposals.',
     '',
     '',
     ''),
    ('hard_timeout',
     'float',
     'Sets the hard request timeout in milliseconds.',
     '',
     '',
     ''),
    ('jobs.celery.enabled_classes',
     'space delimited',
     'Names of Job classes that should be run via celery',
     'No jobs run via celery',
     'Celery-enabled job classes',
     'https://dev.launchpad.net/CeleryJobRunner'),
    ('js.yui_version',
     'space delimited',
     'Allows us to change the YUI version we run against, e.g. yui-3.4.',
     'As speficied in versions.cfg',
     '',
     ''),
    ('mail.dkim_authentication.disabled',
     'boolean',
     'Disable DKIM authentication checks on incoming mail.',
     '',
     '',
     ''),
    ('markdown.enabled',
     'boolean',
     'Interpret selected user content as Markdown.',
     'disabled',
     'Markdown',
     'https://launchpad.net/bugs/391780'),
    ('memcache',
     'boolean',
     'Enables use of memcached where it is supported.',
     'enabled',
     '',
     ''),
    ('profiling.enabled',
     'boolean',
     'Overrides config.profiling.profiling_allowed to permit profiling.',
     '',
     '',
     ''),
    ('soyuz.derived_series_upgrade.enabled',
     'boolean',
     'Enables mass-upgrade of packages on derivative distributions pages.',
     '',
     '',
     ''),
    ('visible_render_time',
     'boolean',
     'Shows the server-side page render time in the login widget.',
     '',
     '',
     ''),
    ('bugs.autoconfirm.enabled_distribution_names',
     'space delimited',
     ('Enables auto-confirming bugtasks for distributions (and their '
      'series and packages).  Use the default domain.  Specify a single '
      'asterisk ("*") to enable for all distributions.'),
     'None are enabled',
     '',
     ''),
    ('bugs.autoconfirm.enabled_product_names',
     'space delimited',
     ('Enables auto-confirming bugtasks for products (and their '
      'series).  Use the default domain.  Specify a single '
      'asterisk ("*") to enable for all products.'),
     'None are enabled',
     '',
     ''),
    ('longpoll.merge_proposals.enabled',
     'boolean',
     ('Enables the longpoll mechanism for merge proposals so that diffs, '
      'for example, are updated in-page when they are ready.'),
     '',
     '',
     ''),
    ('ajax.batch_navigator.enabled',
     'boolean',
     ('If true, batch navigators which have been wired to do so use ajax '
     'calls to load the next batch of data.'),
     '',
     '',
     ''),
    ('registry.upcoming_work_view.enabled',
     'boolean',
     ('If true, the new upcoming work view of teams is available.'),
     '',
     '',
     ''),
    ('soyuz.gina.skip_source_versions',
     'space delimited',
     ('List of source versions for gina to skip when importing into a '
      'distribution, formatted as distro/package/version.'),
     '',
     '',
     ''),
    ('auditor.enabled',
     'boolean',
     'If true, send audit data to an auditor instance.',
     '',
     '',
     ''),
    ('app.root_blog.enabled',
     'boolean',
     'If true, load posts from the Launchpad blog to show on the root page.',
     '',
     '',
     ''),
    ])

# The set of all flag names that are documented.
documented_flags = set(info[0] for info in flag_info)
# The set of all the flags names that have been used during the process
# lifetime, but were not documented in flag_info.
undocumented_flags = set()


class Memoize():

    def __init__(self, calc):
        self._known = {}
        self._calc = calc

    def lookup(self, key):
        if key in self._known:
            return self._known[key]
        v = self._calc(key)
        self._known[key] = v
        return v


class ScopeDict():
    """Allow scopes to be looked up by getitem"""

    def __init__(self, features):
        self.features = features

    def __getitem__(self, scope_name):
        return self.features.isInScope(scope_name)


class FeatureController():
    """A FeatureController tells application code what features are active.

    It does this by meshing together two sources of data:

      - feature flags, typically set by an administrator into the database

      - feature scopes, which would typically be looked up based on attributes
      of the current web request, or the user for whom a job is being run, or
      something similar.

    FeatureController presents a high level interface for application code to
    query flag values, without it needing to know that they are stored in the
    database.

    At this level flag names and scope names are presented as strings for
    easier use in Python code, though the values remain unicode.  They
    should always be ascii like Python identifiers.

    One instance of FeatureController should be constructed for the lifetime
    of code that has consistent configuration values.  For instance there will
    be one per web app request.

    Intended performance: when this object is first asked about a flag, it
    will read the whole feature flag table from the database.  It is expected
    to be reasonably small.  The scopes may be expensive to compute (eg
    checking team membership) so they are checked at most once when
    they are first needed.

    The controller is then supposed to be held in a thread-local and reused
    for the duration of the request.

    @see: U{https://dev.launchpad.net/LEP/FeatureFlags}
    """

    def __init__(self, scope_check_callback, rule_source=None):
        """Construct a new view of the features for a set of scopes.

        :param scope_check_callback: Given a scope name, says whether
            it's active or not.

        :param rule_source: Instance of StormFeatureRuleSource or similar.
        """
        self._known_scopes = Memoize(scope_check_callback)
        self._known_flags = Memoize(self._checkFlag)
        # rules are read from the database the first time they're needed
        self._rules = None
        self.scopes = ScopeDict(self)
        if rule_source is None:
            rule_source = StormFeatureRuleSource()
        self.rule_source = rule_source
        self._current_scopes = Memoize(self._findCurrentScope)

    def getFlag(self, flag):
        """Get the value of a specific flag.

        :param flag: A name to lookup. e.g. 'recipes.enabled'

        :return: The value of the flag determined by the highest priority rule
        that matched.
        """
        # If this is an undocumented flag, record it.
        if flag not in documented_flags:
            undocumented_flags.add(flag)
        return self._known_flags.lookup(flag)

    def _checkFlag(self, flag):
        return self._currentValueAndScope(flag)[0]

    def _currentValueAndScope(self, flag):
        self._needRules()
        if flag in self._rules:
            for scope, priority, value in self._rules[flag]:
                if self._known_scopes.lookup(scope):
                    self._debugMessage(
                        'feature match flag=%r value=%r scope=%r' %
                        (flag, value, scope))
                    return (value, scope)
            else:
                self._debugMessage('no rules matched for %r' % flag)
        else:
            self._debugMessage('no rules relevant to %r' % flag)
        return (None, None)

    def _debugMessage(self, message):
        logger.debug(message)
        # The OOPS machinery can also grab it out of the request if needed.

    def currentScope(self, flag):
        """The name of the scope of the matching rule with the highest
        priority.
        """
        return self._current_scopes.lookup(flag)

    def _findCurrentScope(self, flag):
        """Lookup method for self._current_scopes. See also `currentScope()`.
        """
        return self._currentValueAndScope(flag)[1]

    def isInScope(self, scope):
        return self._known_scopes.lookup(scope)

    def __getitem__(self, flag_name):
        """FeatureController can be indexed.

        This is to support easy zope traversal through eg
        "request/features/a.b.c".  We don't support other collection
        protocols.

        Note that calling this the first time for any key may cause
        arbitrarily large amounts of work to be done to determine if the
        controller is in any scopes relevant to this flag.
        """
        return self.getFlag(flag_name)

    def getAllFlags(self):
        """Return a dict of all active flags.

        This may be expensive because of evaluating many scopes, so it
        shouldn't normally be used by code that only wants to know about one
        or a few flags.
        """
        self._needRules()
        return dict((f, self.getFlag(f)) for f in self._rules)

    def _needRules(self):
        if self._rules is None:
            self._rules = self.rule_source.getAllRulesAsDict()

    def usedFlags(self):
        """Return dict of flags used in this controller so far."""
        return dict(self._known_flags._known)

    def usedScopes(self):
        """Return {scope: active} for scopes that have been used so far."""
        return dict(self._known_scopes._known)

    def defaultFlagValue(self, flag):
        """Return the flag's value in the default scope."""
        self._needRules()
        if flag in self._rules:
            for scope, priority, value in self._rules[flag]:
                if scope == 'default':
                    return value
        return None


class NullFeatureController(FeatureController):
    """For use in testing: everything is turned off"""

    def __init__(self):
        FeatureController.__init__(self, lambda scope: None,
            NullFeatureRuleSource())
