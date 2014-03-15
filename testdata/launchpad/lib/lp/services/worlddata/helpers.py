# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Worlddata helper functions."""

__metaclass__ = type
__all__ = [
    'browser_languages',
    'is_english_variant',
    'preferred_or_request_languages',
    ]


from zope.component import getUtility

from lp.services.geoip.interfaces import (
    IRequestLocalLanguages,
    IRequestPreferredLanguages,
    )
from lp.services.webapp.interfaces import ILaunchBag


def browser_languages(request):
    """Return a list of Language objects based on the browser preferences."""
    return IRequestPreferredLanguages(request).getPreferredLanguages()


def is_english_variant(language):
    """Return whether the language is a variant of modern English ."""
    # XXX sinzui 2007-07-12 bug=125545:
    # We would not need to use this function so often if variant languages
    # knew their parent language.
    return language.code[0:3] in ['en_']


def preferred_or_request_languages(request):
    """Turn a request into a list of languages to show.

    Return Person.languages when the user has preferred languages.
    Otherwise, return the languages from the request either from the
    headers or from the IP address.
    """
    user = getUtility(ILaunchBag).user
    if user is not None and user.languages:
        return user.languages

    # If the user is not authenticated, or they are authenticated but have no
    # languages set, try looking at the HTTP headers for clues.
    languages = IRequestPreferredLanguages(request).getPreferredLanguages()
    for lang in IRequestLocalLanguages(request).getLocalLanguages():
        if lang not in languages:
            languages.append(lang)
    return languages
