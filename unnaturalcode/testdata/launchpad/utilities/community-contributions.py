#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Show what Launchpad community contributors have done.

Trawl a Launchpad branch's history to detect contributions by non-Canonical
developers, then update https://dev.launchpad.net/Contributions accordingly.

Usage: community-contributions.py [options] --devel=PATH --db-devel=DB_PATH

Requirements:
       You need both the 'devel' and 'db-devel' branches of Launchpad
       available locally (see https://dev.launchpad.net/Getting),
       your ~/.moin_ids file must be set up correctly, and you need
       editmoin.py (if you don't have it, the error message will tell
       you where to get it).

Options:
  -q               Print no non-essential messages.
  -h, --help       Print this help.
  --dry-run        Don't update the wiki, just print the new page to stdout.
  --draft-run      Update the wiki "/Draft" page instead of the real page.
  --devel=PATH     Specify the filesystem path to the 'devel' branch.
  --db-devel=PATH  Specify the filesystem path to the 'db-devel' branch.
"""

# General notes:
#
# The Right Way to do this would probably be to output some kind of
# XML format, and then have a separate converter script transform that
# to wiki syntax and update the wiki page.  But as the wiki is our
# only consumer right now, we just output wiki syntax and update the
# wiki page directly, premature generalization being the root of all
# evil.
#
# For understanding the code, you may find it helpful to see
# bzrlib/log.py and http://bazaar-vcs.org/Integrating_with_Bazaar.

import getopt
import re
import sys

from bzrlib import log
from bzrlib.branch import Branch
from bzrlib.osutils import format_date


try:
    from editmoin import editshortcut
except:
    sys.stderr.write("""ERROR: Unable to import from 'editmoin'. How to solve:
Get editmoin.py from launchpadlib's "contrib/" directory:

  http://bazaar.launchpad.net/~lazr-developers/launchpadlib/trunk/annotate/head%3A/contrib/editmoin.py

(Put it in the same directory as this script and everything should work.)
""")
    sys.exit(1)


def wiki_encode(x):
    """Encode a Unicode string for display on the wiki."""
    return x.encode('utf-8', 'xmlcharrefreplace')



# The output contains two classes of contributors: people who don't
# work for Canonical at all, and people who do work for Canonical but
# not on the Launchpad team.
#
# People who used to work for Canonical on the Launchpad team are not
# shown in the output, since they don't help us from a "contributions
# from outside the team" perspective, so they are listed as known
# Canonical Launchpad developers even though they aren't actually on
# the team anymore.  There may be a few former Canonicalites who
# didn't work on the Launchpad team but who still contributed to
# Launchpad; most of them would have done so before Launchpad was open
# sourced in July 2009, though, and since this script is really about
# showing things that have happened since Launchpad was open sourced,
# they may be listed as Launchpad team members anyway just to ensure
# they don't appear in the output.
#
# (As time goes on, that assumption will be less and less correct, of
# course, and eventually we may wish to do something about it.  Also,
# there are some people, e.g. Jelmer Vernooij, who made contributions
# to Launchpad before working at Canonical, but who now work on the
# Launchpad team at Canonical.  Ideally, each potentially listable
# contributor could have a set of roles, and a date range associated
# with each role... but that would be overkill for this script.  That
# last 2% of correctness would cost way too much to achieve.)
#
# XXX: Karl Fogel 2009-09-10 bug=513608: We should use launchpadlib
# to consult Launchpad itself to find out who's a Canonical developer,
# and within that who's a Launchpad developer.


# If a contributor's address contains this, then they are or were a
# Canonical developer -- maybe on the Launchpad team, maybe not.
CANONICAL_ADDR = wiki_encode(u" {_AT_} canonical.com")

# People on the Canonical Launchpad team.
known_canonical_lp_devs = \
    [wiki_encode(x) for x in (u'Aaron Bentley',
                              u'Abel Deuring',
                              u'Andrew Bennetts',
                              u'Barry Warsaw',
                              u'Benji York',
                              u'Bjorn Tillenius',
                              u'Björn Tillenius',
                              u'Brad Bollenbach',
                              u'Brad Crittenden',
                              u'Brian Fromme',
                              u'Canonical.com Patch Queue Manager',
                              u'Carlos Perello Marin',
                              u'Carlos Perelló Marín',
                              u'carlos.perello {_AT_} canonical.com',
                              u'Celso Providelo',
                              u'Christian Reis',
                              u'Christian Robottom Reis',
                              u'kiko {_AT_} beetle',
                              u'Curtis Hovey',
                              u'Dafydd Harries',
                              u'Danilo Šegan',
                              u'Danilo Segan',
                              u'david <david {_AT_} marvin>',
                              u'Данило Шеган',
                              u'данило шеган',
                              u'Daniel Silverstone',
                              u'David Allouche',
                              u'Deryck Hodge',
                              u'Diogo Matsubara',
                              u'Edwin Grubbs',
                              u'Elliot Murphy',
                              u'Firstname Lastname',
                              u'Francesco Banconi',
                              u'Francis Lacoste',
                              u'Francis J. Lacoste',
                              u'Gary Poster',
                              u'Gavin Panella',
                              u'Graham Binns',
                              u'Guilherme Salgado',
                              u'Henning Eggers',
                              u'Herb McNew',
                              u'Huw Wilkins',
                              u'Ian Booth',
                              u'James Henstridge',
                              u'j.c.sackett',
                              u'jc',
                              u'Jelmer Vernooij',
                              u'Jeroen Vermeulen',
                              u'Jeroen T. Vermeulen',
                              u'Joey Stanford',
                              u'Jon Sackett',
                              u'Jonathan Lange',
                              u'j.c.sackett',
                              u'jonathan.sackett {_AT_} canonical.com',
                              u'jml {_AT_} canonical.com',
                              u'jml {_AT_} mumak.net',
                              u'Jonathan Knowles',
                              u'jonathan.knowles {_AT_} canonical.com',
                              u'Julian Edwards',
                              u'Karl Fogel',
                              u'Launch Pad',
                              u'Launchpad APA',
                              u'Launchpad Developers',
                              u'Launchpad Patch Queue Manager',
                              u'Launchpad PQM Bot',
                              u'Leonard Richardson',
                              u'Malcolm Cleaton',
                              u'Maris Fogels',
                              u'Mark Shuttleworth',
                              u'Martin Albisetti',
                              u'Matt Zimmerman',
                              u'Matthew Paul Thomas',
                              u'Matthew Thomas',
                              u'Matthew Revell',
                              u'matthew.revell {_AT_} canonical.com',
                              u'Michael Hudson',
                              u'michael.hudson {_AT_} canonical.com',
                              u'Michael Nelson',
                              u'Muharem Hrnjadovic',
                              u'muharem {_AT_} canonical.com',
                              u'Patch Queue Manager',
                              u'Paul Hummer',
                              u'Raphael Badin',
                              u'Raphaël Badin',
                              u'Richard Harding',
                              u'Rick Harding',
                              u'Rick harding',
                              u'Robert Collins',
                              u'root <root {_AT_} ubuntu>',
                              u'rvb',
                              u'Stuart Bishop',
                              u'Steve Alexander',
                              u'Steve Kowalik',
                              u'Steve McInerney',
                              u'<steve {_AT_} stedee.id.au>',
                              u'test {_AT_} canonical.com',
                              u'Tom Haddon',
                              u'Tim Penhey',
                              u'Tom Berger',
                              u'ubuntu <ubuntu {_AT_} lp-dev>',
                              u'Ursula Junque',
                              u'William Grant <william.grant {_AT_} canonical.com>',
                              )]

# People known to work for Canonical but not on the Launchpad team.
# Anyone with "@canonical.com" in their email address is considered to
# work for Canonical, but some people occasionally submit changes from
# their personal email addresses; this list contains people known to
# do that, so we can treat them appropriately in the output.
known_canonical_non_lp_devs = \
    [wiki_encode(x) for x in (u'Adam Conrad',
                              u'Andrew Bennetts',
                              u'Anthony Lenton',
                              u'Cody Somerville',
                              u'Cody A.W. Somerville',
                              u'David Murphy',
                              u'Didier Roche',
                              u'Elliot Murphy',
                              u'Gabriel Neuman gneuman {_AT_} async.com',
                              u'Gustavo Niemeyer',
                              u'James Henstridge',
                              u'James Westby',
                              u'John Lenton',
                              u'Kees Cook',
                              u'LaMont Jones',
                              u'Loïc Minier',
                              u'Martin Pitt',
                              u'Martin Pool',
                              u'Matt Zimmerman',
                              u'mbp {_AT_} sourcefrog.net',
                              u'Michael Casadevall',
                              u'Michael Vogt',
                              u'Sidnei da Silva',
                              u'Steve Langasek',
                              u'Dustin Kirkland',
                              u'John Arbash Meinel',
                              )]

# Some people have made commits using various names and/or email
# addresses, so this map will be used to merge them accordingly.
# The map is initialized from this list of pairs, where each pair is
# of the form (CONTRIBUTOR_AS_SEEN, UNIFYING_IDENTITY_FOR_CONTRIBUTOR).
merge_names_pairs = (
    (u'Jamal Fanaian <jfanaian {_AT_} gmail.com>',
     u'Jamal Fanaian <jamal.fanaian {_AT_} gmail.com>'),
    (u'Jamal Fanaian <jamal {_AT_} jfvm1>',
     u'Jamal Fanaian <jamal.fanaian {_AT_} gmail.com>'),
    (u'LaMont Jones <lamont {_AT_} rover3>',
     u'LaMont Jones <lamont {_AT_} debian.org>'),
    (u'Sidnei <sidnei {_AT_} ubuntu>',
     u'Sidnei da Silva <sidnei.da.silva {_AT_} canonical.com>'),
    (u'Sidnei da Silva <sidnei.da.silva {_AT_} gmail.com>',
     u'Sidnei da Silva <sidnei.da.silva {_AT_} canonical.com>'),
    (u'Sidnei da Silva <sidnei {_AT_} canonical.com>',
     u'Sidnei da Silva <sidnei.da.silva {_AT_} canonical.com>'),
    (u'Adam Conrad <adconrad {_AT_} ziggup>',
     u'Adam Conrad <adconrad {_AT_} 0c3.net>'),
    (u'Elliot Murphy <elliot {_AT_} elliotmurphy.com>',
     u'Elliot Murphy <elliot {_AT_} canonical.com>'),
    (u'Elliot Murphy <elliot.murphy {_AT_} canonical.com>',
     u'Elliot Murphy <elliot {_AT_} canonical.com>'),
    (u'Cody Somerville <cody-somerville {_AT_} mercurial>',
     u'Cody A.W. Somerville <cody.somerville {_AT_} canonical.com>'),
    (u'Adam Conrad <adconrad {_AT_} chinstrap>',
     u'Adam Conrad <adconrad {_AT_} 0c3.net>'),
    (u'Adam Conrad <adconrad {_AT_} cthulhu>',
     u'Adam Conrad <adconrad {_AT_} 0c3.net>'),
    (u'James Westby <james.westby {_AT_} linaro.org>',
     u'James Westby <james.westby {_AT_} canonical.com>'),
    (u'Bryce Harrington <bryce {_AT_} canonical.com>',
     u'Bryce Harrington <bryce.harrington {_AT_} canonical.com>'),
    (u'Dustin Kirkland <kirkland {_AT_} x200>',
     u'Dustin Kirkland <kirkland {_AT_} canonical.com>'),
    (u'Anthony Lenton <antoniolenton {_AT_} gmail.com>',
     u'Anthony Lenton <anthony.lenton {_AT_} canonical.com>'),
    (u'Steve Kowalik <steven {_AT_} quelled>',
     u'Steve Kowalik <steve.kowalik {_AT_} canonical.com>'),
    (u'Steve Kowalik <stevenk {_AT_} ubuntu.com>',
     u'Steve Kowalik <steve.kowalik {_AT_} canonical.com>'),
    (u'jc <jc {_AT_} launchpad>',
     u'j.c.sackett <jonathan.sackett {_AT_} canonical.com>'),
    (u'Jon Sackett <jc {_AT_} jabberwocky>',
     u'j.c.sackett <jonathan.sackett {_AT_} canonical.com>'),
    (u'John Arbash Meinel <jameinel {_AT_} falco-lucid>',
     u'John Arbash Meinel <john {_AT_} arbash-meinel.com>'),
    (u'Martin Pool <mbp {_AT_} sourcefrog.net>',
     u'Martin Pool <mbp {_AT_} canonical.com>'),
    (u'mbp {_AT_} sourcefrog.net',
     u'Martin Pool <mbp {_AT_} canonical.com>'),
    (u'mbp {_AT_} canonical.com',
     u'Martin Pool <mbp {_AT_} canonical.com>'),
    (u'Andrea Corbellini <corbellini.andrea {_AT_} gmail.com>',
     u'Andrea Corbellini <andrea.corbellini {_AT_} beeseek.org>'),
    (u'Luke Faraone <luke {_AT_} faraone.cc',
     u'Luke Faraone <luke {_AT_} faraone.cc>'),
    )
# Then put it in dictionary form with the correct encodings.
merge_names_map = dict((wiki_encode(a), wiki_encode(b))
                       for a, b in merge_names_pairs)


class ContainerRevision():
    """A wrapper for a top-level LogRevision containing child LogRevisions."""

    def __init__(self, top_lr, branch_info):
        """Create a new ContainerRevision.

        :param top_lr: The top-level LogRevision.
        :param branch_info: The BranchInfo for the containing branch.
        """
        self.top_rev = top_lr       # e.g. LogRevision for r9371.
        self.contained_revs = []    # e.g. [ {9369.1.1}, {9206.4.4}, ... ],
                                    # where "{X}" means "LogRevision for X"
        self.branch_info = branch_info

    def add_subrev(self, lr):
        """Add a descendant child of this container revision."""
        self.contained_revs.append(lr)

    def __str__(self):
        timestamp = self.top_rev.rev.timestamp
        timezone = self.top_rev.rev.timezone
        message = self.top_rev.rev.message or "(NO LOG MESSAGE)"
        rev_id = self.top_rev.rev.revision_id or "(NO REVISION ID)"
        if timestamp:
            date_str = format_date(timestamp, timezone or 0, 'original')
        else:
            date_str = "(NO DATE)"

        rev_url_base = "http://bazaar.launchpad.net/%s/revision/" % (
            self.branch_info.loggerhead_path)

        # In loggerhead, you can use either a revision number or a
        # revision ID.  In other words, these would reach the same page:
        #
        # http://bazaar.launchpad.net/~launchpad-pqm/launchpad/devel/\
        # revision/9202
        #
        #   -and-
        #
        # http://bazaar.launchpad.net/~launchpad-pqm/launchpad/devel/\
        # revision/launchpad@pqm.canonical.com-20090821221206-\
        # ritpv21q8w61gbpt
        #
        # In our links, even when the link text is a revnum, we still
        # use a rev-id for the target.  This is both so that the URL will
        # still work if you manually tweak it (say to "db-devel" from
        # "devel") and so that hovering over a revnum on the wiki page
        # will give you some information about it before you click
        # (because a rev id often identifies the committer).
        rev_id_url = rev_url_base + rev_id

        if len(self.contained_revs) <= 10:
            commits_block = "\n ".join(
                ["[[%s|%s]]" % (rev_url_base + lr.rev.revision_id, lr.revno)
                 for lr in self.contained_revs])
        else:
            commits_block = ("''see the [[%s|full revision]] for details "
                             "(it contains %d commits)''"
                             % (rev_id_url, len(self.contained_revs)))

        name = self.branch_info.name

        text = [
            " * [[%s|r%s%s]] -- %s\n" % (
                rev_id_url, self.top_rev.revno,
                ' (%s)' % name.encode('utf-8') if name else '',
                date_str),
            " {{{\n%s\n}}}\n" % message.encode('utf-8'),
            " '''Commits:'''\n ",
            commits_block,
            "\n",
            ]
        return ''.join(text)


# "ExternalContributor" is too much to type, so I guess we'll just use this.
class ExCon():
    """A contributor to Launchpad from outside Canonical's Launchpad team."""

    def __init__(self, name, is_canonical=False):
        """Create a new external contributor named 'name'.

        If 'is_canonical' is True, then this is a contributor from
        within Canonical, but not on the Launchpad team at Canonical.
        'name' is something like "Veronica Random <vr {_AT_} example.com>".
        """
        self.name = name
        self.is_canonical = is_canonical
        # If name is "Veronica Random <veronica {_AT_} example.com>",
        # then name_as_anchor will be "veronica_random".
        self.name_as_anchor = \
            re.compile("\\s+").sub("_", name.split("<")[0].strip()).lower()
        # All the top-level revisions this contributor is associated with
        # (key == value == ContainerRevision).  We use a dictionary
        # instead of list to get set semantics; set() would be overkill.
        self._landings = {}
        # A map of revision IDs authored by this contributor (probably
        # not top-level) to a (LogRevision, ContainerRevision) pair. The
        # pair contains details of the shallowest found instance of this
        # revision.
        self.seen_revs = {}

    def num_landings(self):
        """Return the number of top-level landings that include revisions
        by this contributor."""
        return len(self._landings)

    def add_top_level_revision(self, cr):
        "Record ContainableRevision CR as associated with this contributor."
        self._landings[cr] = cr

    def show_contributions(self):
        "Return a wikified string showing this contributor's contributions."
        plural = "s"
        name = self.name
        if self.is_canonical:
            name = name + " (Canonical developer)"
        if self.num_landings() == 1:
            plural = ""
        text = [
            "=== %s ===\n\n" % name,
            "''%d top-level landing%s:''\n\n" % (self.num_landings(), plural),
            ''.join(map(str, sorted(self._landings,
                                    key=lambda x: x.top_rev.rev.timestamp,
                                    reverse=True))),
            "\n",
            ]
        return ''.join(text)


def get_ex_cons(authors, all_ex_cons):
    """Return a list of ExCon objects corresponding to AUTHORS (a list
    of strings).  If there are no external contributors in authors,
    return an empty list.

    ALL_EX_CONS is a dictionary mapping author names (as received from
    the bzr logs, i.e., with email address undisguised) to ExCon objects.
    """
    ex_cons_this_rev = []
    for author in authors:
        known_canonical_lp_dev = False
        known_canonical_non_lp_dev = False
        # The authors we list in the source code have their addresses
        # disguised (since this source code is public).  We must
        # disguise the ones coming from the Bazaar logs in the same way,
        # so string matches will work.
        author = wiki_encode(author)
        author = author.replace("@", " {_AT_} ")

        # If someone works/worked for Canonical on the Launchpad team,
        # then skip them -- we don't want to show them in the output.
        for name_fragment in known_canonical_lp_devs:
            if name_fragment in author:
                known_canonical_lp_dev = True
                break
        if known_canonical_lp_dev:
            continue

        # Use the merge names map to merge contributions from the same
        # person using alternate names and/or emails.
        author = merge_names_map.get(author, author)

        if CANONICAL_ADDR in author:
            known_canonical_non_lp_dev = True
        else:
            for name_fragment in known_canonical_non_lp_devs:
                if name_fragment in author:
                    known_canonical_non_lp_dev = True
                    break

        # There's a variant of the Singleton pattern that could be
        # used for this, whereby instantiating an ExCon object would
        # just get back an existing object if such has already been
        # instantiated for this name.  But that would make this code
        # non-reentrant, and that's just not cool.
        ec = all_ex_cons.get(author, None)
        if ec is None:
            ec = ExCon(author, is_canonical=known_canonical_non_lp_dev)
            all_ex_cons[author] = ec
        ex_cons_this_rev.append(ec)
    return ex_cons_this_rev


# The LogFormatter abstract class should really be called LogReceiver
# or something -- subclasses don't have to be about display.
class LogExCons(log.LogFormatter):
    """Log all the external contributions, by Contributor."""

    # See log.LogFormatter documentation.
    supports_merge_revisions = True

    def __init__(self):
        super(LogExCons, self).__init__(to_file=None)
        # Dictionary mapping author names (with undisguised email
        # addresses) to ExCon objects.
        self.all_ex_cons = {}
        # ContainerRevision object representing most-recently-seen
        # top-level rev.
        self.current_top_level_rev = None
        self.branch_info = None

    def _toc(self, contributors):
        toc_text = []
        for val in contributors:
            plural = "s"
            if val.num_landings() == 1:
                plural = ""
            toc_text.extend(" 1. [[#%s|%s]] ''(%d top-level landing%s)''\n"
                            % (val.name_as_anchor, val.name,
                               val.num_landings(), plural))
        return toc_text

    def result(self):
        "Return a moin-wiki-syntax string with TOC followed by contributions."

        # Go through the shallowest authored revisions and add their
        # top level revisions.
        for excon in self.all_ex_cons.values():
            for rev, top_level_rev in excon.seen_revs.values():
                excon.add_top_level_revision(top_level_rev)

        # Divide contributors into non-Canonical and Canonical.
        non_canonical_contributors = [x for x in self.all_ex_cons.values()
                                      if not x.is_canonical]
        canonical_contributors = [x for x in self.all_ex_cons.values()
                                      if x.is_canonical]
        # Sort them.
        non_canonical_contributors = sorted(non_canonical_contributors,
                                            key=lambda x: x.num_landings(),
                                            reverse=True)
        canonical_contributors = sorted(canonical_contributors,
                                        key=lambda x: x.num_landings(),
                                        reverse=True)

        text = [
            "-----\n\n",
            "= Who =\n\n"
            "== Contributors (from outside Canonical) ==\n\n",
            ]
        text.extend(self._toc(non_canonical_contributors))
        text.extend([
            "== Contributors (from Canonical, but outside "
            "the Launchpad team) ==\n\n",
            ])
        text.extend(self._toc(canonical_contributors))
        text.extend(["\n-----\n\n",
                     "= What =\n\n",
                     "== Contributions (from outside Canonical) ==\n\n",
                     ])
        for val in non_canonical_contributors:
            text.extend("<<Anchor(%s)>>\n" % val.name_as_anchor)
            text.extend(val.show_contributions())
        text.extend(["== Contributions (from Canonical, but outside "
                     "the Launchpad team) ==\n\n",
                     ])
        for val in canonical_contributors:
            text.extend("<<Anchor(%s)>>\n" % val.name_as_anchor)
            text.extend(val.show_contributions())
        return ''.join(text)

    def log_revision(self, lr):
        """Log a revision.
        :param  lr:   The LogRevision to be logged.
        """
        # We count on always seeing the containing rev before its subrevs.
        if lr.merge_depth == 0:
            self.current_top_level_rev = ContainerRevision(
                lr, self.branch_info)
        else:
            self.current_top_level_rev.add_subrev(lr)
        ex_cons = get_ex_cons(lr.rev.get_apparent_authors(), self.all_ex_cons)
        for ec in ex_cons:
            # If this is the shallowest sighting of a revision, note it
            # in the ExCon. We may see the revision at different depths
            # in different branches, mostly when one of the trunks is
            # merged into the other. We only care about the initial
            # merge, which should be shallowest.
            if (lr.rev.revision_id not in ec.seen_revs or
                lr.merge_depth <
                    ec.seen_revs[lr.rev.revision_id][0].merge_depth):
                ec.seen_revs[lr.rev.revision_id] = (
                    lr, self.current_top_level_rev)


class BranchInfo:
    """A collection of information about a branch."""

    def __init__(self, path, loggerhead_path, name=None):
        """Create a new BranchInfo.

        :param path: Filesystem path to the branch.
        :param loggerhead_path: The path to the branch on Launchpad's
            Loggerhead instance.
        :param name: Optional name to identify the branch's revisions in the
            produced document.
        """
        self.path = path
        self.name = name
        self.loggerhead_path = loggerhead_path


# XXX: Karl Fogel 2009-09-10: is this really necessary?  See bzrlib/log.py.
log.log_formatter_registry.register('external_contributors', LogExCons,
                                    'Find non-Canonical contributors.')


def usage():
    print __doc__


# Use backslashes to suppress newlines because this is wiki syntax,
# not HTML, so newlines would be rendered as line breaks.
page_intro = """This page shows contributions to Launchpad from \
developers not on the Launchpad team at Canonical.

It lists all changes that have landed in the Launchpad ''devel'' \
or ''db-devel'' trees (see the [[Trunk|trunk explanation]] for more).

~-''Note for maintainers: this page is updated every hour by a \
cron job running as wgrant on devpad (though if there are no new \
contributions, the page's timestamp won't change).  The code that \
generates this page is \
[[http://bazaar.launchpad.net/%7Elaunchpad-pqm/launchpad/devel/annotate/head%3A/utilities/community-contributions.py|utilities/community-contributions.py]] \
in the Launchpad tree.''-~

"""

def main():
    quiet = False
    dry_run = False
    devel_path = None
    db_devel_path = None

    wiki_dest = "https://dev.launchpad.net/Contributions"

    if len(sys.argv) < 3:
        usage()
        sys.exit(1)

    try:
        opts, args = getopt.getopt(sys.argv[1:], '?hq',
                                   ['help', 'usage', 'dry-run', 'draft-run',
                                    'devel=', 'db-devel='])
    except getopt.GetoptError as e:
        sys.stderr.write("ERROR: " + str(e) + '\n\n')
        usage()
        sys.exit(1)

    for opt, value in opts:
        if opt == '--help' or opt == '-h' or opt == '-?' or opt == 'usage':
            usage()
            sys.exit(0)
        elif opt == '-q' or opt == '--quiet':
            quiet = True
        elif opt == '--dry-run':
            dry_run = True
        elif opt == '--draft-run':
            wiki_dest += "/Draft"
        elif opt == '--devel':
            devel_path = value
        elif opt == '--db-devel':
            db_devel_path = value

    # Ensure we have the arguments we need.
    if not devel_path or not db_devel_path:
        sys.stderr.write("ERROR: paths to Launchpad devel and db-devel "
                         "branches required as options\n")
        usage()
        sys.exit(1)

    branches = (
        BranchInfo(
            devel_path, '~launchpad-pqm/launchpad/devel'),
        BranchInfo(
            db_devel_path, '~launchpad-pqm/launchpad/db-devel', 'db-devel'),
        )

    lec = LogExCons()

    for branch_info in branches:
        # Do everything.
        b = Branch.open(branch_info.path)

        logger = log.Logger(b, {'direction' : 'reverse',
                                'levels' : 0, })
        if not quiet:
            print "Calculating (this may take a while)..."

        # Set information about the current branch for later formatting.
        lec.branch_info = branch_info
        logger.show(lec)  # Won't "show" anything -- just gathers data.

    page_contents = page_intro + lec.result()
    def update_if_modified(moinfile):
        if moinfile._unescape(moinfile.body) == page_contents:
            return 0  # Nothing changed, so cancel the edit.
        else:
            moinfile.body = page_contents
            return 1
    if not dry_run:
        if not quiet:
            print "Updating wiki..."
        # Not sure how to get editmoin to obey our quiet flag.
        editshortcut(wiki_dest, editfile_func=update_if_modified)
        if not quiet:
            print "Done updating wiki."
    else:
        print page_contents


if __name__ == '__main__':
    main()
