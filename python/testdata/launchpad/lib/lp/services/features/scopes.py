# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Connect feature flags into scopes where they can be used.

The most common is flags scoped by some attribute of a web request, such as
the page ID or the server name.  But other types of scope can also match code
run from cron scripts and potentially also other places.
"""

__all__ = [
    'DefaultScope',
    'default_scopes',
    'FixedScope',
    'HANDLERS',
    'MultiScopeHandler',
    'ScopesForScript',
    'ScopesFromRequest',
    'TeamScope',
    'UserSliceScope',
    'undocumented_scopes',
    ]

__metaclass__ = type

import re

from lp.registry.interfaces.person import IPerson
import lp.services.config
from lp.services.propertycache import cachedproperty


undocumented_scopes = set()


class BaseScope():
    """A base class for scope handlers.

    The docstring of subclasses is used on the +feature-info page as
    documentation, so write them accordingly.
    """

    # The regex pattern used to decide if a handler can evaluate a particular
    # scope.  Also used on +feature-info.
    pattern = None

    @cachedproperty
    def compiled_pattern(self):
        """The compiled scope matching regex.  A small optimization."""
        return re.compile(self.pattern)

    def lookup(self, scope_name):
        """Returns true if the given scope name is "active"."""
        raise NotImplementedError('Subclasses of BaseScope must implement '
            'lookup.')


class DefaultScope(BaseScope):
    """The default scope.  Always active."""

    pattern = r'default$'

    def lookup(self, scope_name):
        return True


class PageScope(BaseScope):
    """The current page ID.

    Pageid scopes are written as 'pageid:' + the pageid to match.  Pageids
    are treated as a namespace with : and # delimiters.

    For example, the scope 'pageid:Foo' will be active on pages with pageids:
        Foo
        Foo:Bar
        Foo#quux
    """

    pattern = r'pageid:'

    def __init__(self, request):
        self._request = request

    def lookup(self, scope_name):
        """Is the given scope match the current pageid?"""
        pageid_scope = scope_name[len('pageid:'):]
        scope_segments = self._pageid_to_namespace(pageid_scope)
        request_segments = self._request_pageid_namespace
        # In 2.6, this can be replaced with izip_longest
        for pos, name in enumerate(scope_segments):
            if pos == len(request_segments):
                return False
            if request_segments[pos] != name:
                return False
        return True

    @staticmethod
    def _pageid_to_namespace(pageid):
        """Return a list of namespace elements for pageid."""
        # Normalise delimiters.
        pageid = pageid.replace('#', ':')
        # Create a list to walk, empty namespaces are elided.
        return [name for name in pageid.split(':') if name]

    @cachedproperty
    def _request_pageid_namespace(self):
        return tuple(self._pageid_to_namespace(
            self._request._orig_env.get('launchpad.pageid', '')))


class ScopeWithPerson(BaseScope):
    """An abstract base scope that matches on the current user of the request.

    Intended for subclassing, not direct use.
    """

    def __init__(self, get_person):
        self._get_person = get_person

    @cachedproperty
    def person(self):
        return self._get_person()


class TeamScope(ScopeWithPerson):
    """A user's team memberships.

    Team ID scopes are written as 'team:' + the team name to match.

    The scope 'team:launchpad-beta-users' will match members of the team
    'launchpad-beta-users'.

    The constructor takes a callable that returns the currently logged in
    person because Scopes are set up very early in the request publication
    process -- in particular, before authentication has happened.
    """

    pattern = r'team:'

    def lookup(self, scope_name):
        """Is the given scope a team membership?

        This will do a two queries, so we probably want to keep the number of
        team based scopes in use to a small number. (Person.inTeam could be
        fixed to reduce this to one query).
        """
        if self.person is not None:
            team_name = scope_name[len('team:'):]
            return self.person.inTeam(team_name)


class UserSliceScope(ScopeWithPerson):
    """Selects a slice of all users based on their id.

    Written as 'userslice:a,b' with 0<=a<b will slice the entire user
    population into b approximately equal sub-populations, and then take the
    a'th zero-based index.

    For example, to test a new feature for 1% of users, and a different
    version of it for a different 1% you can use `userslice:10,100` and
    userslice:20,100`.

    You may wish to avoid using the same a or b for different rules so that
    some users don't have all the fun by being in eg 0,100.
    """

    pattern = r'userslice:(\d+),(\d+)'

    def lookup(self, scope_name):
        match = self.compiled_pattern.match(scope_name)
        if not match:
            return  # Shouldn't happen...
        try:
            modulus = int(match.group(1))
            divisor = int(match.group(2))
        except ValueError:
            return
        person_id = self.person.id
        return (person_id % divisor) == modulus


class ServerScope(BaseScope):
    """Matches the current server.

    For example, the scope server.lpnet is active when is_lpnet is set to True
    in the Launchpad configuration.
    """

    pattern = r'server\.'

    def lookup(self, scope_name):
        """Match the current server as a scope."""
        server_name = scope_name.split('.', 1)[1]
        try:
            return lp.services.config.config['launchpad']['is_' + server_name]
        except KeyError:
            pass
        return False


class ScriptScope(BaseScope):
    """Matches the name of the currently running script.

    For example, the scope script:embroider is active in a script called
    "embroider."
    """

    pattern = r'script:'

    def __init__(self, script_name):
        self.script_scope = self.pattern + script_name

    def lookup(self, scope_name):
        """Match the running script as a scope."""
        return scope_name == self.script_scope


class FixedScope(BaseScope):
    """A scope that matches an exact value.

    Functionally `ScriptScope` and `DefaultScope` are equivalent to instances
    of this class, but their docstings are used on the +feature-info page.
    """

    def __init__(self, scope):
        self.pattern = re.escape(scope) + '$'

    def lookup(self, scope_name):
        return True


# These are the handlers for all of the allowable scopes, listed here so that
# we can for example show all of them in an admin page.  Any new scope will
# need a scope handler and that scope handler has to be added to this list.
# See BaseScope for hints as to what a scope handler should look like.
HANDLERS = set([DefaultScope, PageScope, TeamScope, ServerScope, ScriptScope])


class MultiScopeHandler():
    """A scope handler that combines multiple `BaseScope`s.

    The ordering in which they're added is arbitrary, because precedence is
    determined by the ordering of rules.
    """

    def __init__(self, scopes):
        self.handlers = scopes

    def _findMatchingHandlers(self, scope_name):
        """Find any handlers that match `scope_name`."""
        return [
            handler
            for handler in self.handlers
                if handler.compiled_pattern.match(scope_name)]

    def lookup(self, scope_name):
        """Determine if scope_name applies.

        This method iterates over the configured scope handlers until it
        either finds one that claims the requested scope name matches,
        or the handlers are exhausted, in which case the
        scope name is not a match.
        """
        matching_handlers = self._findMatchingHandlers(scope_name)
        for handler in matching_handlers:
            if handler.lookup(scope_name):
                return True

        # If we didn't find at least one matching handler, then the
        # requested scope is unknown and we want to record the scope for
        # the +flag-info page to display.
        if len(matching_handlers) == 0:
            undocumented_scopes.add(scope_name)


default_scopes = (DefaultScope(),)


class ScopesFromRequest(MultiScopeHandler):
    """Identify feature scopes based on request state.

    Because the feature controller is constructed very very early in the
    publication process, this needs to be very careful about looking at the
    request -- in particular, this is called before authentication happens.
    """

    def __init__(self, request):
        def person_from_request():
            return IPerson(request.principal, None)
        scopes = list(default_scopes)
        scopes.extend([
            PageScope(request),
            ServerScope(),
            TeamScope(person_from_request),
            UserSliceScope(person_from_request),
            ])
        super(ScopesFromRequest, self).__init__(scopes)


class ScopesForScript(MultiScopeHandler):
    """Identify feature scopes for a given script."""

    def __init__(self, script_name):
        scopes = list(default_scopes)
        scopes.append(ScriptScope(script_name))
        super(ScopesForScript, self).__init__(scopes)
