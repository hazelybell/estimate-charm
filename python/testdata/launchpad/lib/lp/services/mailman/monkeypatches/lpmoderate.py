# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A pipeline handler for holding list non-members postings for approval.
"""

from email.iterators import typed_subpart_iterator
from email.Utils import (
    formatdate,
    make_msgid,
    )
import xmlrpclib

from Mailman import Errors
from Mailman.Logging.Syslog import syslog
from Mailman.Queue import XMLRPCRunner


def process(mlist, msg, msgdata):
    """Handle all list non-member postings.

    For Launchpad members who are not list-members, a previous handler will
    check their personal standing to see if they are allowed to post.  This
    handler takes care of all other cases and it overrides Mailman's standard
    Moderate handler.  It also knows how to hold messages in Launchpad's
    librarian.
    """
    # If the message is already approved, then this handler is done.
    if msgdata.get('approved'):
        return
    # If the sender is a member of the mailing list, then this handler is
    # done.  Note that we don't need to check the member's Moderate flag as
    # the original Mailman handler does, because for Launchpad, we know it
    # will always be unset.
    for sender in msg.get_senders():
        if mlist.isMember(sender):
            return
    # From here on out, we're dealing with senders who are not members of the
    # mailing list.  They are also not Launchpad members in good standing or
    # we'd have already approved the message.  So now the message must be held
    # in Launchpad for approval via the LP u/i.
    hold(mlist, msg, msgdata, 'Not subscribed')


def is_message_empty(msg):
    """Is the message missing a text/plain part with content?"""
    for part in typed_subpart_iterator(msg, 'text'):
        if part.get_content_subtype() == 'plain':
            if len(part.get_payload().strip()) > 0:
                return False
    return True


def hold(mlist, msg, msgdata, annotation):
    """Hold the message in both Mailman and Launchpad.

    `annotation` is an arbitrary string required by the API.
    """
    # Hold the message in Mailman and Launchpad so that it's easier to
    # resubmit it after approval via the LP u/i.  If the team administrator
    # ends up rejecting the message, it will also be easy to discard it on the
    # Mailman side.  But this way, we don't have to reconstitute the message
    # from the librarian if it gets approved.  However, unlike the standard
    # Moderate handler, we don't craft all the notification messages about
    # this hold.  We also need to keep track of the message-id (which better
    # be unique) because that's how we communicate about the message's status.
    request_id = mlist.HoldMessage(msg, annotation, msgdata)
    assert mlist.Locked(), (
        'Mailing list should be locked: %s' % mlist.internal_name())
    # This is a hack because by default Mailman cannot look up held messages
    # by message-id.  This works because Mailman's persistency layer simply
    # pickles the MailList object, mostly without regard to a known schema.
    #
    # Mapping: message-id -> request-id
    holds = getattr(mlist, 'held_message_ids', None)
    if holds is None:
        holds = mlist.held_message_ids = {}
    message_id = msg.get('message-id')
    if message_id is None:
        msg['Message-ID'] = message_id = make_msgid()
    if message_id in holds:
        # No legitimate sender should ever give us a message with a duplicate
        # message id, so treat this as spam.
        syslog('vette',
               'Discarding duplicate held message-id: %s', message_id)
        raise Errors.DiscardMessage
    # Discard messages that claim to be from the list itself because Mailman's
    # internal handlers did not approve the message before it arrived at this
    # step--these messages are forgeries.
    list_address = mlist.getListAddress()
    for sender in msg.get_senders():
        if list_address == sender:
            syslog('vette',
                   'Discarding forged message-id: %s', message_id)
            raise Errors.DiscardMessage
    # Discard messages without text content since there will be nothing to
    # moderate. Most of these messages are spam.
    if is_message_empty(msg):
        syslog('vette',
               'Discarding text-less message-id: %s', message_id)
        raise Errors.DiscardMessage
    holds[message_id] = request_id
    # In addition to Message-ID, the librarian requires a Date header.
    if 'date' not in msg:
        msg['Date'] = formatdate()
    # Store the message in the librarian.
    proxy = XMLRPCRunner.get_mailing_list_api_proxy()
    # This will fail if we can't talk to Launchpad.  That's okay though
    # because Mailman's IncomingRunner will re-queue the message and re-start
    # processing at this handler.
    proxy.holdMessage(mlist.internal_name(),
                      xmlrpclib.Binary(msg.as_string()))
    syslog('vette', 'Holding message for LP approval: %s', message_id)
    # Raise this exception, signaling to the incoming queue runner that it is
    # done processing this message, and should not send it through any further
    # handlers.
    raise Errors.HoldMessage
