#!/usr/bin/env python

"""
HTTP interface to UnnaturalCode, and (transitivly) MITLM.

Currently only serves up a Python service.
"""

from api_utils import get_corpus_or_404, NotFound, jsonify
from flask import Flask, request, abort, json



app = Flask(__name__)

#/ ROUTES /#####################################################################
################################################################################

# GET /{corpus}/
@app.route('/<corpus_name>/')
@jsonify
def corpus_info(corpus_name):
    corpus = get_corpus_or_404(corpus_name)
    return corpus.summary


# POST /{corpus}/predict/{tokens}
@app.route('/<corpus_name>/predict/<path:tokens>', methods=('GET', 'POST'))
@jsonify
def predict(corpus_name, tokens=None):
    get_corpus_or_404(corpus_name)
    # TODO
    abort(501)


# POST /{corpus}/xentropy/
@app.route('/<corpus_name>/cross-entropy/')
@app.route('/<corpus_name>/xentropy/', methods=('GET', 'POST'))
def cross_entropy(corpus_name):
    corpus = get_corpus_or_404(corpus_name)
    # TODO: cross entropy!
    abort(501)


# POST /{corpus}/
@app.route('/<corpus_name>/', methods=('POST',))
def train(corpus_name):
    # TODO: Get file and train.
    abort(501)


# POST /{corpus}/
@app.route('/<corpus_name>/tokenize', methods=('POST',))
@jsonify
def tokenize(corpus_name):
    corpus = get_corpus_or_404(corpus_name)
    # Args... should be a file or strong
    content = get_string_content()
    return {'tokens': corpus.tokenize(content)}


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


if __name__ == '__main__':
    app.run(debug=True)
