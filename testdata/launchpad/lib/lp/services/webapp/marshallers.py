# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


__metaclass__ = type
__all__ = [
    'choiceMarshallerError'
    ]


def choiceMarshallerError(field, request, vocabulary=None):
    # We don't support marshalling a normal Choice field with a
    # SQLObjectVocabularyBase-based vocabulary.
    # Normally for this kind of use case, one returns None and
    # lets the Zope machinery alert the user that the lookup has gone wrong.
    # However, we want to be more helpful, so we make an assertion,
    # with a comment on how to make things better.
    raise AssertionError("You exported %s as an IChoice based on an "
                         "SQLObjectVocabularyBase, you should use "
                         "lazr.restful.fields.ReferenceChoice instead."
                         % field.__name__)
