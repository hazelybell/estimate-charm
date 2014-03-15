# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Section interfaces."""

__metaclass__ = type

__all__ = [
    'ISection',
    'ISectionSelection',
    'ISectionSet',
    ]


from zope.interface import (
    Attribute,
    Interface,
    )


class ISection(Interface):
    """Represents the Section table.

    A distribution section represents a tag that groups related
    packages. Examples in Ubuntu include 'editors', 'x11' and 'net'.
    """

    id = Attribute("The section ID")
    name = Attribute("The section name")


class ISectionSelection(Interface):
    """Represents the allowed section within a DistroSeries."""
    id = Attribute("The ID")
    distroseries = Attribute("Target DistroSeries")
    section = Attribute("Selected Section")


class ISectionSet(Interface):
    """Represents a set of Sections."""

    def __iter__():
        """Iterate over section."""

    def __getitem__(name):
        """Retrieve a section by name"""

    def get(section_id):
        """Return the ISection with the given section_id."""

    def ensure(name):
        """Ensure the existence of a section with a given name."""

    def new(name):
        """Create a new section."""

