# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Pick up the standard Mailman defaults
from Mailman.Defaults import *

# Use a name for the site list that is very unlikely to conflict with any
# possible Launchpad team name.  The default is "mailman" and that doesn't cut
# it. :)  The site list is never used by Launchpad, but it's required by
# Mailman 2.1.
MAILMAN_SITE_LIST = 'unused_mailman_site_list'

# We don't need to coordinate aliases with a mail server because we'll be
# pulling incoming messages from a POP account.
MTA = None

# Disable runners for features we don't need.
QRUNNERS = [
    ('ArchRunner',     1), # messages for the archiver
    ('BounceRunner',   1), # for processing the qfile/bounces directory
##     ('CommandRunner',  1), # commands and bounces from the outside world
    ('IncomingRunner', 1), # posts from the outside world
##     ('NewsRunner',     1), # outgoing messages to the nntpd
    ('OutgoingRunner', 1), # outgoing messages to the smtpd
    ('VirginRunner',   1), # internally crafted (virgin birth) messages
    ('RetryRunner',    1), # retry temporarily failed deliveries
    # Non-standard runners we've added.
    ('XMLRPCRunner',   1), # Poll for XMLRPC requests
    ]

# Other list defaults.
DEFAULT_GENERIC_NONMEMBER_ACTION = 3 # Discard
DEFAULT_SEND_REMINDERS = No
DEFAULT_SEND_WELCOME_MSG = Yes
DEFAULT_SEND_GOODBYE_MSG = No
DEFAULT_DIGESTABLE = No
DEFAULT_BOUNCE_NOTIFY_OWNER_ON_DISABLE = No
DEFAULT_BOUNCE_NOTIFY_OWNER_ON_REMOVAL = No
VERP_PERSONALIZED_DELIVERIES = Yes
DEFAULT_FORWARD_AUTO_DISCARDS = No
DEFAULT_BOUNCE_PROCESSING = No

# Modify the global pipeline to add some handlers for Launchpad specific
# functionality.
# - ensure posters are Launchpad members.
GLOBAL_PIPELINE.insert(0, 'LaunchpadMember')
# - insert our own RFC 2369 and RFC 5064 headers; this must appear after
#   CookHeaders
index = GLOBAL_PIPELINE.index('CookHeaders')
GLOBAL_PIPELINE.insert(index + 1, 'LaunchpadHeaders')
# - Insert our own moderation handlers instead of the standard Mailman
#   Moderate and Hold handlers.  Hold always comes after Moderate in the
#   default global pipeline.
index = GLOBAL_PIPELINE.index('Moderate')
GLOBAL_PIPELINE[index:index + 2] = ['LPStanding', 'LPModerate', 'LPSize']
