# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    Object,
    Text,
    )

from lp import _
from lp.registry.interfaces.person import IPerson


__metaclass__ = type
__all__ = [
    'ITranslationRelicensingAgreement',
    'ITranslationRelicensingAgreementEdit',
    'TranslationRelicensingAgreementOptions'
    ]


class ITranslationRelicensingAgreement(Interface):
    """An agreement to relicensing a person's translations."""

    id = Int(
        title=_("The ID for this relicensing answer"),
        readonly=True, required=True)

    person = Object(
        title=_("The person who responded to the relicensing question"),
        readonly=False, required=True, schema=IPerson)

    allow_relicensing = Bool(
        title=_("Whether the person agreed to the BSD licence"),
        readonly=False, default=True, required=True)

    date_decided = Datetime(
        title=_("The date person made her decision"),
        readonly=True, required=True)


class TranslationRelicensingAgreementOptions(EnumeratedType):
    BSD = Item("License all my translations in Launchpad "
               "under the BSD licence")
    REMOVE = Item("Not make translations in Launchpad")


class ITranslationRelicensingAgreementEdit(ITranslationRelicensingAgreement):
    """Extend ITranslationRelicensingAgreement with `back_to` field."""

    back_to = Text(
        title=_("URL to go back to after question is shown"),
        readonly=False, required=False)

    allow_relicensing = Choice(
        title=_("I would rather"),
        vocabulary=TranslationRelicensingAgreementOptions,
        required=True)
