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
HTTP interface to UnnaturalCode, and (transitivly) MITLM.

Currently only serves up a Python service.
"""

from api_utils import get_corpus_or_404, get_string_content, NotFound, jsonify
from flask import Flask, request, abort, json
from token_fmt import parse_tokens


app = Flask(__name__)

#/ ROUTES /####################################################################
###############################################################################


@app.route('/<corpus_name>/')
@jsonify
def corpus_info(corpus_name):
    """
    GET /{corpus}/

    Retrieve a summary of the corpus info.
    """
    corpus = get_corpus_or_404(corpus_name)
    return corpus.summary


@app.route('/<corpus_name>/predict/',
        defaults={'token_str': ''}, methods=('POST',))
@app.route('/<corpus_name>/predict/<path:token_str>', methods=('GET',))
@jsonify
def predict(corpus_name, token_str=""):
    """
    POST /{corpus}/predict/{tokens*}
    POST /{corpus}/predict/f=?

    Returns a number of suggestions for the given token prefix.
    """
    corpus = get_corpus_or_404(corpus_name)

    if token_str :
        tokens = parse_tokens(token_str)
    else:
        tokens = corpus.tokenize(get_string_content())

    # Predict returns a nice, JSONable dictionary, so just return that.
    return corpus.predict(tokens)


@app.route('/<corpus_name>/cross-entropy')
@app.route('/<corpus_name>/xentropy', methods=('GET', 'POST'))
@jsonify
def cross_entropy(corpus_name):
    """
    POST /{corpus}/xentropy/

    Calculate the cross-entropy of the uploaded file with respect to the
    corpus.
    """
    corpus = get_corpus_or_404(corpus_name)
    content = get_string_content()
    tokens = corpus.tokenize(content)
    return {'cross_entropy': corpus.cross_entropy(tokens)}


@app.route('/<corpus_name>/', methods=('POST',))
@jsonify
def train(corpus_name):
    """
    POST /{corpus}/

    Upload a file for training.
    """
    corpus = get_corpus_or_404(corpus_name)
    content = get_string_content()
    tokens = corpus.tokenize(content)

    return {
        'result': corpus.train(tokens),
        'tokens': len(tokens)
    }, 202


@app.route('/<corpus_name>/tokenize', methods=('POST',))
@jsonify
def tokenize(corpus_name):
    """
    POST /{corpus}/tokenize
    GET  /{corpus}/tokenize?s=...

    Tokenize the given string for this corpus's language.
    """
    corpus = get_corpus_or_404(corpus_name)
    # Args... should be a file or strong
    content = get_string_content()
    return {'tokens': corpus.tokenize(content, mid_line=False)}


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
