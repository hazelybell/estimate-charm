# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import re

from zope.component import getUtility

from lp.services.geoip.interfaces import IGeoIP


__all__ = [
    'request_country',
    'ipaddress_from_request',
    ]


def request_country(request):
    """Adapt a request to the country in which the request was made.

    Return None if the remote IP address is unknown or its country is not in
    our database.

    This information is not reliable and trivially spoofable - use it only
    for selecting sane defaults.
    """
    ipaddress = ipaddress_from_request(request)
    if ipaddress is not None:
        return getUtility(IGeoIP).getCountryByAddr(ipaddress)
    return None


_ipaddr_re = re.compile('\d\d?\d?\.\d\d?\d?\.\d\d?\d?\.\d\d?\d?')


def ipaddress_from_request(request):
    """Determine the IP address for this request.

    Returns None if the IP address cannot be determined or is localhost.

    The remote IP address is determined by the X-Forwarded-For: header,
    or failing that, the REMOTE_ADDR CGI environment variable.

    Because this information is unreliable and trivially spoofable, we
    don't bother to do much error checking to ensure the IP address is at all
    valid.

    >>> google = '66.102.7.104'
    >>> ipaddress_from_request({'REMOTE_ADDR': '1.1.1.1'})
    '1.1.1.1'
    >>> ipaddress_from_request({
    ...     'HTTP_X_FORWARDED_FOR': '666.666.666.666',
    ...     'REMOTE_ADDR': '1.1.1.1'
    ...     })
    '666.666.666.666'
    >>> ipaddress_from_request({'HTTP_X_FORWARDED_FOR':
    ...     'localhost, 127.0.0.1, 255.255.255.255,1.1.1.1'
    ...     })
    '255.255.255.255'
    """
    ipaddresses = request.get('HTTP_X_FORWARDED_FOR')

    if ipaddresses is None:
        ipaddresses = request.get('REMOTE_ADDR')

    if ipaddresses is None:
        return None

    # We actually get a comma separated list of addresses. We need to throw
    # away the obvious duds, such as loopback addresses
    ipaddresses = [addr.strip() for addr in ipaddresses.split(',')]
    ipaddresses = [
        addr for addr in ipaddresses
            if not (addr.startswith('127.')
                    or _ipaddr_re.search(addr) is None)]

    if ipaddresses:
        # If we have more than one, have a guess.
        return ipaddresses[0]
    return None
