# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions to accomodate testing of the email system."""

__all__ = ['read_test_message']

__metaclass__ = type

import os.path

from lp.services.mail.signedmessage import signed_message_from_string


testmails_path = os.path.join(os.path.dirname(__file__), 'emails')

def read_test_message(filename):
    """Reads a test message and returns it as ISignedMessage.

    The test messages are located in lp/services/mail/tests/emails
    """
    message_string = open(os.path.join(testmails_path, filename)).read()
    return signed_message_from_string(message_string)
