# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Package relationships."""

__metaclass__ = type
__all__ = [
    'relationship_builder',
    'PackageRelationship',
    'PackageRelationshipSet',
    ]

import operator as std_operator

from zope.interface import implements

from lp.services.webapp import canonical_url
from lp.soyuz.interfaces.packagerelationship import (
    IPackageRelationship,
    IPackageRelationshipSet,
    )


def relationship_builder(relationship_line, parser, getter):
    """Parse relationship_line into a IPackageRelationshipSet.

    'relationship_line' is parsed via given 'parser' funcion
    It also lookup the corresponding URL via the given 'getter'.
    Return empty list if no line is given.
    """
    relationship_set = PackageRelationshipSet()

    if not relationship_line:
        return relationship_set

    parsed_relationships = [
        token[0] for token in parser(relationship_line)]

    for name, version, operator in parsed_relationships:
        target_object = getter(name)
        if target_object is not None:
            url = canonical_url(target_object)
        else:
            url = None
        # The apt_pkg 0.8 API returns '<' and '>' rather than the '<<' and
        # '>>' form used in control files.
        if operator == '<':
            operator = '<<'
        elif operator == '>':
            operator = '>>'
        relationship_set.add(name, operator, version, url)

    return relationship_set


class PackageRelationship:
    """See IPackageRelationship."""

    implements(IPackageRelationship)

    def __init__(self, name, operator, version, url=None):
        self.name = name
        self.version = version
        self.url = url

        if len(operator.strip()) == 0:
            self.operator = None
        else:
            self.operator = operator


class PackageRelationshipSet:
    """See IPackageRelationshipSet."""
    implements(IPackageRelationshipSet)

    def __init__(self):
        self.contents = []

    def add(self, name, operator, version, url):
        """See IPackageRelationshipSet."""
        self.contents.append(
            PackageRelationship(name, operator, version, url))

    def has_items(self):
        """See IPackageRelationshipSet."""
        return len(self.contents) is not 0

    def __iter__(self):
        return iter(sorted(
            self.contents, key=std_operator.attrgetter('name')))
