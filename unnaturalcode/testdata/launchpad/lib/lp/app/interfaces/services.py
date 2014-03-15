# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces used for named services."""


__metaclass__ = type

__all__ = [
    'IService',
    'IServiceFactory',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from zope.interface import Interface
from zope.schema import TextLine

from lp import _


class IService(Interface):
    """Base interface for services."""

    name = exported(
        TextLine(
            title=_('Name'),
            description=_(
                'The name of the service, used to generate the url.')))


class IServiceFactory(Interface):
    """Interface representing a factory used to access named services."""

    export_as_webservice_entry(publish_web_link=False, as_of='beta')
