# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface definitions for IHasRecipes."""

__metaclass__ = type
__all__ = [
    'IHasRecipes',
    ]


from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import exported
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import Interface

from lp import _


class IHasRecipes(Interface):
    """An object that has recipes."""

    recipes = exported(doNotSnapshot(
        CollectionField(
            title=_("All recipes associated with the object."),
            value_type=Reference(schema=Interface),
            readonly=True)))
