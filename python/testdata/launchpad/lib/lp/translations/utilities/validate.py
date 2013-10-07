# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'GettextValidationError',
    'validate_translation',
    ]

import gettextpo


class GettextValidationError(ValueError):
    """Gettext validation failed."""


def validate_translation(original_singular, original_plural,
                         translations, flags):
    """Check with gettext if a translation is correct or not.

    If the translation has a problem, raise `GettextValidationError`.

    :param original_singular: The English msgid.
    :param original_plural: The English plural msgid, if the message has a
        plural or None otherwise.
    :param translations: A dictionary of translations, indexed with the plural
        form number.
    :param flags: This message's flags as a list of strings.
    """
    msg = gettextpo.PoMessage()
    msg.set_msgid(original_singular)

    if original_plural is None:
        # Basic, single-form message.
        msg.set_msgstr(translations.get(0))
    else:
        # Message with plural forms.
        msg.set_msgid_plural(original_plural)
        for form, translation in translations.iteritems():
            msg.set_msgstr_plural(form, translation)

    for flag in flags:
        msg.set_format(flag, True)

    # Check the msg.
    try:
        msg.check_format()
    except gettextpo.error as e:
        # Wrap gettextpo.error in GettextValidationError.
        raise GettextValidationError(unicode(e))
