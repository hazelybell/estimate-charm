#!/usr/bin/env python

"""
HTTP interface to UnnaturalCode, and (transitivly) MITLM.

Currently only serves up a Python service.
"""

import functools

import unnaturalcode.ucUser

from flask import Flask, request, abort, json


app = Flask(__name__)


class PythonCorpus(object):
    name = 'Python corpus_name [MITLM]'
    description = None
    language = 'Python'

    # Get the singleton instance of the underlying Python language model.
    _underlying_lm = unnaturalcode.ucUser.pyUser()
    # [sigh]... this API.
    _lm = _underlying_lm.lm()

    # TODO: Come up with these next two DYNAMICALLY.
    order = 10
    smoothing = 'ModKN'

    def __init__(self):
        self.last_updated = None

    @property
    def summary(self):
        "Returns a select portion of properties."

        props = ('name', 'description', 'language', 'order', 'smoothing',
                'last_updated')
        return {attr: getattr(self, attr) for attr in props}

    def tokenize(self, string):
        """
        Tokenizes the given string in the manner appropriate for this
        corpus's language model.
        """
        return self._lm.lex(string)

    def train(self, tokens):
        """
        Trains the language model with tokens -- precious tokens!
        Updates last_updated as a side-effect.
        """
        pass

    def predict(self, prefix):
        pass

    def cross_entropy(self, tokens):
        pass



CORPORA = {
    'py': PythonCorpus()
}


# TODO: Should probably export these next four to a web utils module or
# something...

# Create a "NotFound" singleton
NotFound = type('NotFound', (object,), {'__repr__': lambda s: 'NotFound'})

def get_corpus_or_404(name):
    "Returns corpus_name; aborts request if the corpus_name is not found."
    if name not in CORPORA:
        abort(404)
    return CORPORA[name]

def get_default(seq, index, default=None):
    if len(seq) <= index:
        return default
    return seq[index]

def jsonify(fn):
    @functools.wraps(fn)
    def json_returned(*args, **kwargs):
        value = fn(*args, **kwargs)
        if not isinstance(value, tuple):
            value = (value,)
        content = json.jsonify(get_default(value, 0))
        status = get_default(value, 1, 200)
        headers = get_default(value, 2, {})
        return content, status, headers
    return json_returned


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
