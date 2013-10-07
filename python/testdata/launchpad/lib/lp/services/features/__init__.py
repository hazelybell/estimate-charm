# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Dynamic feature configuration.

Introduction
============

The point of feature flags is to let us turn some features of Launchpad on
and off without changing the code or restarting the application, and to
expose different features to different subsets of users.

See U{https://dev.launchpad.net/LEP/FeatureFlags} for more discussion and
rationale.

The typical use for feature flags is within web page requests but they can
also be used in asynchronous jobs or apis or other parts of Launchpad.

Internal model for feature flags
================================

A feature flag maps from a I{name} to a I{value}.  The specific value used
for a particular request is determined by a set of zero or more I{scopes}
that apply to that request, by finding the I{rule} with the highest
I{priority}.

Flags are defined by a I{name} that typically looks like a Python
identifier, for example C{notification.global.text}.  A definition is
given for a particular I{scope}, which also looks like a dotted identifier,
for example C{user.beta} or C{server.lpnet}.  This is just a naming
convention, and they do not need to correspond to Python modules.

The value is stored in the database as just a Unicode string, and it might
be interpreted as a boolean, number, human-readable string or whatever.

The default for flags is to be None if they're not set in the database, so
that should be a sensible baseline default state.

Performance model
=================

Flags are supposed to be cheap enough that you can introduce them without
causing a performance concern.

If the page does not check any flags, no extra work will be done.  The
first time a page checks a flag, all the rules will be read from the
database and held in memory for the duration of the request.

Scopes may be expensive in some cases, such as checking group membership.
Whether a scope is active or not is looked up the first time it's needed
within a particular request.

The standard page footer identifies the flags and scopes that were
actually used by the page.

Naming conventions
==================

We have naming conventions for feature flags and scopes, so that people can
understand the likely impact of a particular flag and so they can find all
the flags likely to affect a feature.

So for any flag we want to say:

  - What application area does this affect? (malone, survey, questions,
    code, etc)

  - What specific feature does it change?

  - What affect does it have on this feature?  The most common is "enabled"
    but for some other we want to specify a specific value as well such as
    "date" or "size".

These are concatenated with dots so the overall feature name looks a bit
like a Python module name.

A similar approach is used for scopes.

Checking flags in page templates
================================

You can conditionally show some text like this::

  <tal:survey condition="features/user_survey.enabled">
    &nbsp;&bull;&nbsp;
    <a href="http://survey.example.com/">Take our survey!</a>
  </tal:survey>

You can use the built-in TAL feature of prepending C{not:} to the
condition, and for flags that have a value you could use them in
C{tal:replace} or C{tal:attributes}.

If you just want to simply insert some text taken from a feature, say
something like::

  Message of the day: ${motd.text}

Templates can also check whether the request is in a particular scope, but
before using this consider whether the code will always be bound to that
scope or whether it would be more correct to define a new feature::

  <p tal:condition="feature_scopes/server.staging">
    Staging server: all data will be discarded daily!</p>

Checking flags in code
======================

The Zope traversal code establishes a `FeatureController` for the duration
of a request.  The object can be obtained through either
`request.features` or `lp.services.features.per_thread.features`.  This
provides various useful methods including `getFlag` to look up one feature
(memoized), and `isInScope` to check one scope (also memoized).

As a convenience, `lp.services.features.getFeatureFlag` looks up a single
flag in the thread default controller.

To simply check a boolean::

    if features.getFeatureFlag('example_flag.enabled'):
        ...

and if you want to use the value ::

     value = features.getFeatureFlag('example_flag.enabled')
     if value:
        print value

Checking flags without access to the database
=============================================

Feature flags can also be checked without access to the database by making use
of the 'getFeatureFlag' XML-RPC method.

    server_proxy = xmlrpclib.ServerProxy(
        config.launchpad.feature_flags_endpoint, allow_none=True)
    if server_proxy.getFeatureFlag(
        'codehosting.use_forking_server', ['user:' + user_name]):
        pass

Debugging feature usage
=======================

The flags active during a page request, and the scopes that were looked
up are visible in the comment at the bottom of every standard Launchpad
page.


Setting flags in your tests
===========================

lp.services.features.testing contains a fixture that can help you temporarily
set feature flags during a test run.  All existing flags will be removed and
the new flag values set.  The old flags are restored when the fixture is
cleaned up.

The lp.testing.TestCase class has built-in support for test fixtures.  To
set a flag for the duration of a test::

    from lp.services.features.testing import FeatureFixture

    def setUp(self):
        self.useFixture(FeatureFixture({'myflag', 'on'}))


You can also use the fixture as a context manager::

    with FeatureFixture({'myflag': 'on'}):
        ...


You can call the fixture's setUp() and cleanUp() methods for doctests and
other environments that have no explicit setup and teardown::

    >>> from lp.services.features.testing import FeatureFixture
    >>> fixture = FeatureFixture({'my-doctest-flag': 'on'})
    >>> fixture.setUp()
    ...
    >>> fixture.cleanUp()

"""

import threading

from lazr.restful.utils import safe_hasattr


__all__ = [
    'currentScope',
    'defaultFlagValue',
    'get_relevant_feature_controller',
    'getFeatureFlag',
    'install_feature_controller',
    'make_script_feature_controller',
    ]


per_thread = threading.local()
"""Holds the default per-thread feature controller in its .features attribute.

Framework code is responsible for setting this in the appropriate context, eg
when starting a web request.
"""


def install_feature_controller(controller):
    """Install a `FeatureController` on this thread."""
    per_thread.features = controller


def uninstall_feature_controller():
    """Remove, if it exists, the current feature controller from this thread.

    This function is used to create a pristine environment in tests.
    """
    if safe_hasattr(per_thread, 'features'):
        del per_thread.features


def get_relevant_feature_controller():
    """Get a `FeatureController` for this thread."""
    # The noncommittal name "relevant" is because this function may change to
    # look things up from the current request or some other mechanism in
    # future.
    return getattr(per_thread, 'features', None)


def getFeatureFlag(flag):
    """Get the value of a flag for this thread's scopes."""
    # Workaround for bug 631884 - features have two homes, threads and
    # requests.
    features = get_relevant_feature_controller()
    if features is None:
        return None
    return features.getFlag(flag)


def currentScope(flag):
    """Get the current scope of the flag for this thread's scopes."""
    # Workaround for bug 631884 - features have two homes, threads and
    # requests.
    features = get_relevant_feature_controller()
    if features is None:
        return None
    return features.currentScope(flag)


def defaultFlagValue(flag):
    features = get_relevant_feature_controller()
    if features is None:
        return None
    return features.defaultFlagValue(flag)


def make_script_feature_controller(script_name):
    """Create a `FeatureController` for the named script.

    You can then install this feature controller using
    `install_feature_controller`.
    """
    # Avoid circular import.
    from lp.services.features.flags import FeatureController
    from lp.services.features.rulesource import StormFeatureRuleSource
    from lp.services.features.scopes import ScopesForScript

    return FeatureController(
        ScopesForScript(script_name).lookup, StormFeatureRuleSource())
