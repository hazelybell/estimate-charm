# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import re


DBUSER = 'librarianlogparser'


# Regexp used to match paths to LibraryFileAliases.
lfa_path_re = re.compile('^/[0-9]+/')
multi_slashes_re = re.compile('/+')


def get_library_file_id(path):
    path = multi_slashes_re.sub('/', path)
    if not lfa_path_re.match(path):
        # We only count downloads of LibraryFileAliases, and this is
        # not one of them.
        return None

    file_id = path.split('/')[1]
    assert file_id.isdigit(), ('File ID is not a digit: %s' % path)
    return file_id
