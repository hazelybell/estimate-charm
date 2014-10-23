#!/usr/bin/env python

"""
Defines corpus object(s).
Currently, only PythonCorpus is defined.
"""

import unnaturalcode.ucUser

__all__ = ['PythonCorpus', 'CORPORA']


class PythonCorpus(object):
    """
    The default UnnaturalCode Python corpus.
    """

    name = 'Python corpus_name [MITLM]'
    description = __doc__
    language = 'Python'

    # Get the singleton instance of the underlying Python language (source)
    # model.
    # [sigh]... this API.
    _corpus = unnaturalcode.ucUser.pyUser().sm
    _lang = _corpus.lang()
    #pdb.set_trace()

    order = _corpus.cm.order
    # Hard-coded because "it's the best! the best a language model can get!"
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
        return self._lang.lex(string)

    def train(self, tokens):
        """
        Trains the language model with tokens -- precious tokens!
        Updates last_updated as a side-effect.
        """
        return self._corpus.trainLexemes(tokens)

    def predict(self, prefix_tokens):
        """
        Predicts...? The next tokens from the token string.
        """
        return self._corpus.predictLexed(prefix_tokens)

    def cross_entropy(self, tokens):
        """
        Calculates the cross entropy for the given token string.
        """
        return self._corpus.queryLexed(tokens)


CORPORA = {
    'py': PythonCorpus()
}
