# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""A parser for FileBug data BLOBs"""

__metaclass__ = type
__all__ = [
    'FileBugData',
    'FileBugDataParser',
    ]

from email import message_from_string
import tempfile

from lp.bugs.model.bug import FileBugData


class FileBugDataParser:
    """Parser for a message containing extra bug information.

    Applications like Apport upload such messages, before filing the
    bug.
    """

    def __init__(self, blob_file):
        self.blob_file = blob_file
        self.headers = {}
        self._buffer = ''
        self.extra_description = None
        self.comments = []
        self.attachments = []
        self.BUFFER_SIZE = 8192

    def _consumeBytes(self, end_string):
        """Read bytes from the message up to the end_string.

        The end_string is included in the output.

        If end-of-file is reached, '' is returned.
        """
        while end_string not in self._buffer:
            data = self.blob_file.read(self.BUFFER_SIZE)
            self._buffer += data
            if len(data) < self.BUFFER_SIZE:
                # End of file.
                if end_string not in self._buffer:
                    # If the end string isn't present, we return
                    # everything.
                    buffer = self._buffer
                    self._buffer = ''
                    return buffer
                break
        end_index = self._buffer.index(end_string)
        bytes = self._buffer[:end_index+len(end_string)]
        self._buffer = self._buffer[end_index+len(end_string):]
        return bytes

    def readHeaders(self):
        """Read the next set of headers of the message."""
        header_text = self._consumeBytes('\n\n')
        # Use the email package to return a dict-like object of the
        # headers, so we don't have to parse the text ourselves.
        return message_from_string(header_text)

    def readLine(self):
        """Read a line of the message."""
        data = self._consumeBytes('\n')
        if data == '':
            raise AssertionError('End of file reached.')
        return data

    def _setDataFromHeaders(self, data, headers):
        """Set the data attributes from the message headers."""
        if 'Subject' in headers:
            data.initial_summary = unicode(headers['Subject'])
        if 'Tags' in headers:
            tags_string = unicode(headers['Tags'])
            data.initial_tags = tags_string.lower().split()
        if 'Private' in headers:
            private = headers['Private']
            if private.lower() == 'yes':
                data.private = True
            elif private.lower() == 'no':
                data.private = False
            else:
                # If the value is anything other than yes or no we just
                # ignore it as we cannot currently give the user an error
                pass
        if 'Subscribers' in headers:
            subscribers_string = unicode(headers['Subscribers'])
            data.subscribers = subscribers_string.lower().split()
        if 'HWDB-Submission' in headers:
            submission_string = unicode(headers['HWDB-Submission'])
            data.hwdb_submission_keys = sorted(
                part.strip() for part in submission_string.split(','))

    def parse(self):
        """Parse the message and  return a FileBugData instance.

            * The Subject header is the initial bug summary.
            * The Tags header specifies the initial bug tags.
            * The Private header sets the visibility of the bug.
            * The Subscribers header specifies additional initial subscribers
            * The first inline part will be added to the description.
            * All other inline parts will be added as separate comments.
            * All attachment parts will be added as attachment.

        When parsing each part of the message is stored in a temporary
        file on the file system. After using the returned data,
        removeTemporaryFiles() must be called.
        """
        headers = self.readHeaders()
        data = FileBugData()
        self._setDataFromHeaders(data, headers)

        # The headers is a Message instance.
        boundary = "--" + headers.get_param("boundary")
        line = self.readLine()
        while not line.startswith(boundary + '--'):
            part_file = tempfile.TemporaryFile()
            part_headers = self.readHeaders()
            content_encoding = part_headers.get('Content-Transfer-Encoding')
            if content_encoding is not None and content_encoding != 'base64':
                raise AssertionError(
                    "Unknown encoding: %r." % content_encoding)
            line = self.readLine()
            while not line.startswith(boundary):
                # Decode the file.
                if content_encoding is not None:
                    line = line.decode(content_encoding)
                part_file.write(line)
                line = self.readLine()
            # Prepare the file for reading.
            part_file.seek(0)
            disposition = part_headers['Content-Disposition']
            disposition = disposition.split(';')[0]
            disposition = disposition.strip()
            if disposition == 'inline':
                assert part_headers.get_content_type() == 'text/plain', (
                    "Inline parts have to be plain text.")
                charset = part_headers.get_content_charset()
                assert charset, (
                    "A charset has to be specified for text parts.")
                inline_content = part_file.read().rstrip()
                part_file.close()
                inline_content = inline_content.decode(charset)

                if data.extra_description is None:
                    # The first inline part is extra description.
                    data.extra_description = inline_content
                else:
                    data.comments.append(inline_content)
            elif disposition == 'attachment':
                attachment = dict(
                    filename=unicode(part_headers.get_filename().strip("'")),
                    content_type=unicode(part_headers['Content-type']),
                    content=part_file)
                if 'Content-Description' in part_headers:
                    attachment['description'] = unicode(
                        part_headers['Content-Description'])
                else:
                    attachment['description'] = attachment['filename']
                data.attachments.append(attachment)
            else:
                # If the message include other disposition types,
                # simply ignore them. We don't want to break just
                # because some extra information is included.
                continue
        return data
