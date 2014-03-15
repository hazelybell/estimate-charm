# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Remove specific translation messages from the database."""

__metaclass__ = type
__all__ = [
    'process_options',
    'RemoveTranslations',
    'remove_translations',
    ]

import logging
from optparse import (
    Option,
    OptionValueError,
    )

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.services.database.postgresql import drop_tables
from lp.services.database.sqlbase import (
    cursor,
    sqlvalues,
    )
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    )


def process_bool_option(value):
    """Validation and conversion for Boolean argument."""
    value = value.lower()
    bool_representations = {
        'true': True,
        '1': True,
        'false': False,
        '0': False,
        }

    if value not in bool_representations:
        raise OptionValueError("Invalid boolean value: %s" % value)

    return bool_representations[value]


def get_id(identifier, lookup_function=None):
    """Look up id of object identified by a string.

    Raises `OptionValueError` if the option's value appears invalid.

    :param identifier: String identifying an object.  If entirely
        numeric, taken as id.  Otherwise, passed to lookup_function.
    :param lookup_function: Callback that will take `identifier` as
        its argument and return a numeric object id.  If no object
        has the given identifier, may raise a `LookUpError` or return
        None.
    :return: Numeric object id, or None if no identifier is given.
    """
    if identifier is None or identifier == '':
        return None
    elif isinstance(identifier, basestring) and identifier == '':
        return None
    elif isinstance(identifier, int):
        return identifier
    elif identifier.isdigit():
        return int(identifier)
    elif lookup_function is None:
        raise OptionValueError("Expected numeric id, got '%s'." % identifier)
    else:
        try:
            result = lookup_function(identifier)
        except LookupError:
            raise OptionValueError("'%s' not found." % identifier)

    if result is None:
        raise OptionValueError("'%s' not found." % identifier)
    return result


def get_person_id(name):
    """`get_id` helper.  Look up person by name."""
    person = getUtility(IPersonSet).getByName(name)
    if person is None:
        return None
    return person.id


def get_origin(name):
    """`get_id` helper.  Look up `RosettaTranslationOrigin` by name."""
    try:
        return getattr(RosettaTranslationOrigin, name).value
    except AttributeError:
        return None


def process_origin_option(value):
    """Validation and conversion for `RosettaTranslationsOrigin`."""
    return get_id(value, get_origin)


def process_person_option(value):
    """Validation and conversion for `Person`."""
    return get_id(value, get_person_id)


# Options that need special processing.
OPTIONS_TO_PROCESS = {
    'submitter': process_person_option,
    'reviewer': process_person_option,
    'origin': process_origin_option,
    'is_current_ubuntu': process_bool_option,
    'is_current_upstream': process_bool_option,
    }


def process_options(options):
    """Process options that need special processing."""
    for option_name, process_func in OPTIONS_TO_PROCESS.items():
        option_value = getattr(options, option_name)
        if option_value is not None:
            setattr(options, option_name, process_func(option_value))


def is_nonempty_list(list_option):
    """Is list_option a non-empty a nonempty list of option values?"""
    return list_option is not None and len(list_option) > 0


def is_nonempty_string(string_option):
    """Is string_option a non-empty option value?"""
    return string_option is not None and string_option != ''


def compose_language_match(language_code):
    """Compose SQL condition for matching a language in the deletion query.

    :param: Language code to match.
    :return: SQL condition in string form.
    """
    return 'Language.code = %s' % sqlvalues(language_code)


def add_bool_match(conditions, expression, match_value):
    """Add match for tri-state Boolean to SQL conditions.

    :param conditions: Set of SQL condition clauses to add to.
    :param expression: Variable or other SQL expression to match on.
    :param match_value: If given, the Boolean value to match.  If left
        as None, no condition is added.
    """
    if match_value is None:
        return

    if match_value:
        match = expression
    else:
        match = 'NOT (%s)' % expression
    conditions.add(match)


class RemoveTranslations(LaunchpadScript):
    """Remove specific `TranslationMessage`s from the database.

    The script accepts a wide range of options to specify exactly which
    messages need deleting.  It will refuse to run if the options are so
    non-specific that the command is more likely to be a mistake than a
    valid use case.  In borderline cases, it may be persuaded to run
    using a "force" option.
    """

    description = "Delete matching translation messages from the database."
    loglevel = logging.INFO

    my_options = [
        Option(
            '-s', '--submitter', dest='submitter',
            help="Submitter match: delete only messages with this "
                "submitter."),
        Option(
            '-r', '--reviewer', dest='reviewer',
            help="Reviewer match: delete only messages with this reviewer."),
        Option(
            '-x', '--reject-license', action='store_true',
            dest='reject_license',
            help="Match submitters who rejected the licence agreement."),
        Option(
            '-i', '--id', action='append', dest='ids', type='int',
            help="ID of message to delete.  May be specified multiple "
                "times."),
        Option(
            '-p', '--potemplate', dest='potemplate', type='int',
            help="Template id match.  Delete only messages in this "
                "template."),
        Option(
            '-l', '--language', dest='language',
            help="Language match.  Deletes (default) or spares (with -L) "
                 "messages in this language."),
        Option(
            '-L', '--not-language', action='store_true', dest='not_language',
            help="Invert language match: spare messages in given language."),
        Option(
            '-C', '--is-current-ubuntu', dest='is_current_ubuntu',
            help="Match on is_current_ubuntu value (True or False)."),
        Option(
            '-I', '--is-current-upstream', dest='is_current_upstream',
            help="Match on is_current_upstream value (True or False)."),
        Option(
            '-m', '--msgid', dest='msgid',
            help="Match on (singular) msgid text."),
        Option(
            '-o', '--origin', dest='origin',
            help="Origin match: delete only messages with this origin code."),
        Option(
            '-f', '--force', action='store_true', dest='force',
            help="Override safety check on moderately unsafe action."),
        Option(
            '-d', '--dry-run', action='store_true', dest='dry_run',
            help="Go through the motions, but don't really delete."),
        ]

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_options(self.my_options)

    def _check_constraints_safety(self):
        """Are these options to the deletion script sufficiently safe?

        :return: Boolean approval and output message.  All disapprovals come
            with an explanation; some approvals come with an informational
            message.
        """
        if is_nonempty_list(self.options.ids):
            return (True, None)
        if is_nonempty_string(self.options.submitter):
            return (True, None)
        if is_nonempty_string(self.options.reviewer):
            return (True, None)

        forced = self.options.force

        if is_nonempty_string(self.options.potemplate) and forced:
            return (
                True,
                "Safety override in effect.  Deleting translations for "
                "template %s." % self.options.potemplate)

        if self.options.reject_license:
            if self.options.is_current_upstream == False:
                # "Remove non-is_current_upstream messages submitted by users
                # who rejected the licence."
                return (True, None)

            rosettaweb_key = RosettaTranslationOrigin.ROSETTAWEB.value
            if self.options.origin == rosettaweb_key:
                # "Remove messages submitted directly in Launchpad by
                # users who rejected the licence."
                return (True, None)

            if forced:
                return (
                    True,
                    "Safety override in effect.  Removing translations "
                    "by users who rejected the licence, regardless of "
                    "origin.")

            return (
                False,
                "To delete the translations by users who "
                "rejected the translations licence, specify at least "
                "--origin=ROSETTAWEB or --is-imported=False.")

        return (
            False,
            "Refusing unsafe deletion.  Use matching options to constrain "
            "deletion to a safe subset.")

    def main(self):
        """See `LaunchpadScript`."""
        process_options(self.options)
        (result, message) = self._check_constraints_safety()
        if not result:
            raise LaunchpadScriptFailure(message)
        if message is not None:
            self.logger.warn(message)

        if self.options.dry_run:
            self.logger.info("Dry run only.  Not really deleting.")

        remove_translations(logger=self.logger,
            submitter=self.options.submitter,
            reject_license=self.options.reject_license,
            reviewer=self.options.reviewer,
            ids=self.options.ids,
            potemplate=self.options.potemplate,
            language_code=self.options.language,
            not_language=self.options.not_language,
            is_current_ubuntu=self.options.is_current_ubuntu,
            is_current_upstream=self.options.is_current_upstream,
            msgid_singular=self.options.msgid,
            origin=self.options.origin)

        if self.options.dry_run:
            if self.txn is not None:
                self.txn.abort()
        else:
            self.txn.commit()


def warn_about_deleting_current_messages(cur, from_text, where_text, logger):
    # Deleting currently used translations is a bit harmful. Log
    # them so that we have a clue which messages might have to be
    # translated again. Note that this script tries to find
    # another translation that becomes current -- but only in one
    # situation: If we delete a shared translation which is current
    # in Ubuntu, a shared translation which is current in upstream
    # becomes the current Ubuntu translation. In other cases (deleting
    # a diverged translation, deleting a shared translation which
    # is current upstream) we do not attempt to find another current
    # message.
    if logger is not None and logger.getEffectiveLevel() <= logging.WARN:
        query = """
            SELECT
                TranslationMessage.id, TranslationMessage.is_current_upstream,
                TranslationMessage.is_current_ubuntu
            FROM %s
            WHERE %s AND (
                TranslationMessage.is_current_upstream OR
                TranslationMessage.is_current_ubuntu)
            """ % (from_text, where_text)
        cur.execute(query)
        rows = cur.fetchall()
        if cur.rowcount > 0:
            logger.warn(
                'Deleting messages currently in use:')
            for (id, is_current_upstream, is_current_ubuntu) in rows:
                current = []
                if is_current_upstream:
                    current.append('upstream')
                if is_current_ubuntu:
                    current.append('Ubuntu')
                logger.warn(
                    'Message %i is a current translation in %s'
                    % (id, ' and '.join(current)))


def remove_translations(logger=None, submitter=None, reviewer=None,
                        reject_license=False, ids=None, potemplate=None,
                        language_code=None, not_language=False,
                        is_current_ubuntu=None, is_current_upstream=None,
                        msgid_singular=None, origin=None):
    """Remove specified translation messages.

    :param logger: Optional logger to write output to.
    :param submitter: Delete only messages submitted by this person.
    :param reviewer: Delete only messages reviewed by this person.
    :param reject_license: Delete only messages submitted by persons who
        have rejected the licensing agreement.
    :param ids: Delete only messages with these `TranslationMessage` ids.
    :param potemplate: Delete only messages in this template.
    :param language_code: Language code.  Depending on `not_language`,
        either delete messages in this language or spare messages in this
        language that would otherwise be deleted.
    :param not_language: Whether to spare (True) or delete (False)
        messages in this language.
    :param is_current_ubuntu: Delete only messages with this is_current_ubuntu
        value.
    :param is_current_upstream: Delete only messages with this
        is_current_upstream value.
    :param msgid_singular: Delete only messages with this singular msgid.
    :param origin: Delete only messages with this `TranslationOrigin` code.

    :return: Number of messages deleted.
    """
    joins = set()
    conditions = set()
    if submitter is not None:
        conditions.add(
            'TranslationMessage.submitter = %s' % sqlvalues(submitter))
    if reviewer is not None:
        conditions.add(
            'TranslationMessage.reviewer = %s' % sqlvalues(reviewer))
    if reject_license:
        joins.add('TranslationRelicensingAgreement')
        conditions.add(
            'TranslationMessage.submitter = '
            'TranslationRelicensingAgreement.person')
        conditions.add(
            'NOT TranslationRelicensingAgreement.allow_relicensing')
    if ids is not None:
        conditions.add('TranslationMessage.id IN %s' % sqlvalues(ids))
    if potemplate is not None:
        joins.add('TranslationTemplateItem')
        conditions.add(
            'TranslationTemplateItem.potmsgset '
            ' = TranslationMessage.potmsgset')
        conditions.add(
            'TranslationTemplateItem.potemplate = %s' % sqlvalues(potemplate))

    if language_code is not None:
        joins.add('Language')
        conditions.add('Language.id = TranslationMessage.language')
        language_match = compose_language_match(language_code)
        if not_language:
            conditions.add('NOT (%s)' % language_match)
        else:
            conditions.add(language_match)

    add_bool_match(
        conditions, 'TranslationMessage.is_current_ubuntu', is_current_ubuntu)
    add_bool_match(
        conditions, 'TranslationMessage.is_current_upstream',
        is_current_upstream)

    if msgid_singular is not None:
        joins.add('POTMsgSet')
        conditions.add('POTMsgSet.id = TranslationMessage.potmsgset')
        joins.add('POMsgID')
        conditions.add('POMsgID.id = POTMsgSet.msgid_singular')
        conditions.add('POMsgID.msgid = %s' % sqlvalues(msgid_singular))

    if origin is not None:
        conditions.add('TranslationMessage.origin = %s' % sqlvalues(origin))

    assert len(conditions) > 0, "That would delete ALL translations, maniac!"

    cur = cursor()
    drop_tables(cur, 'temp_doomed_message')

    joins.add('TranslationMessage')
    from_text = ', '.join(joins)
    where_text = ' AND\n    '.join(conditions)

    warn_about_deleting_current_messages(cur, from_text, where_text, logger)

    # Keep track of messages we're going to delete.
    # Don't bother indexing this.  We'd more likely end up optimizing
    # away the operator's "oh-shit-ctrl-c" time than helping anyone.
    query = """
        CREATE TEMP TABLE temp_doomed_message AS
        SELECT TranslationMessage.id, NULL::integer AS imported_message
        FROM %s
        WHERE %s
        """ % (from_text, where_text)
    cur.execute(query)

    # Note which shared messages are masked by the messages we're
    # going to delete.  We'll be making those the current ones.
    query = """
         UPDATE temp_doomed_message
        SET imported_message = Imported.id
        FROM TranslationMessage Doomed, TranslationMessage Imported
        WHERE
            Doomed.id = temp_doomed_message.id AND
            -- Is alternative for the message we're about to delete.
            Imported.potmsgset = Doomed.potmsgset AND
            Imported.language = Doomed.language AND
            Imported.potemplate IS NULL AND
            Doomed.potemplate IS NULL AND
            -- Is used upstream.
            Imported.is_current_upstream IS TRUE AND
            -- Was masked by the message we're about to delete.
            Doomed.is_current_ubuntu IS TRUE AND
            Imported.id <> Doomed.id
            """
    cur.execute(query)

    if logger is not None and logger.getEffectiveLevel() <= logging.DEBUG:
        # Dump sample of doomed messages for debugging purposes.
        cur.execute("""
            SELECT *
            FROM temp_doomed_message
            ORDER BY id
            LIMIT 20
            """)
        rows = cur.fetchall()
        if cur.rowcount > 0:
            logger.debug("Sample of messages to be deleted follows.")
            logger.debug("%10s %10s" % ("[message]", "[unmasks]"))
            for (doomed, unmasked) in rows:
                if unmasked is None:
                    unmasked = '--'
                logger.debug("%10s %10s" % (doomed, unmasked))

    cur.execute("""
        DELETE FROM TranslationMessage
        USING temp_doomed_message
        WHERE TranslationMessage.id = temp_doomed_message.id
        """)

    rows_deleted = cur.rowcount
    if logger is not None:
        if rows_deleted > 0:
            logger.info("Deleting %d message(s)." % rows_deleted)
        else:
            logger.warn("No rows match; not deleting anything.")

    cur.execute("""
        UPDATE TranslationMessage
        SET is_current_ubuntu = TRUE
        FROM temp_doomed_message
        WHERE TranslationMessage.id = temp_doomed_message.imported_message
        """)

    if cur.rowcount > 0 and logger is not None:
        logger.debug("Unmasking %d imported message(s)." % cur.rowcount)

    drop_tables(cur, 'temp_doomed_message')

    return rows_deleted
