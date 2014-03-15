# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'EditEmailCommand',
    'EmailCommand',
    'EmailCommandCollection',
    'normalize_arguments',
    'NoSuchCommand',
    ]

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.interfaces import (
    IObjectCreatedEvent,
    IObjectModifiedEvent,
    )
from lazr.lifecycle.snapshot import Snapshot
from zope.interface import providedBy

from lp.services.mail.helpers import get_error_message
from lp.services.mail.interfaces import EmailProcessingError


def normalize_arguments(string_args):
    """Normalizes the string arguments.

    The string_args argument is simply the argument string whitespace
    splitted. Sometimes arguments may be quoted, though, so that they can
    contain space characters. For example "This is a long string".

    This function loops through all the argument and joins the quoted strings
    into a single arguments.

        >>> normalize_arguments(['"This', 'is', 'a', 'long', 'string."'])
        ['This is a long string.']

        >>> normalize_arguments(
        ...     ['"First', 'string"', '"Second', 'string"', 'foo'])
        ['First string', 'Second string', 'foo']
    """
    result = []
    quoted_string = False
    for item in string_args:
        if item.startswith('"'):
            quoted_string = True
            result.append(item[1:])
        elif quoted_string and item.endswith('"'):
            result[-1] += ' ' + item[:-1]
            quoted_string = False
        elif quoted_string:
            result[-1] += ' ' + item
        else:
            result.append(item)

    return result


class EmailCommand:
    """Represents a command.

    Both name the values in the args list are strings.
    """
    _numberOfArguments = None

    # Should command arguments be converted to lowercase?
    case_insensitive_args = True

    def __init__(self, name, string_args):
        self.name = name
        self.string_args = normalize_arguments(string_args)

    def _ensureNumberOfArguments(self):
        """Check that the number of arguments is correct.

        Raise an EmailProcessingError
        """
        if self._numberOfArguments is not None:
            num_arguments_got = len(self.string_args)
            if self._numberOfArguments != num_arguments_got:
                raise EmailProcessingError(
                    get_error_message(
                        'num-arguments-mismatch.txt',
                        command_name=self.name,
                        num_arguments_expected=self._numberOfArguments,
                        num_arguments_got=num_arguments_got))

    def convertArguments(self, context):
        """Converts the string argument to Python objects.

        Returns a dict with names as keys, and the Python objects as
        values.
        """
        raise NotImplementedError

    def __str__(self):
        """See IEmailCommand."""
        return ' '.join([self.name] + self.string_args)


class EditEmailCommand(EmailCommand):
    """Helper class for commands that edits the context.

    It makes sure that the correct events are notified.
    """

    def execute(self, context, current_event):
        """See IEmailCommand."""
        self._ensureNumberOfArguments()
        args = self.convertArguments(context)

        edited_fields = set()
        if IObjectModifiedEvent.providedBy(current_event):
            context_snapshot = current_event.object_before_modification
            edited_fields.update(current_event.edited_fields)
        else:
            context_snapshot = Snapshot(
                context, providing=providedBy(context))

        edited = False
        for attr_name, attr_value in args.items():
            if getattr(context, attr_name) != attr_value:
                self.setAttributeValue(context, attr_name, attr_value)
                edited = True
        if edited and not IObjectCreatedEvent.providedBy(current_event):
            edited_fields.update(args.keys())
            current_event = ObjectModifiedEvent(
                context, context_snapshot, list(edited_fields))

        return context, current_event

    def setAttributeValue(self, context, attr_name, attr_value):
        """See IEmailCommand."""
        setattr(context, attr_name, attr_value)


class NoSuchCommand(KeyError):
    """A command with the given name couldn't be found."""


class EmailCommandCollection:
    """A collection of email commands."""

    @classmethod
    def parsingParameters(klass):
        """Returns all the command names."""
        return dict(
            (command_name, command.case_insensitive_args)
            for command_name, command in klass._commands.items())

    @classmethod
    def get(klass, name, string_args):
        """Returns a command object with the given name and arguments.

        If a command with the given name can't be found, a NoSuchCommand
        error is raised.
        """
        command_class = klass._commands.get(name)
        if command_class is None:
            raise NoSuchCommand(name)
        return command_class(name, string_args)
