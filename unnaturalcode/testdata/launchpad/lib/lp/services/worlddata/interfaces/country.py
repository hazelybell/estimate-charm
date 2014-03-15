# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Country interfaces."""

__metaclass__ = type

__all__ = [
    'ICountry',
    'ICountrySet',
    'IContinent'
    ]

from lazr.restful.declarations import (
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_parameters,
    operation_returns_entry,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Int,
    TextLine,
    )

from lp import _
from lp.app.validators.name import valid_name
from lp.services.fields import (
    Description,
    Title,
    )


class ICountry(Interface):
    """The country description."""
    export_as_webservice_entry(
        plural_name='countries', publish_web_link=False)

    id = Int(
        title=_('Country ID'), required=True, readonly=True,
        )
    iso3166code2 = exported(
        TextLine(title=_('iso3166code2'), required=True,
            readonly=True))
    iso3166code3 = exported(
        TextLine(title=_('iso3166code3'), required=True,
            readonly=True))
    name = exported(
        TextLine(
            title=_('Country name'), required=True,
            constraint=valid_name))
    title = exported(
        Title(
            title=_('Country title'), required=True))
    description = exported(
        Description(
            title=_('Description'), required=True))

    continent = Attribute("The Continent where this country is located.")
    languages = Attribute("An iterator over languages that are spoken in "
                          "that country.")


class ICountrySet(Interface):
    """A container for countries."""
    export_as_webservice_collection(ICountry)

    def __getitem__(key):
        """Get a country."""

    def __iter__():
        """Iterate through the countries in this set."""

    @operation_parameters(
        name=TextLine(title=_("Name"), required=True))
    @operation_returns_entry(ICountry)
    @export_read_operation()
    def getByName(name):
        """Return a country by its name."""

    @operation_parameters(
        code=TextLine(title=_("Code"), required=True))
    @operation_returns_entry(ICountry)
    @export_read_operation()
    def getByCode(code):
        """Return a country by its code."""

    @collection_default_content()
    def getCountries():
        """Return a collection of countries."""


class IContinent(Interface):
    """See IContinent."""

    id = Int(title=_('ID'), required=True, readonly=True)
    code = TextLine(title=_("Continent's code"), required=True, readonly=True)
    name = TextLine(title=_("Continent's name"), required=True, readonly=True)

