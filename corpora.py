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

import os
import unnaturalcode.ucUser

__all__ = ['PythonCorpus', 'CORPORA']

# See "On Naturalness of Software", Hindle et al. 2012
BEHINDLE_NGRAM_ORDER = 6
GOOD_ENOUGH_NGRAM_ORDER = 4


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
    _pyUser = unnaturalcode.ucUser.pyUser(ngram_order=GOOD_ENOUGH_NGRAM_ORDER)
    _sourceModel = _pyUser.sm
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

    def tokenize(self, string, mid_line=True):
        """
        Tokenizes the given string in the manner appropriate for this
        corpus's language model.
        """
        return self._lang.lex(string, mid_line)

    def train(self, tokens):
        """
        Trains the language model with tokens -- precious tokens!
        Updates last_updated as a side-effect.
        """
        return self._sourceModel.trainLexemes(tokens)

    def predict(self, tokens):
        """
        Returns a dict of:
            * suggestions: a list of suggestions from the given token string.
            * tokens: the actual list of tokens used in the prediction. Note
                      that this may be different from the given input.
        """

        # The model *requires* at least four tokens, so pad prefixs tokens
        # with `unks` until it works.
        if len(tokens) < 4:
            unk_padding_size = 4 - len(tokens)
            prefix_tokens = [[None, None, None, None, '<unk>']] * unk_padding_size
        else:
            prefix_tokens = []
        prefix_tokens.extend(tokens)

        # Truncate to the n-gram order size, because those are all the tokens
        # that you really need for prediction...
        prefix_tokens = prefix_tokens[-self.order:]

        return {
            'suggestions': self._sourceModel.predictLexed(prefix_tokens),
            'tokens': prefix_tokens
        }

    def cross_entropy(self, tokens):
        """
        Calculates the cross entropy for the given token string.
        """
        return self._sourceModel.queryLexed(tokens)

    def reset(self):
        # Halt the MITLM process.
        self._mitlm.stopMitlm()

        # Right now, since there is only one corpus, we can just hardcode its
        # path:
        base_path = os.path.expanduser('~/.unnaturalCode/')
        path = os.path.join(base_path, 'pyCorpus')

        # Ain't gotta do nothing if the file doesn't exist.
        if os.path.exists(path):
            replacementPath = os.path.join(base_path, 'pyCorpus.bak')
            shutil.move(path, replacementPath)

    def __del__(self):
        # Ensures that MITLM has stopped.
        self._mitlm.release()

CORPORA = {
    'py': PythonCorpus()
}
