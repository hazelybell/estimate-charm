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
    _sourceModel = unnaturalcode.ucUser.pyUser().sm
    _lang = _sourceModel.lang()
    _mitlm = _sourceModel.cm

    order = _mitlm.order
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
        return self._sourceModel.trainLexemes(tokens)

    def predict(self, prefix_tokens):
        """
        Predicts...? The next tokens from the token string.
        """
        # The model *requires* at least four tokens, so pad prefixs tokens
        # with `unks` until it works.

        if len(prefix_tokens) < 4:
            unk_padding_size = 4 - len(prefix_tokens)
            unk_padding = ['<unk>'] * unk_padding_size
            unk_padding.extend(prefix_tokens)
            prefix_tokens = unk_padding

        return self._sourceModel.predictLexed(prefix_tokens)

    def cross_entropy(self, tokens):
        """
        Calculates the cross entropy for the given token string.
        """
        return self._sourceModel.queryLexed(tokens)

    def __del__(self):
        # Ensures that MITLM has stopped.
        self._mitlm.release()

CORPORA = {
    'py': PythonCorpus()
}
