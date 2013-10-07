# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Featured project interfaces."""

__metaclass__ = type

__all__ = [
    'IFeaturedProject',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class IFeaturedProject(Interface):
    """A featured project name."""

    id = Attribute("The unique ID of this featured project.")
    pillar_name = Attribute("The pillar name of the featured project.")

    def destroySelf():
        """Remove this project from the featured project list."""

