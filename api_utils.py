#!/usr/bin/env python

# Copyright (C) 2014  Eddie Antonio Santos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.



"""
Utitlities for common Flask operations.
"""

from functools import wraps
from flask import json, abort, request
from corpora import CORPORA


def get_corpus_or_404(name):
    "Returns corpus_name; aborts Request if the corpus_name is not found."
    if name not in CORPORA:
        abort(404)
    return CORPORA[name]


def get_string_content():
    """
    Gets string contents from either 'f' for file or 's' for string.
    """
    content = request.files.get('f')
    # Try the file first...
    if content is not None:
        return content.read()

    content = request.form.get('s')
    # Next, try the content.
    if content is not None:
        return content

    # Bad request!
    abort(400)
