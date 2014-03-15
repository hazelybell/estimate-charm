# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A pipeline handler for checking message sizes."""

import email

from Mailman import (
    Errors,
    Message,
    mm_cfg,
    )
from Mailman.Handlers.LPModerate import hold
from Mailman.Logging.Syslog import syslog


def truncated_message(original_message, limit=10000):
    """Create a smaller version of the message for moderation."""
    message = email.message_from_string(
        original_message.as_string(), Message.Message)
    for part in email.iterators.typed_subpart_iterator(message, 'multipart'):
        subparts = part.get_payload()
        removeable = []
        for subpart in subparts:
            if subpart.get_content_maintype() == 'multipart':
                # This part is handled in the outer loop.
                continue
            elif subpart.get_content_type() == 'text/plain':
                # Truncate the message at 10kb so that there is enough
                # information for the moderator to make a decision.
                content = subpart.get_payload().strip()
                if len(content) > limit:
                    subpart.set_payload(
                        content[:limit] + '\n[truncated for moderation]',
                        subpart.get_charset())
            else:
                removeable.append(subpart)
        for subpart in removeable:
            subparts.remove(subpart)
    return message


def process(mlist, msg, msgdata):
    """Check the message size (approximately) against hard and soft limits.

    If the message is below the soft limit, do nothing.  This allows the
    message to be posted without moderation, assuming no other handler get
    triggered of course.

    Messages between the soft and hard limits get moderated in the Launchpad
    web u/i, just as non-member posts would.  Personal standing does not
    override the size checks.

    Messages above the hard limit get logged and discarded.  In production, we
    should never actually hit the hard limit.  The Exim in front of
    lists.launchpad.net has its own hard limit of 50MB (which is the
    production standard Mailman hard limit value), so messages larger than
    this should never even show up.
    """
    # Calculate the message size by turning it back into a string.  In Mailman
    # 3.0 this calculation is done on initial message parse so it will be
    # quicker and not consume so much memory.  But since the hard limit is
    # 50MB I don't think we can actually get into any real trouble here, as
    # long as we can trust Python's reference counter.
    message_size = len(msg.as_string())
    # Hard and soft limits are specified in bytes.
    if message_size < mm_cfg.LAUNCHPAD_SOFT_MAX_SIZE:
        # Nothing to do.
        return
    if message_size < mm_cfg.LAUNCHPAD_HARD_MAX_SIZE:
        # Hold the message in Mailman.  See lpmoderate.py for similar
        # algorithm.
        # There is a limit to the size that can be stored in Lp. Send
        # a trucated copy of the message that has enough information for
        # the moderator to make a decision.
        hold(mlist, truncated_message(msg), msgdata, 'Too big')
    # The message is larger than the hard limit, so log and discard.
    syslog('vette', 'Discarding message w/size > hard limit: %s',
           msg.get('message-id', 'n/a'))
    raise Errors.DiscardMessage
