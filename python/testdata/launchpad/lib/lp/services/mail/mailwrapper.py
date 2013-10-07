# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The MailWrapper class."""

__metaclass__ = type
__all__ = [
    'MailWrapper',
    ]


import textwrap


class MailWrapper:
    """Wraps text that should be included in an email.

        :width: how long should the lines be
        :indent: specifies how much indentation the lines should have
        :indent_first_line: indicates whether the first line should be
                            indented or not.

    Note that MailWrapper doesn't guarantee that all lines will be less
    than :width:, sometimes it's better not to break long lines in
    emails. See textformatting.txt for more information.
    """

    def __init__(self, width=72, indent='', indent_first_line=True):
        self.indent = indent
        self.indent_first_line = indent_first_line
        self._text_wrapper = textwrap.TextWrapper(
            width=width, subsequent_indent=indent,
            replace_whitespace=False, break_long_words=False)

    def format(self, text, force_wrap=False, wrap_func=None):
        """Format the text to be included in an email.

        :param force_wrap: When False (the default), only paragraphs
            containing a single line will be wrapped.  Otherwise paragraphs in
            text will be re-wrapped.
        :type force_wrap: bool
        :param wrap_func: A function to call at the beginning of each
            paragraph to be wrapped.  If the function returns False, the
            paragraph is not wrapped.
        :type wrap_func: callable or None
        """
        wrapped_lines = []

        if self.indent_first_line:
            indentation = self.indent
        else:
            indentation = ''

        # We don't care about trailing whitespace.
        text = text.rstrip()

        # Normalize dos-style line endings to unix-style.
        text = text.replace('\r\n', '\n')

        for paragraph in text.split('\n\n'):
            lines = paragraph.split('\n')

            if wrap_func is not None and not wrap_func(paragraph):
                # The user's callback function has indicated that the
                # paragraph should not be wrapped.
                wrapped_lines += (
                    [indentation + lines[0]] +
                    [self.indent + line for line in lines[1:]])
            elif len(lines) == 1:
                # We use TextWrapper only if the paragraph consists of a
                # single line, like in the case where a person enters a
                # comment via the web ui, without breaking the lines
                # manually.
                self._text_wrapper.initial_indent = indentation
                wrapped_lines += self._text_wrapper.wrap(paragraph)
            elif force_wrap:
                self._text_wrapper.initial_indent = indentation
                for line in lines:
                    wrapped_lines += self._text_wrapper.wrap(line)
            else:
                # If the user has gone through the trouble of wrapping
                # the lines, we shouldn't re-wrap them for him.
                wrapped_lines += (
                    [indentation + lines[0]] +
                    [self.indent + line for line in lines[1:]])

            if not self.indent_first_line:
                # 'indentation' was temporarily set to '' in order to
                # prevent the first line from being indented. Set it
                # back to self.indent so that the rest of the lines get
                # indented.
                indentation = self.indent

            # Add an empty line so that the paragraphs get separated by
            # a blank line when they are joined together again.
            wrapped_lines.append('')

        # We added one line too much, remove it.
        wrapped_lines = wrapped_lines[:-1]
        return '\n'.join(wrapped_lines)
