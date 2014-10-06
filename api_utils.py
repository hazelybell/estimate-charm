#!/usr/bin/env python

"""
Utitlities for common Flask operations.
"""

from functools import wraps
from flask import json, abort, request
from corpora import CORPORA


# Create a "NotFound" singleton
NotFound = type('NotFound', (object,), {'__repr__': lambda s: 'NotFound'})


def get_corpus_or_404(name):
    "Returns corpus_name; aborts Request if the corpus_name is not found."
    if name not in CORPORA:
        abort(404)
    return CORPORA[name]


def get_default(seq, index, default=None):
    if len(seq) <= index:
        return default
    return seq[index]


def jsonify(fn):
    @wraps(fn)
    def json_returned(*args, **kwargs):
        value = fn(*args, **kwargs)
        if not isinstance(value, tuple):
            value = (value,)
        content = json.jsonify(get_default(value, 0))
        status = get_default(value, 1, 200)
        headers = get_default(value, 2, {})
        return content, status, headers
    return json_returned


def get_string_content():
    "Gets string contents from either 'f' or 'file'."
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
