# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'summarize_current_translations',
    'make_translationmessage',
    'make_translationmessage_for_context',
    ]

from storm.expr import Or
from storm.store import Store
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.translations.interfaces.side import ITranslationSideTraitsSet
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    TranslationValidationStatus,
    )
from lp.translations.model.translationmessage import TranslationMessage


def make_translationmessage_for_context(factory, pofile, potmsgset=None,
                                        current=True, other=False,
                                        diverged=False, translations=None):
    """A low-level way of constructing TMs appropriate to `pofile` context."""
    assert pofile is not None, "You must pass in an existing POFile."

    potemplate = pofile.potemplate
    if potemplate.distroseries is not None:
        ubuntu, upstream = current, other
    else:
        ubuntu, upstream = other, current
    return make_translationmessage(
        factory, pofile, potmsgset, ubuntu, upstream, diverged, translations)


def make_translationmessage(factory, pofile=None, potmsgset=None,
                            ubuntu=True, upstream=True,
                            diverged=False, translations=None):
    """Creates a TranslationMessage directly and sets relevant parameters.

    This is very low level function used to test core Rosetta
    functionality such as setCurrentTranslation() method.  If not used
    correctly, it will trigger unique constraints.
    """
    if pofile is None:
        pofile = factory.makePOFile('sr')
    if potmsgset is None:
        potmsgset = factory.makePOTMsgSet(
            potemplate=pofile.potemplate)
    if translations is None:
        translations = [factory.getUniqueString()]
    if diverged:
        potemplate = pofile.potemplate
    else:
        potemplate = None

    # Parameters we don't care about are origin, submitter and
    # validation_status.
    origin = RosettaTranslationOrigin.SCM
    submitter = pofile.owner
    validation_status = TranslationValidationStatus.UNKNOWN

    translations = dict(enumerate(translations))

    potranslations = removeSecurityProxy(
        potmsgset)._findPOTranslations(translations)
    new_message = TranslationMessage(
        potmsgset=potmsgset,
        potemplate=potemplate,
        pofile=None,
        language=pofile.language,
        origin=origin,
        submitter=submitter,
        msgstr0=potranslations[0],
        msgstr1=potranslations[1],
        msgstr2=potranslations[2],
        msgstr3=potranslations[3],
        msgstr4=potranslations[4],
        msgstr5=potranslations[5],
        validation_status=validation_status,
        is_current_ubuntu=ubuntu,
        is_current_upstream=upstream)
    return new_message


def get_all_translations_diverged_anywhere(pofile, potmsgset):
    """Get diverged `TranslationMessage`s for this `POTMsgSet` and language.

    Leave out translations diverged to pofile.potemplate.
    """
    result = Store.of(potmsgset).find(
        TranslationMessage,
        TranslationMessage.potmsgset == potmsgset,
        Or(
            TranslationMessage.is_current_ubuntu == True,
            TranslationMessage.is_current_upstream == True),
        TranslationMessage.potemplate != None,
        TranslationMessage.potemplate != pofile.potemplate,
        TranslationMessage.language == pofile.language)
    return result.order_by(-TranslationMessage.potemplateID)


def summarize_current_translations(pofile, potmsgset):
    """Return all existing current translations for `POTMsgSet`.

    Returns a tuple containing 4 elements:
     * current, shared translation for `potmsgset`.
     * diverged translation for `potmsgset` in `pofile`, or None.
     * shared translation for `potmsgset` in "other" context.
     * list of all other diverged translations (not including the one
       diverged in `pofile`) or an empty list if there are none.
    """
    template = pofile.potemplate
    language = pofile.language
    side = template.translation_side

    current_shared = potmsgset.getCurrentTranslation(None, language, side)
    current_diverged = potmsgset.getCurrentTranslation(
        template, language, side)
    if current_diverged is not None and not current_diverged.is_diverged:
        current_diverged = None

    traits = getUtility(ITranslationSideTraitsSet).getTraits(side)
    other_side = traits.other_side_traits.side

    other_shared = potmsgset.getCurrentTranslation(None, language, other_side)
    other_diverged = potmsgset.getCurrentTranslation(
        template, language, other_side)
    assert other_diverged is None or other_diverged.potemplate is None, (
        "There is a diverged 'other' translation for "
        "this same template, which should be impossible.")

    diverged = list(get_all_translations_diverged_anywhere(pofile, potmsgset))
    return (
        current_shared, current_diverged,
        other_shared, diverged)
