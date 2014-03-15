# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A pipeline handler for moderating Launchpad users based on standing.

This handler checks Launchpad member's personal standing in order to determine
whether list non-members are allowed to post to a mailing list.
"""

from Mailman.Queue import XMLRPCRunner


def process(mlist, msg, msgdata):
    """Check the standing of a non-Launchpad member.

    A message posted to a mailing list from a Launchpad member in good
    standing is allowed onto the list even if they are not members of the
    list.

    Because this handler comes before the standard Moderate handler, if the
    sender is not in good standing, we just defer to other decisions further
    along the pipeline.  If the sender is in good standing, we approve it.
    """
    sender = msg.get_sender()
    # Ask Launchpad about the standing of this member.
    in_good_standing = False
    proxy = XMLRPCRunner.get_mailing_list_api_proxy()
    # This will fail if we can't talk to Launchpad.  That's okay though
    # because Mailman's IncomingRunner will re-queue the message and re-start
    # processing at this handler.
    try:
        in_good_standing = proxy.inGoodStanding(sender)
    except Exception as error:
        XMLRPCRunner.handle_proxy_error(error, msg, msgdata)
    # If the sender is a member in good standing, that's all we need to know
    # in order to let the message pass.
    if in_good_standing:
        msgdata['approved'] = True
