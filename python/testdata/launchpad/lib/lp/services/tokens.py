# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utility methods for random token generation."""

__metaclass__ = type

__all__ = [
    'create_token',
    'create_unique_token_for_table',
    ]

import random

from lp.services.database.interfaces import IMasterStore


def create_token(token_length):
    """Create a random token string.

    :param token_length: Specifies how long you want the token.
    """
    # Since tokens are, in general, user-visible, vowels are not included
    # below to prevent them from having curse/offensive words.
    characters = '0123456789bcdfghjklmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ'
    token = ''.join(
        random.choice(characters) for count in range(token_length))
    return unicode(token)


def create_unique_token_for_table(token_length, column):
    """Create a new unique token in a table.

    Generates a token and makes sure it does not already exist in
    the table and column specified.

    :param token_length: The length for the token string
    :param column: Database column where the token will be stored.

    :return: A new token string
    """
    # Use the master Store to ensure no race conditions. 
    store = IMasterStore(column.cls)
    token = create_token(token_length)
    while store.find(column.cls, column==token).one() is not None:
        token = create_token(token_length)
    return token
