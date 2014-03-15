# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class to handle translation template export view."""

__metaclass__ = type

__all__ = [ 'VPOTExport' ]

from zope.interface import implements

from lp.translations.interfaces.vpotexport import IVPOTExport


class VPOTExport:
    """Present Rosetta POT files in a form suitable for exporting them
    efficiently.
    """
    # XXX JeroenVermeulen 2009-07-30 bug=406540: This should be an
    # ITranslationMessageData.
    implements(IVPOTExport)

    def __init__(self, potemplate, tti, potmsgset, singular, plural):
        self.potemplate = potemplate
        self.sequence = tti.sequence
        self.potmsgset = potmsgset

        if singular:
            self.msgid_singular = singular.msgid
        else:
            self.msgid_singular = None

        if plural:
            self.msgid_plural = plural.msgid
        else:
            self.msgid_plural = None

        self.template_header = self.potemplate.header
        self.context = self.potmsgset.context
        self.comment = self.potmsgset.commenttext
        self.source_comment = self.potmsgset.sourcecomment
        self.file_references = self.potmsgset.filereferences
        self.flags_comment = self.potmsgset.flagscomment
