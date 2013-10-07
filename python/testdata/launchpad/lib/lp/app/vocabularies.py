# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Vocabularies for content objects.

Vocabularies that represent a set of content objects should be in this module.
Those vocabularies that are only used for providing a UI are better placed in
the browser code.

Note that you probably shouldn't be importing stuff from these modules, as it
is better to have your schema's fields look up the vocabularies by name. Some
of these vocabularies will only work if looked up by name, as they require
context to calculate the available options. Obtaining a vocabulary by name
also avoids circular import issues.

eg.

class IFoo(Interface):
    thingy = Choice(..., vocabulary='Thingies')

The binding of name -> class is done in the configure.zcml
"""

__metaclass__ = type

__all__ = [
    'InformationTypeVocabulary',
    ]


from lazr.enum import IEnumeratedType
from zope.interface import implements
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )


class InformationTypeVocabulary(SimpleVocabulary):

    implements(IEnumeratedType)

    def __init__(self, types):
        terms = []
        for type in types:
            term = SimpleTerm(type, type.name, type.title)
            term.name = type.name
            term.description = type.description
            terms.append(term)
        super(InformationTypeVocabulary, self).__init__(terms)
