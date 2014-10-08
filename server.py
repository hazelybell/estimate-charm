#!/usr/bin/env python

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


@app.route('/<corpus_name>/predict/<path:token_str>', methods=('GET', 'POST'))
@jsonify
def predict(corpus_name, token_str=None):
    """
    POST /{corpus}/predict/{tokens*}

    Returns a number of suggestions for the given token prefix.
    """
    corpus = get_corpus_or_404(corpus_name)

    # TODO: Implement parameters
    #  n - number of additional tokens to predict
    #  s - number of suggestions to emit

    if token_str is not None:
        tokens = parse_tokens(token_str)
    else:
        tokens = corpus.tokenize(get_string_content())

    return {'suggestions': corpus.predict(tokens)}


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

    # TODO: return some kind of statistics?
    return {'result': corpus.train(tokens)}, 201


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
    return {'tokens': corpus.tokenize(content)}


if __name__ == '__main__':
    app.run(debug=True)
