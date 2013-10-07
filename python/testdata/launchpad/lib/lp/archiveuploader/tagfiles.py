# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utility classes for parsing Debian tag files."""

__all__ = [
    'TagFileParseError',
    'parse_tagfile',
    'parse_tagfile_content'
    ]


import tempfile

import apt_pkg

from lp.services.mail.signedmessage import strip_pgp_signature


class TagFileParseError(Exception):
    """This exception is raised if parse_changes encounters nastiness"""
    pass


def parse_tagfile_content(content, filename=None):
    """Parses a tag file and returns a dictionary where each field is a key.

    The mandatory first argument is the contents of the tag file as a
    string.

    An OpenPGP cleartext signature will be stripped before parsing if
    one is present.
    """

    with tempfile.TemporaryFile() as f:
        f.write(strip_pgp_signature(content))
        f.seek(0)
        stanzas = list(apt_pkg.TagFile(f))
    if len(stanzas) != 1:
        raise TagFileParseError(
            "%s: multiple stanzas where only one is expected" % filename)

    [stanza] = stanzas

    # We can't do this sensibly with dict() or update(), as it has some
    # keys without values.
    trimmed_dict = {}
    for key in stanza.keys():
        try:
            trimmed_dict[key] = stanza[key]
        except KeyError:
            pass
    return trimmed_dict


def parse_tagfile(filename):
    """Parses a tag file and returns a dictionary where each field is a key.

    The mandatory first argument is the filename of the tag file, and
    the contents of that file is passed on to parse_tagfile_content.
    """
    with open(filename, "r") as changes_in:
        content = changes_in.read()
    if not content:
        raise TagFileParseError("%s: empty file" % filename)
    return parse_tagfile_content(content, filename=filename)
