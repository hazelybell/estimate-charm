# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions for bug-related doctests and pagetests."""

from datetime import (
    datetime,
    timedelta,
    )
from operator import attrgetter
import re
import textwrap

from BeautifulSoup import BeautifulSoup
from pytz import UTC
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBugSet,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTaskSet,
    )
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.testing.pages import (
    extract_text,
    find_main_content,
    find_tag_by_id,
    find_tags_by_class,
    )


def print_direct_subscribers(bug_page):
    """Print the direct subscribers listed in a portlet."""
    print_subscribers(bug_page, 'Maybe', reverse=True)


def print_also_notified(bug_page):
    """Print the structural and duplicate subscribers listed in a portlet."""
    print 'Also notified:'
    print_subscribers(bug_page, 'Maybe')


def print_subscribers(bug_page, subscription_level=None, reverse=False):
    """Print the subscribers listed in the subscribers JSON portlet."""
    from simplejson import loads
    details = loads(bug_page)

    if details is None:
        # No subscribers at all.
        print ""
    else:
        lines = []
        for subscription in details:
            level_matches = (
                (not reverse and
                 subscription['subscription_level'] == subscription_level) or
                (reverse and
                 subscription['subscription_level'] != subscription_level))
            if subscription_level is None or level_matches:
                subscriber = subscription['subscriber']
                line = subscriber['display_name']
                if subscriber['can_edit']:
                    line += " (Unsubscribe)"
                lines.append(line)
        print "\n".join(sorted(lines))


def print_bug_affects_table(content, highlighted_only=False):
    """Print information about all the bug tasks in the 'affects' table.

        :param highlighted_only: Only print the highlighted row
    """
    main_content = find_main_content(content)
    affects_table = main_content.first('table', {'class': 'listing'})
    if highlighted_only:
        tr_attrs = {'class': 'highlight'}
    else:
        tr_attrs = {}
    tr_tags = affects_table.tbody.findAll(
        'tr', attrs=tr_attrs, recursive=False)
    for tr in tr_tags:
        if tr.td.table:
            # Don't print the bugtask edit form.
            continue
        # Strip zero-width white-spaces.
        print extract_text(tr).replace('&#8203;', '')


def print_remote_bugtasks(content):
    """Print the remote bugtasks of this bug.

    For each remote bugtask, print the target and the bugwatch.
    """
    affects_table = find_tags_by_class(content, 'listing')[0]
    for span in affects_table.findAll('span'):
        for key, value in span.attrs:
            if 'bug-remote' in value:
                target = extract_text(span.findAllPrevious('td')[-2])
                print target, extract_text(span.findNext('a'))


def print_bugs_list(content, list_id):
    """Print the bugs list with the given ID.

    Right now this is quite simplistic, in that it just extracts the
    text from the element specified by list_id. If the bug listing
    becomes more elaborate then this function will be the place to
    cope with it.
    """
    bugs_list = find_tag_by_id(content, list_id).findAll(
        None, {'class': 'similar-bug'})
    for node in bugs_list:
        # Also strip zero-width spaces out.
        print extract_text(node).replace('&#8203;', '')


def print_bugtasks(text, show_heat=None):
    """Print all the bugtasks in the text."""
    print '\n'.join(extract_bugtasks(text, show_heat=show_heat))


def extract_bugtasks(text, show_heat=None):
    """Extracts a list of strings for all the bugtasks in the text."""
    main_content = find_main_content(text)
    listing = main_content.find('div', {'id': 'bugs-table-listing'})
    if listing is None:
        return []
    rows = []
    for bugtask in listing('div', {'class': 'buglisting-row'}):
        bug_nr = extract_text(
            bugtask.find(None, {'class': 'bugnumber'})).replace('#', '')
        title = extract_text(bugtask.find(None, {'class': 'bugtitle'}))
        status = extract_text(
            bugtask.find(None, {'class': re.compile('status')}))
        importance = extract_text(
            bugtask.find(None, {'class': re.compile('importance')}))
        affects = extract_text(
            bugtask.find(
                None,
                {'class': re.compile(
                    'None|(sprite product|distribution|package-source) field')
                }))
        row_items = [bug_nr, title, affects, importance, status]
        if show_heat:
            heat = extract_text(
                bugtask.find(None, {'class': 'bug-heat-icons'}))
            row_items.append(heat)
        rows.append(' '.join(row_items))
    return rows


def create_task_from_strings(bug, owner, product, watchurl=None):
    """Create a task, optionally linked to a watch."""
    bug = getUtility(IBugSet).get(bug)
    product = getUtility(IProductSet).getByName(product)
    owner = getUtility(IPersonSet).getByName(owner)
    task = getUtility(IBugTaskSet).createTask(bug, owner, product)
    if watchurl:
        [watch] = getUtility(IBugWatchSet).fromText(watchurl, bug, owner)
        task.bugwatch = watch
    return task


def create_bug_from_strings(
    distribution, sourcepackagename, owner, summary, description,
    status=None):
    """Create and return a bug."""
    distroset = getUtility(IDistributionSet)
    distribution = distroset.getByName(distribution)

    personset = getUtility(IPersonSet)
    owner = personset.getByName(owner)

    bugset = getUtility(IBugSet)
    params = CreateBugParams(
        owner, summary, description, status=status,
        target=distribution.getSourcePackage(sourcepackagename))
    return bugset.createBug(params)


def update_task_status(task_id, person, status):
    """Update a bugtask status."""
    task = getUtility(IBugTaskSet).get(task_id)
    person = getUtility(IPersonSet).getByName(person)
    task.transitionToStatus(status, person)


def create_old_bug(
    title, days_old, target, status=BugTaskStatus.INCOMPLETE,
    with_message=True, external_bugtracker=None, assignee=None,
    milestone=None, duplicateof=None):
    """Create an aged bug.

    :title: A string. The bug title for testing.
    :days_old: An int. The bug's age in days.
    :target: A BugTarget. The bug's target.
    :status: A BugTaskStatus. The status of the bug's single bugtask.
    :with_message: A Bool. Whether to create a reply message.
    :external_bugtracker: An external bug tracker which is watched for this
        bug.
    """
    no_priv = getUtility(IPersonSet).getByEmail('no-priv@canonical.com')
    params = CreateBugParams(
        owner=no_priv, title=title, comment='Something is broken.')
    bug = target.createBug(params)
    if duplicateof is not None:
        bug.markAsDuplicate(duplicateof)
    sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')
    if with_message is True:
        bug.newMessage(
            owner=sample_person, subject='Something is broken.',
            content='Can you provide more information?')
    bugtask = bug.bugtasks[0]
    bugtask.transitionToStatus(
        status, sample_person)
    if assignee is not None:
        bugtask.transitionToAssignee(assignee)
    bugtask.milestone = milestone
    if external_bugtracker is not None:
        getUtility(IBugWatchSet).createBugWatch(bug=bug, owner=sample_person,
            bugtracker=external_bugtracker, remotebug='1234')
    date = datetime.now(UTC) - timedelta(days=days_old)
    removeSecurityProxy(bug).date_last_updated = date
    return bugtask


def summarize_bugtasks(bugtasks):
    """Summarize a sequence of bugtasks."""
    bugtaskset = getUtility(IBugTaskSet)
    expirable_bugtasks = list(bugtaskset.findExpirableBugTasks(
        config.malone.days_before_expiration,
        getUtility(ILaunchpadCelebrities).janitor))
    print 'ROLE  EXPIRE  AGE  STATUS  ASSIGNED  DUP  MILE  REPLIES'
    for bugtask in sorted(set(bugtasks), key=attrgetter('id')):
        if len(bugtask.bug.bugtasks) == 1:
            title = bugtask.bug.title
        else:
            title = bugtask.target.name
        print '%s  %s  %s  %s  %s  %s  %s  %s' % (
            title,
            bugtask in expirable_bugtasks,
            (datetime.now(UTC) - bugtask.bug.date_last_updated).days,
            bugtask.status.title,
            bugtask.assignee is not None,
            bugtask.bug.duplicateof is not None,
            bugtask.milestone is not None,
            bugtask.bug.messages.count() == 1)


def print_upstream_linking_form(browser):
    """Print the upstream linking form found via +choose-affected-product.

    The resulting output will look something like:
    (*) A checked option
        [A related text field]
    ( ) An unchecked option
    """
    soup = BeautifulSoup(browser.contents)

    link_upstream_how_radio_control = browser.getControl(
        name='field.link_upstream_how')
    link_upstream_how_buttons = soup.findAll(
        'input', {'name': 'field.link_upstream_how'})

    wrapper = textwrap.TextWrapper(width=65, subsequent_indent='    ')
    for button in link_upstream_how_buttons:
        # Print the radio button.
        label = button.findParent('label')
        if label is None:
            label = soup.find('label', {'for': button['id']})
        if button.get('value') in link_upstream_how_radio_control.value:
            print wrapper.fill('(*) %s' % extract_text(label))
        else:
            print wrapper.fill('( ) %s' % extract_text(label))
        # Print related text field, if found. Assumes that the text
        # field is in the same table row as the radio button.
        text_field = button.findParent('tr').find('input', {'type': 'text'})
        if text_field is not None:
            text_control = browser.getControl(name=text_field.get('name'))
            print '    [%s]' % text_control.value.ljust(10)


def print_bugfilters_portlet_unfilled(browser, target):
    """Print the raw, unfilled contents of the bugfilters portlet.

    This is the contents before any actual data has been fetched.
    (The portlet is normally populated with data by a separate
    javascript call, to avoid delaying the overall page load.  Use
    print_bugfilters_portlet_filled() to test the populated portlet.)

    :param browser  browser from which to extract the content.
    :param target   entity from whose bugs page to fetch the portlet
                    (e.g., http://bugs.launchpad.dev/TARGET/...)
    """
    browser.open(
        'http://bugs.launchpad.dev/%s/+portlet-bugfilters' % target)
    ul = BeautifulSoup(browser.contents).find('ul', 'data-list')
    print_ul(ul)


def print_bugfilters_portlet_filled(browser, target):
    """Print the filled-in contents of the bugfilters portlet.

    This is the contents after the actual data has been fetched.
    (The portlet is normally populated with data by a separate
    javascript call, to avoid delaying the overall page load.  Use
    print_bugfilters_portlet_unfilled() to test the unpopulated
    portlet.)

    :param browser  browser from which to extract the content.
    :param target   entity from whose bugs page to fetch the portlet
                    (e.g., http://bugs.launchpad.dev/TARGET/...)
    """
    browser.open(
        'http://bugs.launchpad.dev'
        '/%s/+bugtarget-portlet-bugfilters-stats' % target)
    ul = BeautifulSoup(browser.contents).find('ul', 'data-list')
    print_ul(ul)


def print_ul(ul):
    """Print the data from a list."""
    li_content = []
    for li in ul.findAll('li'):
        li_content.append(extract_text(li))
    if len(li_content) > 0:
        print '\n'.join(li_content)


def print_bug_tag_anchors(anchors):
    """The the bug tags in the iterable of anchors."""
    for anchor in anchors:
        href = anchor['href']
        if href != '+edit' and '/+help-bugs/tag-help.html' not in href:
            print anchor['class'], anchor.contents[0]
