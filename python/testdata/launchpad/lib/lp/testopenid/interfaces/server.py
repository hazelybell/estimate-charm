# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'get_server_url',
    'ITestOpenIDApplication',
    'ITestOpenIDLoginForm',
    'ITestOpenIDPersistentIdentity',
    ]

from zope.interface import Interface
from zope.schema import TextLine

from lp.services.openid.interfaces.openid import IOpenIDPersistentIdentity
from lp.services.webapp.interfaces import ILaunchpadApplication
from lp.services.webapp.url import urlappend
from lp.services.webapp.vhosts import allvhosts


class ITestOpenIDApplication(ILaunchpadApplication):
    """Launchpad's testing OpenID application root."""


class ITestOpenIDLoginForm(Interface):
    email = TextLine(title=u'What is your e-mail address?', required=True)


class ITestOpenIDPersistentIdentity(IOpenIDPersistentIdentity):
    """Marker interface for IOpenIDPersistentIdentity on testopenid."""


def get_server_url():
    """Return the URL for this server's OpenID endpoint.

    This is wrapped in a function (instead of a constant) to make sure the
    vhost.testopenid section is not required in production configs.
    """
    return urlappend(allvhosts.configs['testopenid'].rooturl, '+openid')
