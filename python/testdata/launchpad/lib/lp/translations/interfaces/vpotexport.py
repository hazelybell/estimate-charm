# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for efficient POT file exports."""

__metaclass__ = type

__all__ = ['IVPOTExport']

from zope.interface import Interface
from zope.schema import (
    Int,
    Object,
    Text,
    )

from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.potmsgset import IPOTMsgSet


class IVPOTExport(Interface):
    """Database view for efficient POT exports."""

    potemplate = Object(
        title=u"See IPOTemplate",
        required=True, readonly=True, schema=IPOTemplate)

    template_header = Text(
        title=u"See IPOTemplate.header",
        required=True, readonly=True)

    potmsgset = Object(
        title=u"See `IPOTMsgSet`.",
        required=True, readonly=True, schema=IPOTMsgSet)

    sequence = Int(
        title=u"See `IPOTMsgSet`.sequence",
        required=False, readonly=True)

    comment = Text(
        title=u"See `IPOTMsgSet`.commenttext",
        required=False, readonly=True)

    source_comment = Text(
        title=u"See `IPOTMsgSet`.sourcecomment",
        required=False, readonly=True)

    file_references = Text(
        title=u"See `IPOTMsgSet.filereferences`",
        required=False, readonly=True)

    flags_comment = Text(
        title=u"See `IPOTMsgSet`.flagscomment",
        required=False, readonly=True)

    context = Text(
        title=u"See `IPOTMsgSet`.context",
        required=False, readonly=True)

    msgid_singular = Text(
        title=u"See `IPOMsgID`.pomsgid",
        required=True, readonly=True)

    msgid_plural = Text(
        title=u"See `IPOMsgID`.pomsgid",
        required=False, readonly=True)
