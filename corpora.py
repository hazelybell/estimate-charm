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

