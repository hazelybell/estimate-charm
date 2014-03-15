# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


__all__ = [
    'json_dump_information_types',
    ]


from lp.app.enums import (
    InformationType,
    PRIVATE_INFORMATION_TYPES,
    )


def json_dump_information_types(cache, information_types):
    """Dump a dict of the data in the types requested."""
    dump = {}
    order = list(InformationType.sort_order)
    for term in information_types:
        dump[term.name] = {
            'value': term.name,
            'description': term.description,
            'name': term.title,
            'order': order.index(term.name),
            'is_private': (term in PRIVATE_INFORMATION_TYPES),
            'description_css_class': 'choice-description',
        }

    cache.objects['information_type_data'] = dump
