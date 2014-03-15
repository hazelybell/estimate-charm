# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from zope.interface import Interface
from zope.schema import (
    Int,
    Object,
    )

from lp import _
from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.potmsgset import IPOTMsgSet


__metaclass__ = type
__all__ = [
    'ITranslationTemplateItem',
    ]


class ITranslationTemplateItem(Interface):
    """A translatable message in a translation template file."""

    id = Int(
        title=_("The ID for this translation message"),
        readonly=True, required=True)

    potemplate = Object(
        title=_("The template this translation is in"),
        readonly=False, required=False, schema=IPOTemplate)

    sequence = Int(
        title=_("The ordering of this set within its file"),
        readonly=False, required=True)

    potmsgset = Object(
        title=_("The template message that this translation is for"),
        readonly=False, required=True, schema=IPOTMsgSet)
