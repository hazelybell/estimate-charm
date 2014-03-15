# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'GeoIP',
    'GeoIPRequest',
    'RequestLocalLanguages',
    'RequestPreferredLanguages',
    ]

import os

import GeoIP as libGeoIP
from zope.component import getUtility
from zope.i18n.interfaces import IUserPreferredLanguages
from zope.interface import implements

from lp.services.config import config
from lp.services.geoip.helpers import ipaddress_from_request
from lp.services.geoip.interfaces import (
    IGeoIP,
    IGeoIPRecord,
    IRequestLocalLanguages,
    IRequestPreferredLanguages,
    )
from lp.services.propertycache import cachedproperty
from lp.services.worlddata.interfaces.country import ICountrySet
from lp.services.worlddata.interfaces.language import ILanguageSet


class GeoIP:
    """See `IGeoIP`."""
    implements(IGeoIP)

    @cachedproperty
    def _gi(self):
        if not os.path.exists(config.launchpad.geoip_database):
            raise NoGeoIPDatabaseFound(
                "No GeoIP DB found. Please install launchpad-dependencies.")
        return libGeoIP.open(
            config.launchpad.geoip_database, libGeoIP.GEOIP_MEMORY_CACHE)

    def getRecordByAddress(self, ip_address):
        """See `IGeoIP`."""
        ip_address = ensure_address_is_not_private(ip_address)
        try:
            return self._gi.record_by_addr(ip_address)
        except SystemError:
            # libGeoIP may raise a SystemError if it doesn't find a record for
            # some IP addresses (e.g. 255.255.255.255), so we need to catch
            # that and return None here.
            return None

    def getCountryByAddr(self, ip_address):
        """See `IGeoIP`."""
        ip_address = ensure_address_is_not_private(ip_address)
        geoip_record = self.getRecordByAddress(ip_address)
        if geoip_record is None:
            return None
        countrycode = geoip_record['country_code']

        countryset = getUtility(ICountrySet)
        try:
            country = countryset[countrycode]
        except KeyError:
            return None
        else:
            return country


class GeoIPRequest:
    """An adapter for a BrowserRequest into an IGeoIPRecord."""
    implements(IGeoIPRecord)

    def __init__(self, request):
        self.request = request
        ip_address = ipaddress_from_request(self.request)
        if ip_address is None:
            # This happens during page testing, when the REMOTE_ADDR is not
            # set by Zope.
            ip_address = '127.0.0.1'
        ip_address = ensure_address_is_not_private(ip_address)
        self.ip_address = ip_address
        self.geoip_record = getUtility(IGeoIP).getRecordByAddress(
            self.ip_address)

    @property
    def latitude(self):
        """See `IGeoIPRecord`."""
        if self.geoip_record is None:
            return None
        return self.geoip_record['latitude']

    @property
    def longitude(self):
        """See `IGeoIPRecord`."""
        if self.geoip_record is None:
            return None
        return self.geoip_record['longitude']

    @property
    def time_zone(self):
        """See `IGeoIPRecord`."""
        if self.geoip_record is None:
            return None
        return self.geoip_record['time_zone']


class RequestLocalLanguages(object):

    implements(IRequestLocalLanguages)

    def __init__(self, request):
        self.request = request

    def getLocalLanguages(self):
        """See the IRequestLocationLanguages interface"""
        ip_addr = ipaddress_from_request(self.request)
        if ip_addr is None:
            # this happens during page testing, when the REMOTE_ADDR is not
            # set by Zope
            ip_addr = '127.0.0.1'
        gi = getUtility(IGeoIP)
        country = gi.getCountryByAddr(ip_addr)
        if country in [None, 'A0', 'A1', 'A2']:
            return []

        languages = [
            language for language in country.languages if language.visible]
        return sorted(languages, key=lambda x: x.englishname)


class RequestPreferredLanguages(object):

    implements(IRequestPreferredLanguages)

    def __init__(self, request):
        self.request = request

    def getPreferredLanguages(self):
        """See the IRequestPreferredLanguages interface"""

        codes = IUserPreferredLanguages(self.request).getPreferredLanguages()
        languageset = getUtility(ILanguageSet)
        languages = set()

        for code in codes:
            # We need to ensure that the code received contains only ASCII
            # characters otherwise SQLObject will crash if it receives a query
            # with non printable ASCII characters.
            if isinstance(code, str):
                try:
                    code = code.decode('ASCII')
                except UnicodeDecodeError:
                    # skip language codes that can't be represented in ASCII
                    continue
            else:
                try:
                    code = code.encode('ASCII')
                except UnicodeEncodeError:
                    # skip language codes that can't be represented in ASCII
                    continue
            code = languageset.canonicalise_language_code(code)
            try:
                languages.add(languageset[code])
            except KeyError:
                pass

        languages = [language for language in languages if language.visible]
        return sorted(languages, key=lambda x: x.englishname)


def ensure_address_is_not_private(ip_address):
    """Return the given IP address if it doesn't start with '127.'.

    If it does start with '127.' then we return a South African IP address.
    Notice that we have no specific reason for using a South African IP
    address here -- we could have used any other non-private IP address.
    """
    private_prefixes = (
        '127.',
        '192.168.',
        '172.16.',
        '10.',
        )

    for prefix in private_prefixes:
        if ip_address.startswith(prefix):
            # This is an arbitrary South African IP which was handy at the
            # time of writing; it's not special in any way.
            return '196.36.161.227'
    return ip_address


class NoGeoIPDatabaseFound(Exception):
    """No GeoIP database was found."""
