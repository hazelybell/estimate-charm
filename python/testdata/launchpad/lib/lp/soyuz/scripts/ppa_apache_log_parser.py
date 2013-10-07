# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = ['DBUSER', 'get_ppa_file_key']

import os.path
import urllib

from lp.archiveuploader.utils import re_isadeb


DBUSER = 'ppa-apache-log-parser'


def get_ppa_file_key(path):
    split_path = os.path.normpath(urllib.unquote(path)).split('/')
    if len(split_path) != 9:
        return None

    if re_isadeb.match(split_path[8]) is None:
        return None

    return tuple(split_path[1:4]) + (split_path[8],)
