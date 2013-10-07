# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mail for new bugs."""

__metaclass__ = type
__all__ = [
    'generate_bug_add_email',
    ]

from lp.services.mail.mailwrapper import MailWrapper
from lp.services.webapp.publisher import canonical_url


def generate_bug_add_email(bug, new_recipients=False, reason=None,
                           subscribed_by=None, event_creator=None):
    """Generate a new bug notification from the given IBug.

    If new_recipients is supplied we generate a notification explaining
    that the new recipients have been subscribed to the bug. Otherwise
    it's just a notification of a new bug report.
    """
    subject = u"[Bug %d] [NEW] %s" % (bug.id, bug.title)
    contents = ''

    if bug.private:
        # This is a confidential bug.
        visibility = u"Private"
    else:
        # This is a public bug.
        visibility = u"Public"

    if bug.security_related:
        visibility += ' security'
        contents += '*** This bug is a security vulnerability ***\n\n'

    bug_info = []
    # Add information about the affected upstreams and packages.
    for bugtask in bug.bugtasks:
        bug_info.append(u"** Affects: %s" % bugtask.bugtargetname)
        bug_info.append(u"     Importance: %s" % bugtask.importance.title)

        if bugtask.assignee:
            # There's a person assigned to fix this task, so show that
            # information too.
            bug_info.append(
                u"     Assignee: %s" % bugtask.assignee.unique_displayname)
        bug_info.append(u"         Status: %s\n" % bugtask.status.title)

    if bug.tags:
        bug_info.append('\n** Tags: %s' % ' '.join(bug.tags))

    mailwrapper = MailWrapper(width=72)
    content_substitutions = {
        'visibility': visibility,
        'bug_url': canonical_url(bug),
        'bug_info': "\n".join(bug_info),
        'bug_title': bug.title,
        'description': mailwrapper.format(bug.description),
        'notification_rationale': reason,
        }

    if new_recipients:
        if "assignee" in reason and event_creator is not None:
            if event_creator == bugtask.assignee:
                contents += (
                    "You have assigned this bug to yourself for %(target)s")
            else:
                contents += (
                    "%(assigner)s has assigned this bug to you for " +
                    "%(target)s")
            content_substitutions['assigner'] = (
                event_creator.unique_displayname)
            content_substitutions['target'] = bugtask.target.displayname
        else:
            contents += "You have been subscribed to a %(visibility)s bug"
        if subscribed_by is not None:
            contents += " by %(subscribed_by)s"
            content_substitutions['subscribed_by'] = (
                subscribed_by.unique_displayname)
        contents += (":\n\n"
                     "%(description)s\n\n%(bug_info)s")
        # The visibility appears mid-phrase so.. hack hack.
        content_substitutions['visibility'] = visibility.lower()
        # XXX: kiko, 2007-03-21:
        # We should really have a centralized way of adding this
        # footer, but right now we lack a INotificationRecipientSet
        # for this particular situation.
        contents += (
            "\n-- \n%(bug_title)s\n%(bug_url)s\n%(notification_rationale)s")
    else:
        contents += ("%(visibility)s bug reported:\n\n"
                     "%(description)s\n\n%(bug_info)s")

    contents = contents % content_substitutions

    contents = contents.rstrip()

    return (subject, contents)
