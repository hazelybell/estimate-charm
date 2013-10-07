# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A global pipeline handler for determining Launchpad membership."""


import hashlib

from Mailman import (
    Errors,
    mm_cfg,
    )
from Mailman.Logging.Syslog import syslog
from Mailman.Queue import XMLRPCRunner


def process(mlist, msg, msgdata):
    """Discard the message if it doesn't come from a Launchpad member."""
    if msgdata.get('approved'):
        return
    # Some automated processes will send messages to the mailing list. For
    # example, if the list is a contact address for a team and that team is
    # the contact address for a project's answer tracker, an automated message
    # will be sent from Launchpad. Check for a header that indicates this was
    # a Launchpad-generated message. See
    # lp.services.mail.sendmail.sendmail for where this is set.
    secret = msg['x-launchpad-hash']
    message_id = msg['message-id']
    if secret and message_id:
        hash = hashlib.sha1(mm_cfg.LAUNCHPAD_SHARED_SECRET)
        hash.update(message_id)
        if secret == hash.hexdigest():
            # Since this message is coming from Launchpad, pre-approve it.
            # Yes, this could be spoofed, but there's really no other way
            # (currently) to do it.
            msgdata['approved'] = True
            return
    # Ask Launchpad whether the sender is a Launchpad member.  If not, discard
    # the message with extreme prejudice, but log this.
    sender = msg.get_sender()
    # Check with Launchpad about whether the sender is a member or not.  If we
    # can't talk to Launchpad, I believe it's better to let the message get
    # posted to the list than to discard or hold it.
    is_member = True
    proxy = proxy = XMLRPCRunner.get_mailing_list_api_proxy()
    # This will fail if we can't talk to Launchpad.  That's okay though
    # because Mailman's IncomingRunner will re-queue the message and re-start
    # processing at this handler.
    try:
        is_member = proxy.isRegisteredInLaunchpad(sender)
    except Exception as error:
        XMLRPCRunner.handle_proxy_error(error, msg, msgdata)
    # This handler can just return if the sender is a member of Launchpad.
    if is_member:
        return
    # IncomingRunner already posts the Message-ID to the logs/vette for
    # discarded messages, so we only need to add a little more detail here.
    syslog('vette', 'Sender is not a Launchpad member: %s', sender)
    raise Errors.DiscardMessage
