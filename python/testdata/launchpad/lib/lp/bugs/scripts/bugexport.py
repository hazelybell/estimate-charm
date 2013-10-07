# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'BUGS_XMLNS',
    'export_bugtasks',
    'serialise_bugtask',
    ]

import base64


try:
    import xml.etree.cElementTree as ET
except ImportError:
    import cElementTree as ET

from zope.component import getUtility
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.browser.bugtask import get_comments_for_bugtask

BUGS_XMLNS = 'https://launchpad.net/xmlns/2006/bugs'


def addnode(parent, elementname, content, **attrs):
    node = ET.SubElement(parent, elementname, attrs)
    node.text = content
    node.tail = '\n'
    return node


def addperson(parent, elementname, person):
    return addnode(parent, elementname, person.displayname, name=person.name)


def serialise_bugtask(bugtask):
    bug = bugtask.bug
    bug_node = ET.Element('bug', id=str(bug.id))
    bug_node.text = bug_node.tail = '\n'

    addnode(bug_node, 'private', str(bug.private))
    addnode(bug_node, 'security_related', str(bug.security_related))
    if bug.duplicateof is not None:
        addnode(bug_node, 'duplicateof', str(bug.duplicateof.id))
    addnode(bug_node, 'datecreated',
            bug.datecreated.strftime('%Y-%m-%dT%H:%M:%SZ'))
    if bug.name is not None:
        addnode(bug_node, 'nickname', bug.name)
    addnode(bug_node, 'title', bug.title)
    addnode(bug_node, 'description', bug.description)
    addperson(bug_node, 'reporter', bug.owner)

    # Information from bug task:
    addnode(bug_node, 'status', bugtask.status.name)
    addnode(bug_node, 'importance', bugtask.importance.name)
    if bugtask.milestone is not None:
        addnode(bug_node, 'milestone', bugtask.milestone.name)
    if bugtask.assignee is not None:
        addperson(bug_node, 'assignee', bugtask.assignee)

    if bug.tags:
        tags_node = ET.SubElement(bug_node, 'tags')
        tags_node.text = tags_node.tail = '\n'
        for tag in bug.tags:
            addnode(tags_node, 'tag', tag)

    subscribers = bug.getDirectSubscribers()
    if subscribers:
        subs_node = ET.SubElement(bug_node, 'subscriptions')
        subs_node.text = subs_node.tail = '\n'
        for person in subscribers:
            addperson(subs_node, 'subscriber', person)

    for comment in get_comments_for_bugtask(bugtask):
        comment_node = ET.SubElement(bug_node, 'comment')
        comment_node.text = comment_node.tail = '\n'
        addperson(comment_node, 'sender', comment.owner)
        addnode(comment_node, 'date',
                comment.datecreated.strftime('%Y-%m-%dT%H:%M:%SZ'))
        addnode(comment_node, 'text', comment.text_for_display)
        for attachment in comment.bugattachments:
            attachment_node = ET.SubElement(
                comment_node, 'attachment',
                href=ProxiedLibraryFileAlias(
                    attachment.libraryfile, attachment).http_url)
            attachment_node.text = attachment_node.tail = '\n'
            addnode(attachment_node, 'type', attachment.type.name)
            addnode(attachment_node, 'filename',
                    attachment.libraryfile.filename)
            addnode(attachment_node, 'title', attachment.title)
            addnode(attachment_node, 'mimetype',
                    attachment.libraryfile.mimetype)
            # Attach the attachment file contents, base 64 encoded.
            addnode(attachment_node, 'contents',
                    base64.encodestring(attachment.libraryfile.read()))

    return bug_node


def export_bugtasks(ztm, bugtarget, output, include_private=False):
    # Collect bug task IDs.
    if include_private:
        # The admin team can see all bugs
        user = getUtility(ILaunchpadCelebrities).admin
    else:
        user = None
    ids = [task.id for task in bugtarget.searchTasks(
        BugTaskSearchParams(user=user, omit_dupes=False, orderby='id'))]
    bugtaskset = getUtility(IBugTaskSet)
    output.write('<launchpad-bugs xmlns="%s">\n' % BUGS_XMLNS)
    for count, taskid in enumerate(ids):
        task = bugtaskset.get(taskid)
        tree = ET.ElementTree(serialise_bugtask(task))
        tree.write(output)
        # Periodically abort the transaction so that we don't lock
        # everyone else out.
        if count % 100:
            ztm.abort()
    output.write('</launchpad-bugs>\n')
