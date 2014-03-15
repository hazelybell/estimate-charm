# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""TALES formatter for strings."""

__metaclass__ = type
__all__ = [
    'add_word_breaks',
    'break_long_words',
    'extract_bug_numbers',
    'extract_email_addresses',
    'FormattersAPI',
    'linkify_bug_numbers',
    're_substitute',
    'split_paragraphs',
    ]

from base64 import urlsafe_b64encode
import re

from lxml import html
import markdown
from zope.component import getUtility
from zope.interface import implements
from zope.traversing.interfaces import (
    ITraversable,
    TraversalError,
    )

from lp.answers.interfaces.faq import IFAQSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.config import config
from lp.services.features import getFeatureFlag
from lp.services.utils import (
    obfuscate_email,
    re_email_address,
    )
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import (
    html_escape,
    html_unescape,
    structured,
    )
from lp.services.webapp.interfaces import ILaunchBag


def split_paragraphs(text):
    """Split text into paragraphs.

    This function yields lists of strings that represent lines of text
    in each paragraph.

    Paragraphs are split by one or more blank lines.
    """
    paragraph = []
    for line in text.splitlines():
        line = line.rstrip()

        # blank lines split paragraphs
        if not line:
            if paragraph:
                yield paragraph
            paragraph = []
            continue

        paragraph.append(line)

    if paragraph:
        yield paragraph


def re_substitute(pattern, replace_match, replace_nomatch, string):
    """Transform a string, replacing matched and non-matched sections.

     :param patter: a regular expression
     :param replace_match: a function used to transform matches
     :param replace_nomatch: a function used to transform non-matched text
     :param string: the string to transform

    This function behaves similarly to re.sub() when a function is
    passed as the second argument, except that the non-matching
    portions of the string can be transformed by a second function.
    """
    if replace_match is None:
        replace_match = lambda match: match.group()
    if replace_nomatch is None:
        replace_nomatch = lambda text: text
    parts = []
    position = 0
    for match in re.finditer(pattern, string):
        if match.start() != position:
            parts.append(replace_nomatch(string[position:match.start()]))
        parts.append(replace_match(match))
        position = match.end()
    remainder = string[position:]
    if remainder:
        parts.append(replace_nomatch(remainder))
    return ''.join(parts)


def next_word_chunk(word, pos, minlen, maxlen):
    """Return the next chunk of the word of length between minlen and maxlen.

    Shorter word chunks are preferred, preferably ending in a non
    alphanumeric character.  The index of the end of the chunk is also
    returned.

    This function treats HTML entities in the string as single
    characters.  The string should not include HTML tags.
    """
    nchars = 0
    endpos = pos
    while endpos < len(word):
        # advance by one character
        if word[endpos] == '&':
            # make sure we grab the entity as a whole
            semicolon = word.find(';', endpos)
            assert semicolon >= 0, 'badly formed entity: %r' % word[endpos:]
            endpos = semicolon + 1
        else:
            endpos += 1
        nchars += 1
        if nchars >= maxlen:
            # stop if we've reached the maximum chunk size
            break
        if nchars >= minlen and not word[endpos - 1].isalnum():
            # stop if we've reached the minimum chunk size and the last
            # character wasn't alphanumeric.
            break
    return word[pos:endpos], endpos


def add_word_breaks(word):
    """Insert manual word breaks into a string.

    The word may be entity escaped, but is not expected to contain
    any HTML tags.

    Breaks are inserted at least every 7 to 15 characters,
    preferably after puctuation.
    """
    broken = []
    pos = 0
    while pos < len(word):
        chunk, pos = next_word_chunk(word, pos, 7, 15)
        broken.append(chunk)
    return '<wbr />'.join(broken)


break_text_pat = re.compile(r'''
  (?P<tag>
    <[^>]*>
  ) |
  (?P<longword>
    (?<![^\s<>])(?:[^\s<>&]|&[^;]*;){20,}
  )
''', re.VERBOSE)


def break_long_words(text):
    """Add word breaks to long words in a run of text.

    The text may contain entity references or HTML tags.
    """

    def replace(match):
        if match.group('tag'):
            return match.group()
        elif match.group('longword'):
            return add_word_breaks(match.group())
        else:
            raise AssertionError('text matched but neither named group found')
    return break_text_pat.sub(replace, text)


def extract_bug_numbers(text):
    '''Unique bug numbers matching the "LP: #n(, #n)*" pattern in the text.'''
    # FormattersAPI._linkify_substitution requires a match object
    # that has named groups "bug" and "bugnum".  The matching text for
    # the "bug" group is used as the link text and "bugnum" forms part
    # of the URL for the link to the bug. Example:
    #   >>> bm.groupdict( )
    #   {'bugnum': '400686', 'bug': '#400686'}

    # We need to match bug numbers of the form:
    # LP: #1, #2, #3
    #  #4, #5
    # over multiple lines.
    #
    # Writing a single catch-all regex for this has proved rather hard
    # so I am taking the strategy of matching  LP:(group) first, and
    # feeding the result into another regex to pull out the bug and
    # bugnum groups.
    unique_bug_matches = dict()

    line_matches = re.finditer(
        'LP:\s*(?P<buglist>(.+?[^,]))($|\n)', text,
        re.DOTALL | re.IGNORECASE)

    for line_match in line_matches:
        bug_matches = re.finditer(
            '\s*((?P<bug>#(?P<bugnum>\d+)),?\s*)',
            line_match.group('buglist'))

        for bug_match in bug_matches:
            bugnum = bug_match.group('bugnum')
            if bugnum in unique_bug_matches:
                # We got this bug already, ignore it.
                continue
            unique_bug_matches[bugnum] = bug_match

    return unique_bug_matches


def linkify_bug_numbers(text):
    """Linkify to a bug if LP: #number appears in the (changelog) text."""
    unique_bug_matches = extract_bug_numbers(text)
    for bug_match in unique_bug_matches.values():
        replace_text = bug_match.group('bug')
        if replace_text is not None:
            # XXX julian 2008-01-10
            # Note that re.sub would be far more efficient to use
            # instead of string.replace() but this requires a regex
            # that matches everything in one go.  We're also at danger
            # of replacing the wrong thing if string.replace() finds
            # other matching substrings.  So for example in the
            # string:
            # "LP: #9, #999"
            # replacing #9 with some HTML would also interfere with
            # #999.  The liklihood of this happening is very, very
            # small, however.
            text = text.replace(
                replace_text,
                FormattersAPI._linkify_substitution(bug_match))
    return text


def extract_email_addresses(text):
    '''Unique email addresses in the text.'''
    matches = re.finditer(re_email_address, text)
    return list(set([match.group() for match in matches]))


class FormattersAPI:
    """Adapter from strings to HTML formatted text."""

    implements(ITraversable)

    def __init__(self, stringtoformat):
        self._stringtoformat = stringtoformat

    def nl_to_br(self):
        """Quote HTML characters, then replace newlines with <br /> tags."""
        return html_escape(self._stringtoformat).replace('\n', '<br />\n')

    def escape(self):
        return html_escape(self._stringtoformat)

    def break_long_words(self):
        """Add manual word breaks to long words."""
        return break_long_words(html_escape(self._stringtoformat))

    @staticmethod
    def _substitute_matchgroup_for_spaces(match):
        """Return a string made up of '&nbsp;' for each character in the
        first match group.

        Used when replacing leading spaces with nbsps.

        There must be only one match group.
        """
        groups = match.groups()
        assert len(groups) == 1
        return '&nbsp;' * len(groups[0])

    @staticmethod
    def _linkify_bug_number(text, bugnum, trailers=''):
        # Don't look up the bug or display anything about the bug, just
        # linkify to the general bug url.
        url = '/bugs/%s' % bugnum
        # The text will have already been cgi escaped.
        return '<a href="%s" class="bug-link">%s</a>%s' % (
            url, text, trailers)

    @staticmethod
    def _handle_parens_in_trailers(url, trailers):
        """Move closing parens from the trailer back into the url if needed.

        If there are opening parens in the url that are matched by closing
        parens at the start of the trailer, those closing parens should be
        part of the url."""
        assert trailers != '', ("Trailers must not be an empty string.")
        opencount = url.count('(')
        closedcount = url.count(')')
        missing = opencount - closedcount
        slice_idx = 0
        while slice_idx < missing:
            if trailers[slice_idx] == ')':
                slice_idx += 1
            else:
                break
        url += trailers[:slice_idx]
        trailers = trailers[slice_idx:]
        return url, trailers

    @staticmethod
    def _split_url_and_trailers(url):
        """Given a URL return a tuple of the URL and punctuation trailers.

        :return: an unescaped url, an unescaped trailer.
        """
        match = FormattersAPI._re_url_trailers.search(url)
        if match:
            trailers = match.group(1)
            url = url[:-len(trailers)]
            return FormattersAPI._handle_parens_in_trailers(url, trailers)
        else:
            # No match, return URL with empty string for trailers
            return url, ''

    @staticmethod
    def _linkify_url_should_be_ignored(url):
        """Don't linkify URIs consisting of just the protocol."""

        protocol_bases = [
            'about',
            'gopher',
            'http',
            'https',
            'sftp',
            'news',
            'ftp',
            'mailto',
            'irc',
            'jabber',
            'apt',
            ]

        for base in protocol_bases:
            if url in ('%s' % base, '%s:' % base, '%s://' % base):
                return True
        return False

    @staticmethod
    def _linkify_substitution(match):
        if match.group('bug') is not None:
            return FormattersAPI._linkify_bug_number(
                match.group('bug'), match.group('bugnum'))
        elif match.group('url') is not None:
            # The text will already have been cgi escaped.  We temporarily
            # unescape it so that we can strip common trailing characters
            # that aren't part of the URL.
            full_url = match.group('url')
            url, trailers = FormattersAPI._split_url_and_trailers(
                html_unescape(full_url))
            # We use nofollow for these links to reduce the value of
            # adding spam URLs to our comments; it's a way of moderately
            # devaluing the return on effort for spammers that consider
            # using Launchpad.
            # The use of structured() in the argument here is a bit
            # evil. Ideally add_word_breaks would return one itself.
            if not FormattersAPI._linkify_url_should_be_ignored(url):
                return structured(
                    '<a rel="nofollow" '
                    'href="%(url)s">%(linked_text)s</a>%(trailers)s',
                    url=url,
                    linked_text=structured(add_word_breaks(html_escape(url))),
                    trailers=trailers).escapedtext
            else:
                return full_url
        elif match.group('faq') is not None:
            # This is *BAD*.  We shouldn't be doing database lookups to
            # linkify text.
            text = match.group('faq')
            faqnum = match.group('faqnum')
            faqset = getUtility(IFAQSet)
            faq = faqset.getFAQ(faqnum)
            if not faq:
                return text
            url = canonical_url(faq)
            return '<a href="%s">%s</a>' % (url, text)
        elif match.group('oops') is not None:
            text = match.group('oops')

            if not getUtility(ILaunchBag).developer:
                return text

            root_url = config.launchpad.oops_root_url
            url = root_url + "OOPS-" + match.group('oopscode')
            return '<a href="%s">%s</a>' % (url, text)
        elif match.group('lpbranchurl') is not None:
            lp_url = match.group('lpbranchurl')
            path = match.group('branch')
            lp_url, trailers = FormattersAPI._split_url_and_trailers(
                html_unescape(lp_url))
            path, trailers = FormattersAPI._split_url_and_trailers(
                html_unescape(path))
            if path.isdigit():
                return FormattersAPI._linkify_bug_number(
                    lp_url, path, trailers)
            url = '/+branch/%s' % path
            # Mark the links with a 'branch-short-link' class so they can be
            # harvested and validated when the page is rendered.
            return structured(
                '<a href="%s" class="branch-short-link">%s</a>%s',
                url, lp_url, trailers).escapedtext
        elif match.group("clbug") is not None:
            # 'clbug' matches Ubuntu changelog format bugs. 'bugnumbers' is
            # all of the bug numbers, that look something like "#1234, #434".
            # 'leader' is the 'LP: ' bit at the beginning.
            bug_parts = []
            # Split the bug numbers into multiple bugs.
            splitted = re.split("(,(?:\s|<br\s*/>)+)",
                    match.group("bugnumbers")) + [""]
            for bug_id, spacer in zip(splitted[::2], splitted[1::2]):
                bug_parts.append(FormattersAPI._linkify_bug_number(
                    bug_id, bug_id.lstrip("#")))
                bug_parts.append(spacer)
            return match.group("leader") + "".join(bug_parts)
        else:
            raise AssertionError("Unknown pattern matched.")

    @staticmethod
    def _linkify_substitution_with_target(match):
        """See `_linkify_substitution`().

        The target attribute of the links will be updated to point to
        "_new", so that links will open in a new window.
        """
        linkified_text = FormattersAPI._linkify_substitution(match)
        element_tree = html.fromstring(linkified_text)
        for link in element_tree.xpath('//a'):
            link.set('target', '_new')
        return html.tostring(element_tree)

    # match whitespace at the beginning of a line
    _re_leadingspace = re.compile(r'^(\s+)')

    # From RFC 3986 ABNF for URIs:
    #
    #   URI           = scheme ":" hier-part [ "?" query ] [ "#" fragment ]
    #   hier-part     = "//" authority path-abempty
    #                 / path-absolute
    #                 / path-rootless
    #                 / path-empty
    #
    #   authority     = [ userinfo "@" ] host [ ":" port ]
    #   userinfo      = *( unreserved / pct-encoded / sub-delims / ":" )
    #   host          = IP-literal / IPv4address / reg-name
    #   reg-name      = *( unreserved / pct-encoded / sub-delims )
    #   port          = *DIGIT
    #
    #   path-abempty  = *( "/" segment )
    #   path-absolute = "/" [ segment-nz *( "/" segment ) ]
    #   path-rootless = segment-nz *( "/" segment )
    #   path-empty    = 0<pchar>
    #
    #   segment       = *pchar
    #   segment-nz    = 1*pchar
    #   pchar         = unreserved / pct-encoded / sub-delims / ":" / "@"
    #
    #   query         = *( pchar / "/" / "?" )
    #   fragment      = *( pchar / "/" / "?" )
    #
    #   unreserved    = ALPHA / DIGIT / "-" / "." / "_" / "~"
    #   pct-encoded   = "%" HEXDIG HEXDIG
    #   sub-delims    = "!" / "$" / "&" / "'" / "(" / ")"
    #                 / "*" / "+" / "," / ";" / "="
    #
    # We only match a set of known scheme names too.  We don't handle
    # IP-literal either.
    #
    # We will simplify "unreserved / pct-encoded / sub-delims" as the
    # following regular expression:
    #   [-a-zA-Z0-9._~%!$&'()*+,;=]
    # But we are working on text that has already been through
    # html_escape, so the & and ' are &amp; and &#x27; respectively. It
    # gets a bit more complicated.
    #
    # We also require that the path-rootless form not begin with a
    # colon to avoid matching strings like "http::foo" (to avoid bug
    # #40255).
    #
    # The path-empty pattern is not matched either, due to false
    # positives.
    #
    # Some allowed URI punctuation characters will be trimmed if they
    # appear at the end of the URI since they may be incidental in the
    # flow of the text.
    #
    # apport has at one time produced query strings containing sqaure
    # braces (that are not percent-encoded). In RFC 2986 they seem to be
    # allowed by section 2.2 "Reserved Characters", yet section 3.4
    # "Query" appears to provide a strict definition of the query string
    # that would forbid square braces. Either way, links with
    # non-percent-encoded square braces are being used on Launchpad so
    # it's probably best to accomodate them.

    # Match urls or bugs or oopses.
    _re_linkify = re.compile(r'''
      (?P<url>
        \b
        (?:about|gopher|http|https|sftp|news|ftp|mailto|irc|jabber|apt)
        :
        (?:
          (?:
            # "//" authority path-abempty
            //
            (?: # userinfo
              (?:%(unreserved)s|:)*
              @
            )?
            (?: # host
              \d+\.\d+\.\d+\.\d+ |
              %(unreserved)s*
            )
            (?: # port
              : \d*
            )?
            (?: / (?:%(unreserved)s|[:@])* )*
          ) | (?:
            # path-absolute
            /
            (?: (?:%(unreserved)s|[:@])+
                (?: / (?:%(unreserved)s|[:@])* )* )?
          ) | (?:
            # path-rootless
            (?:%(unreserved)s|@)
            (?:%(unreserved)s|[:@])*
            (?: / (?:%(unreserved)s|[:@])* )*
          )
        )
        (?: # query
          \?
          (?:%(unreserved)s|[:@/\?\[\]])*
        )?
        (?: # fragment
          \#
          (?:%(unreserved)s|[:@/\?])*
        )?
      ) |
      (?P<clbug>
        \b(?P<leader>lp:(\s|<br\s*/>)+)
        (?P<bugnumbers>\#\d+(,(\s|<br\s*/>)+\#\d+)*
         )
      ) |
      (?P<bug>
        \bbug(?:[\s=-]|<br\s*/>)*
            (?:(?:(?:\#|report|number|num\.?|no\.?)?(?:[\s=-]|<br\s*/>)+)|
            (?:(?:\s\#)?(?:[\s=-]|<br\s*/>)*))
        0*(?P<bugnum>\d+)
      ) |
      (?P<faq>
        \bfaq(?:[\s=-]|<br\s*/>)*(?:\#|item|number?|num\.?|no\.?)?
        (?:[\s=-]|<br\s*/>)*
        0*(?P<faqnum>\d+)
      ) |
      (?P<oops>
        \boops\s*-\s*
        (?P<oopscode> \w+)
      ) |
      (?P<lpbranchurl>
        \blp:(?:///|/)?
        (?P<branch>%(unreserved)s(?:%(unreserved)s|/)*)
      )
    ''' % {'unreserved': "(?:[-a-zA-Z0-9._~%!$'()*+,;=]|&amp;|&\#x27;)"},
                             re.IGNORECASE | re.VERBOSE)

    # There is various punctuation that can occur at the end of a link that
    # shouldn't be included. The regex below matches on the set of characters
    # we don't generally want. See also _handle_parens_in_trailers, which
    # re-attaches parens if we do want them to be part of the url.
    _re_url_trailers = re.compile(r'([,.?:);>]+)$')

    def text_to_html(self, linkify_text=True, linkify_substitution=None,
                     last_paragraph_class=None):
        """Quote text according to DisplayingParagraphsOfText."""
        # This is based on the algorithm in the
        # DisplayingParagraphsOfText spec, but is a little more
        # complicated.

        # 1. Blank lines are used to detect paragraph boundaries.
        # 2. Two lines are considered to be part of the same logical line
        #    only if the first is between 60 and 80 characters and the
        #    second does not begin with white space.
        # 3. Use <br /> to split logical lines within a paragraph.
        output = []
        paras = list(split_paragraphs(self._stringtoformat))
        last_paragraph_index = len(paras) - 1
        for index, para in enumerate(paras):
            if index > 0:
                output.append('\n')
            css_class = ''
            if last_paragraph_class and index == last_paragraph_index:
                css_class = ' class="%s"' % last_paragraph_class
            output.append('<p%s>' % css_class)

            first_line = True
            for line in para:
                if not first_line:
                    output.append('<br />\n')
                first_line = False
                # escape ampersands, etc in text
                line = html_escape(line)
                # convert leading space in logical line to non-breaking space
                line = self._re_leadingspace.sub(
                    self._substitute_matchgroup_for_spaces, line)
                output.append(line)
            output.append('</p>')

        text = ''.join(output)

        # Linkify the text, if allowed.
        if linkify_text is True:
            if linkify_substitution is None:
                linkify_substitution = self._linkify_substitution
            text = re_substitute(self._re_linkify, linkify_substitution,
                break_long_words, text)

        return text

    def text_to_html_with_target(self):
        """See `text_to_html`().

        URLs will be linkified with a target="_new" attribute.
        """
        return self.text_to_html(
            linkify_text=True,
            linkify_substitution=self._linkify_substitution_with_target)

    def nice_pre(self):
        """<pre>, except the browser knows it is allowed to break long lines

        Note that CSS will eventually have a property to specify this
        behaviour, but we want this now. To do this we need to use the mozilla
        specific -moz-pre-wrap value of the white-space property. We try to
        fall back for IE by using the IE specific word-wrap property.

        TODO: Test IE compatibility. StuartBishop 20041118
        """
        if not self._stringtoformat:
            return self._stringtoformat
        else:
            linkified_text = re_substitute(self._re_linkify,
                self._linkify_substitution, break_long_words,
                html_escape(self._stringtoformat))
            return '<pre class="wrap">%s</pre>' % linkified_text

    # Match lines that start with one or more quote symbols followed
    # by a space. Quote symbols are commonly '|', or '>'; they are
    # used for quoting passages from another email. Both '>> ' and
    # '> > ' are valid quoting sequences.
    # The dpkg version is used for exceptional cases where it
    # is better to not assume '|' is a start of a quoted passage.
    _re_quoted = re.compile('^(([|] ?)+|(&gt; ?)+)')
    _re_dpkg_quoted = re.compile('^(&gt; ?)+ ')

    # Match blocks that start as signatures or PGP inclusions.
    _re_include = re.compile('^<p>(--<br />|-----BEGIN PGP)')

    def email_to_html(self):
        """text_to_html and hide signatures and full-quoted emails.

        This method wraps inclusions like signatures and PGP blocks in
        <span class="foldable"></span> tags. Quoted passages are wrapped
        <span class="foldable-quoted"></span> tags. The tags identify the
        extra content in the message to the presentation layer. CSS and
        JavaScript may use this markup to control the content's display
        behaviour.
        """
        start_fold_markup = '<span class="foldable">'
        start_fold_quoted_markup = '<span class="foldable-quoted">'
        end_fold_markup = '%s\n</span></p>'
        re_quoted = self._re_quoted
        re_include = self._re_include
        output = []
        in_fold = False
        in_quoted = False
        in_false_paragraph = False

        def is_quoted(line):
            """Test that a line is a quote and not Python.

            Note that passages may be wrongly be interpreted as Python
            because they start with '>>> '. The function does not check
            that next and previous lines of text consistently uses '>>> '
            as Python would.
            """
            python_block = '&gt;&gt;&gt; '
            return (not line.startswith(python_block)
                and re_quoted.match(line) is not None)

        def strip_leading_p_tag(line):
            """Return the characters after the paragraph mark (<p>).

            The caller must be certain the line starts with a paragraph mark.
            """
            assert line.startswith('<p>'), (
                "The line must start with a paragraph mark (<p>).")
            return line[3:]

        def strip_trailing_p_tag(line):
            """Return the characters before the line paragraph mark (</p>).

            The caller must be certain the line ends with a paragraph mark.
            """
            assert line.endswith('</p>'), (
                "The line must end with a paragraph mark (</p>).")
            return line[:-4]

        for line in self.text_to_html().split('\n'):
            if 'Desired=<wbr />Unknown/' in line and not in_fold:
                # When we see a evidence of dpkg output, we switch the
                # quote matching rules. We do not assume lines that start
                # with a pipe are quoted passages. dpkg output is often
                # reformatted by users and tools. When we see the dpkg
                # output header, we change the rules regardless of if the
                # lines that follow are legitimate.
                re_quoted = self._re_dpkg_quoted
            elif not in_fold and re_include.match(line) is not None:
                # This line is a paragraph with a signature or PGP inclusion.
                # Start a foldable paragraph.
                in_fold = True
                line = '<p>%s%s' % (start_fold_markup,
                                    strip_leading_p_tag(line))
            elif (not in_fold and line.startswith('<p>')
                and is_quoted(strip_leading_p_tag(line))):
                # The paragraph starts with quoted marks.
                # Start a foldable quoted paragraph.
                in_fold = True
                line = '<p>%s%s' % (
                    start_fold_quoted_markup, strip_leading_p_tag(line))
            elif not in_fold and is_quoted(line):
                # This line in the paragraph is quoted.
                # Start foldable quoted lines in a paragraph.
                in_quoted = True
                in_fold = True
                output.append(start_fold_quoted_markup)
            else:
                # This line is continues the current state.
                # This line is not a transition.
                pass

            # We must test line starts and ends in separate blocks to
            # close the rare single line that is foldable.
            if in_fold and line.endswith('</p>') and in_false_paragraph:
                # The line ends with a false paragraph in a PGP signature.
                # Restore the line break to join with the next paragraph.
                line = '%s<br />\n<br />' % strip_trailing_p_tag(line)
            elif (in_quoted and self._re_quoted.match(line) is None):
                # The line is not quoted like the previous line.
                # End fold before we append this line.
                in_fold = False
                in_quoted = False
                output.append("</span>\n")
            elif in_fold and line.endswith('</p>'):
                # The line is quoted or an inclusion, and ends the paragraph.
                # End the fold before the close paragraph mark.
                in_fold = False
                in_quoted = False
                line = end_fold_markup % strip_trailing_p_tag(line)
            elif in_false_paragraph and line.startswith('<p>'):
                # This line continues a PGP signature, but starts a paragraph.
                # Remove the paragraph to join with the previous paragraph.
                in_false_paragraph = False
                line = strip_leading_p_tag(line)
            else:
                # This line is continues the current state.
                # This line is not a transition.
                pass

            if in_fold and 'PGP SIGNATURE' in line:
                # PGP signature blocks are split into two paragraphs
                # by the text_to_html. The foldable feature works with
                # a single paragraph, so we merge this paragraph with
                # the next one.
                in_false_paragraph = True

            output.append(line)
        return '\n'.join(output)

    def obfuscate_email(self):
        """Obfuscate an email address if there's no authenticated user.

        The email address is obfuscated as <email address hidden>.

        This formatter is intended to hide possible email addresses from
        unauthenticated users who view this text on the Web. Run this before
        the text is converted to html because text-to-html and email-to-html
        will insert markup into the address. eg.
        foo/fmt:obfuscate-email/fmt:email-to-html

        The pattern used to identify an email address is not 2822. It strives
        to match any possible email address embedded in the text. For example,
        mailto:person@domain.dom and http://person:password@domain.dom both
        match, though the http match is in fact not an email address.
        """
        if getUtility(ILaunchBag).user is not None:
            return self._stringtoformat
        return obfuscate_email(self._stringtoformat)

    def strip_email(self):
        """Strip out things that may be email.

        This is a variation on obfuscate_email for when we are generating a
        snipped for page metadata: we don't want to waste space spelling out
        "<email address hidden>", and we do want to strip addresses even for
        logged-in users in case they use the summary in a sharing tool.
        """
        return obfuscate_email(self._stringtoformat, replacement="...")

    def linkify_email(self, preloaded_person_data=None):
        """Linkify any email address recognised in Launchpad.

        If an email address is recognised as one registered in Launchpad,
        it is linkified to point to the profile page for that person.

        Note that someone could theoretically register any old email
        address in Launchpad and then have it linkified.  This may or not
        may be a concern but is noted here for posterity anyway.
        """
        text = self._stringtoformat
        seen_addresses = []
        matches = re.finditer(re_email_address, text)
        for match in matches:
            address = match.group()
            # Since we globally replace the e-mail in the text, if we have seen
            # the address before, skip it.
            if address in seen_addresses:
                continue
            person = None
            # First try to find the person required in the preloaded person
            # data dictionary.
            if preloaded_person_data is not None:
                person = preloaded_person_data.get(address, None)
            else:
                # No pre-loaded data -> we need to perform a database lookup.
                person = getUtility(IPersonSet).getByEmail(address)
            # Only linkify if person exists and does not want to hide
            # their email addresses.
            if person is not None and not person.hide_email_addresses:
                # Circular dependancies now. Should be resolved by moving the
                # object image display api.
                from lp.app.browser.tales import ObjectImageDisplayAPI
                css_sprite = ObjectImageDisplayAPI(person).sprite_css()
                seen_addresses.append(address)
                text = text.replace(
                    address, '<a href="%s" class="%s">%s</a>' % (
                        canonical_url(person), css_sprite, address))

        return text

    def lower(self):
        """Return the string in lowercase"""
        return self._stringtoformat.lower()

    def shorten(self, maxlength):
        """Use like tal:content="context/foo/fmt:shorten/60"."""
        if len(self._stringtoformat) > maxlength:
            return '%s...' % self._stringtoformat[:maxlength - 3]
        else:
            return self._stringtoformat

    def ellipsize(self, maxlength):
        """Use like tal:content="context/foo/fmt:ellipsize/60"."""
        if len(self._stringtoformat) > maxlength:
            length = (maxlength - 3) / 2
            return (
                self._stringtoformat[:maxlength - length - 3] + '...' +
                self._stringtoformat[-length:])
        else:
            return self._stringtoformat

    def format_diff(self):
        """Format the string as a diff in a table with line numbers."""
        # Trim off trailing carriage returns.
        text = self._stringtoformat.rstrip('\n')
        if len(text) == 0:
            return text
        result = ['<table class="diff">']

        max_format_lines = config.diff.max_format_lines
        header_next = False
        for row, line in enumerate(text.splitlines()[:max_format_lines]):
            result.append('<tr>')
            result.append('<td class="line-no">%s</td>' % (row + 1))
            if line.startswith('==='):
                css_class = 'diff-file text'
                header_next = True
            elif (header_next and
                  (line.startswith('+++') or
                  line.startswith('---'))):
                css_class = 'diff-header text'
            elif line.startswith('@@'):
                css_class = 'diff-chunk text'
                header_next = False
            elif line.startswith('+'):
                css_class = 'diff-added text'
                header_next = False
            elif line.startswith('-'):
                css_class = 'diff-removed text'
                header_next = False
            elif line.startswith('#'):
                # This doesn't occur in normal unified diffs, but does
                # appear in merge directives, which use text/x-diff or
                # text/x-patch.
                css_class = 'diff-comment text'
                header_next = False
            else:
                css_class = 'text'
                header_next = False
            result.append(
                structured(
                    '<td class="%s">%s</td>', css_class, line).escapedtext)
            result.append('</tr>')

        result.append('</table>')
        return ''.join(result)

    _css_id_strip_pattern = re.compile(r'[^a-zA-Z0-9-_]+')
    _zope_css_id_strip_pattern = re.compile(r'[^a-zA-Z0-9-_\.]+')

    def css_id(self, prefix=None):
        """Return a CSS compliant id."""
        return self._css_id(self._css_id_strip_pattern, prefix)

    def zope_css_id(self, prefix=None):
        """Return a CSS compliant id compatible with zope's form fields.

        The strip pattern allows ids which contain periods which is required
        for compatibility with zope form fields.
        """
        return self._css_id(self._zope_css_id_strip_pattern, prefix)

    def _css_id(self, strip_pattern, prefix=None):
        """Return a CSS compliant id.

        The id may contain letters, numbers, hyphens and underscores. The
        first character must be a letter. Unsupported characters are converted
        to hyphens. Multiple characters are replaced by a single hyphen. The
        letter 'j' will start the id if the string's first character is not a
        letter.

        :param prefix: an optional string to prefix to the id. It can be
            used to ensure that the start of the id is predictable.
        """
        if prefix is not None:
            raw_text = prefix + self._stringtoformat
        else:
            raw_text = self._stringtoformat
        id_ = strip_pattern.sub('-', raw_text)

        # If any characters are converted to a hyphen, we cannot be 100%
        # assured of a unique id unless we take further action. Note that we
        # use the _zope_css_id_strip_pattern for the check because ids with
        # periods are still in common usage.
        if self._zope_css_id_strip_pattern.search(raw_text):
            # We need to ensure that the id is always guaranteed to be unique,
            # hence we append URL-safe base 64 encoding of the name. However
            # we also have to strip off any padding characters ("=") because
            # Python's URL-safe base 64 encoding includes those and they
            # aren't allowed in IDs either.
            unique_suffix = urlsafe_b64encode(raw_text)
            # Ensure we put a '-' between the id and base 64 encoding.
            if id_[-1] != '-':
                id_ += '-'
            id_ += unique_suffix.replace('=', '')

        if id_[0] in '-_0123456789':
            # 'j' is least common starting character in technical usage;
            # engineers love 'z', 'q', and 'y'.
            return 'j' + id_
        else:
            return id_

    def oops_id(self):
        """Format an OOPS ID for display."""
        if not getUtility(ILaunchBag).developer:
            # We only linkify OOPS IDs for Launchpad developers.
            return self._stringtoformat

        root_url = config.launchpad.oops_root_url
        url = root_url + self._stringtoformat
        return '<a href="%s">%s</a>' % (url, self._stringtoformat)

    def markdown(self):
        if getFeatureFlag('markdown.enabled'):
            return format_markdown(self._stringtoformat)
        else:
            return self.text_to_html()

    def traverse(self, name, furtherPath):
        if name == 'nl_to_br':
            return self.nl_to_br()
        elif name == 'escape':
            return self.escape()
        elif name == 'lower':
            return self.lower()
        elif name == 'break-long-words':
            return self.break_long_words()
        elif name == 'markdown':
            return self.markdown()
        elif name == 'text-to-html':
            return self.text_to_html()
        elif name == 'text-to-html-with-target':
            return self.text_to_html_with_target()
        elif name == 'nice_pre':
            return self.nice_pre()
        elif name == 'email-to-html':
            return self.email_to_html()
        elif name == 'obfuscate-email':
            return self.obfuscate_email()
        elif name == 'strip-email':
            return self.strip_email()
        elif name == 'linkify-email':
            return self.linkify_email()
        elif name == 'shorten':
            if len(furtherPath) == 0:
                raise TraversalError(
                    "you need to traverse a number after fmt:shorten")
            maxlength = int(furtherPath.pop())
            return self.shorten(maxlength)
        elif name == 'ellipsize':
            if len(furtherPath) == 0:
                raise TraversalError(
                    "you need to traverse a number after fmt:ellipsize")
            maxlength = int(furtherPath.pop())
            return self.ellipsize(maxlength)
        elif name == 'diff':
            return self.format_diff()
        elif name == 'css-id':
            if len(furtherPath) > 0:
                return self.css_id(furtherPath.pop())
            else:
                return self.css_id()
        elif name == 'zope-css-id':
            if len(furtherPath) > 0:
                return self.zope_css_id(furtherPath.pop())
            else:
                return self.zope_css_id()
        elif name == 'oops-id':
            return self.oops_id()
        else:
            raise TraversalError(name)


def format_markdown(text):
    """Return html form of marked-up text."""
    # This returns whole paragraphs (in p tags), similarly to text_to_html.
    md = markdown.Markdown(
        safe_mode='escape',
        extensions=[
            'tables',
            'nl2br',
            ])
    return md.convert(text)  # How easy was that?
