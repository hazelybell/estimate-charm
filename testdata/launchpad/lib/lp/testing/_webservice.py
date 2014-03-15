# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'launchpadlib_credentials_for',
    'launchpadlib_for',
    'oauth_access_token_for',
    ]


import shutil
import tempfile

from launchpadlib.credentials import (
    AccessToken,
    AnonymousAccessToken,
    Credentials,
    )
from launchpadlib.launchpad import Launchpad
import transaction
from zope.app.testing import ztapi
from zope.component import getUtility
from zope.publisher.interfaces import IEndRequestEvent
import zope.testing.cleanup

from lp.registry.interfaces.person import IPersonSet
from lp.services.oauth.interfaces import IOAuthConsumerSet
from lp.services.webapp.adapter import get_request_statements
from lp.services.webapp.interaction import ANONYMOUS
from lp.services.webapp.interfaces import OAuthPermission
from lp.services.webapp.publisher import canonical_url
from lp.testing._login import (
    login,
    logout,
    )


def api_url(obj):
    """Find the web service URL of a data model object.

    This makes it easy to load up the factory object you just created
    in launchpadlib.

    :param: Which web service version to use.

    :return: A relative URL suitable for passing into Launchpad.load().
    """
    return canonical_url(obj, force_local_path=True)


def oauth_access_token_for(consumer_name, person, permission, context=None):
    """Find or create an OAuth access token for the given person.
    :param consumer_name: An OAuth consumer name.
    :param person: A person (or the name of a person) for whom to create
        or find credentials.
    :param permission: An OAuthPermission (or its token) designating
        the level of permission the credentials should have.
    :param context: The OAuth context for the credentials (or a string
        designating same).

    :return: An OAuthAccessToken object.
    """
    if isinstance(person, basestring):
        # Look up a person by name.
        person = getUtility(IPersonSet).getByName(person)
    if isinstance(context, basestring):
        # Turn an OAuth context string into the corresponding object.
        # Avoid an import loop by importing from launchpad.browser here.
        from lp.services.oauth.browser import lookup_oauth_context
        context = lookup_oauth_context(context)
    if isinstance(permission, basestring):
        # Look up a permission by its token string.
        permission = OAuthPermission.items[permission]

    # Find or create the consumer object.
    consumer_set = getUtility(IOAuthConsumerSet)
    consumer = consumer_set.getByKey(consumer_name)
    if consumer is None:
        consumer = consumer_set.new(consumer_name)
    else:
        # We didn't have to create the consumer. Maybe this user
        # already has an access token for this
        # consumer+person+permission?
        existing_token = [token for token in person.oauth_access_tokens
                          if (token.consumer == consumer
                              and token.permission == permission
                              and token.context == context)]
        if len(existing_token) >= 1:
            return existing_token[0]

    # There is no existing access token for this
    # consumer+person+permission+context. Create one and review it.
    request_token = consumer.newRequestToken()
    request_token.review(person, permission, context)
    access_token = request_token.createAccessToken()
    return access_token


def launchpadlib_credentials_for(
    consumer_name, person, permission=OAuthPermission.WRITE_PRIVATE,
    context=None):
    """Create launchpadlib credentials for the given person.

    :param consumer_name: An OAuth consumer name.
    :param person: A person (or the name of a person) for whom to create
        or find credentials.
    :param permission: An OAuthPermission (or its token) designating
        the level of permission the credentials should have.
    :param context: The OAuth context for the credentials.
    :return: A launchpadlib Credentials object.
    """
    # Start an interaction so that oauth_access_token_for will
    # succeed.  oauth_access_token_for may be called in any layer, but
    # launchpadlib_credentials_for is only called in the
    # PageTestLayer, when a Launchpad instance is running for
    # launchpadlib to use.
    login(ANONYMOUS)
    access_token = oauth_access_token_for(
        consumer_name, person, permission, context)
    logout()
    launchpadlib_token = AccessToken(
        access_token.key, access_token.secret)
    return Credentials(consumer_name=consumer_name,
                       access_token=launchpadlib_token)


def _clean_up_cache(cache):
    """Clean up a temporary launchpadlib cache directory."""
    shutil.rmtree(cache, ignore_errors=True)


def launchpadlib_for(
    consumer_name, person=None, permission=OAuthPermission.WRITE_PRIVATE,
    context=None, version="devel", service_root="http://api.launchpad.dev/"):
    """Create a Launchpad object for the given person.

    :param consumer_name: An OAuth consumer name.
    :param person: A person (or the name of a person) for whom to create
        or find credentials.
    :param permission: An OAuthPermission (or its token) designating
        the level of permission the credentials should have.
    :param context: The OAuth context for the credentials.
    :param version: The version of the web service to access.
    :param service_root: The root URL of the web service to access.

    :return: A launchpadlib Launchpad object.
    """
    if person is None:
        token = AnonymousAccessToken()
        credentials = Credentials(consumer_name, access_token=token)
    else:
        credentials = launchpadlib_credentials_for(
            consumer_name, person, permission, context)
    transaction.commit()
    cache = tempfile.mkdtemp(prefix='launchpadlib-cache-')
    zope.testing.cleanup.addCleanUp(_clean_up_cache, (cache,))
    return Launchpad(credentials, None, None, service_root=service_root,
                     version=version, cache=cache)


class QueryCollector:
    """Collect database calls made in web requests.

    These are only retrievable at the end of a request, and for tests it is
    useful to be able to make assertions about the calls made during a
    request: this class provides a tool to gather them in a simple fashion.

    :ivar count: The count of db queries the last web request made.
    :ivar queries: The list of queries made. See
        lp.services.webapp.adapter.get_request_statements for more
        information.
    """

    def __init__(self):
        self._active = False
        self.count = None
        self.queries = None

    def register(self):
        """Start counting queries.

        Be sure to call unregister when finished with the collector.

        After each web request the count and queries attributes are updated.
        """
        ztapi.subscribe((IEndRequestEvent, ), None, self)
        self._active = True

    def __enter__(self):
        self.register()
        return self

    def __call__(self, event):
        if self._active:
            self.queries = get_request_statements()
            self.count = len(self.queries)

    def unregister(self):
        self._active = False

    def __exit__(self, exc_type, exc_value, traceback):
        self.unregister()
