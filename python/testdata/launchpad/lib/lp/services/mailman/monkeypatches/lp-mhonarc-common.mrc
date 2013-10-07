<!-- Launchpad customizations common to all our MHonArc-generated
     mailing list archives.

     See http://www.mhonarc.org/MHonArc/doc/mhonarc.html and
     http://www.mhonarc.org/MHonArc/doc/faq/, they are your friends.

     http://www.mhonarc.org/MHonArc/doc/resources.html#index is
     especially your friend, when all others have abandoned you.  -->

<!-- Basic parameters. -->
<SPAMMODE>
<MAIN>
<THREAD>
<SORT>
<REVERSE>
<TREVERSE>
<NODOC>
<UMASK>
022
</UMASK>


<!-- Encode all messages as utf-8 and set the page encoding to utf-8 -->
<TextEncode>
utf-8; MHonArc::UTF8::to_utf8; MHonArc/UTF8.pm
</TextEncode>

<!-- text/plain only. CVE-2010-4524 -->
<MIMEExcs>
text/html
text/x-html
</MIMEExcs>

<IDXFNAME>
date.html
</IDXFNAME>

<TIDXFNAME>
maillist.html
</TIDXFNAME>

<!-- Use multi-page indexes.
     See http://www.mhonarc.org/MHonArc/doc/resources/multipg.html -->
<MULTIPG>
<IDXSIZE>
200
</IDXSIZE>

<!-- strip the first [list-name] from the subect line. -->
<SUBJECTSTRIPCODE>
s/\[[^ ]+\]//;
</SUBJECTSTRIPCODE>


<!-- Define a custom resource variable to represent this mailing list.
     This depends on $ML-NAME$ having been set already, presumably on
     the command line via '-definevar'.  See
     http://www.mhonarc.org/MHonArc/doc/resources/definevar.html. -->

<DefineVar>
TEAM-LINK
<a href="https://launchpad.net/~$ML-NAME$">$ML-NAME$</a>
</DefineVar>


<DefineVar>
PAGE-TOP-START
<!DOCTYPE html>
<html>
<head>
<title>
</DefineVar>

<DefineVar>
PAGE-TOP-END
</title>
<style type="text/css">
h1, ul, ol, dl, li, dt, dd {
    margin: 0;
    padding: 0;
    }
ul ul {
    margin-left: 2em;
    }
.mail li {
    margin-left: 20px;
    padding-left: 0px;
   }
.upper-batch-nav {
    margin: 12px 0;
    border-bottom: 1px solid #d2d2d2;
    }
.lower-batch-nav {
    margin: 12px 0;
    border-top: 1px solid #d2d2d2;
    }
.lower-batch-nav.message-count-0 {
    display: none;
    }
.batch-navigation-links {
    text-align: right;
    padding-left: 24px;
    }
.message-count-0 {
    margin-bottom: 12px;
    }
.message-count-0:before {
    content: "There are no messages in this mailing list archive.";
    }
.back-to {
    margin: 0 0 12px 0;
    padding: 0 0 6px 0;
    border-bottom: 1px solid #d2d2d2;
    }
.facetmenu {
    margin-top: 4px;
    margin-left: .5em;
    }
</style>
<link rel="stylesheet" href="https://launchpad.net/+icing/import.css" />
<link rel="shortcut icon" href="https://launchpad.net/@@/launchpad.png" />
</head>
<body>
  <div class="back-to">
    <a href="https://launchpad.net/~$ML-NAME$">&larr;
      Back to team overview</a>
  </div>
  <h1>$ML-NAME$ team mailing list archive</h1>
  <div id="watermark" class="watermark-apps-portlet">
    <div class="wide">
</DefineVar>

<DefineVar>
PAGE-BOTTOM
  <div id="footer" class="footer">
    <div class="lp-arcana">
        <div class="lp-branding">
          <a href="https://launchpad.net/"><img
         src="https://launchpad.net/@@/launchpad-logo-and-name-hierarchy.png"
         alt="Launchpad" /></a>
          &nbsp;&bull;&nbsp;
          <a href="https://launchpad.net/+tour">Take the tour</a>
          &nbsp;&bull;&nbsp;
          <a href="https://help.launchpad.net/">Read the guide</a>
          &nbsp;&bull;&nbsp;
          <a href="https://help.launchpad.net/Teams/MailingLists"
          >Help for mailing lists</a>
          &nbsp;
          <form id="globalsearch" method="get"
                accept-charset="UTF-8"
                action="https://launchpad.net/+search">
            <input type="search" id="search-text" name="field.text" />
            <input type="submit" value=""
              class="sprite search-icon" />
          </form>
        </div>
    </div>
    <div class="colophon">
      &copy; 2004-2012
      <a href="http://canonical.com/">Canonical&nbsp;Ltd.</a>
      &nbsp;&bull;&nbsp;
      <a href="https://launchpad.net/legal">Terms of use</a>
      &nbsp;&bull;&nbsp;
      <a href="/support">Contact Launchpad Support</a>
      &nbsp;&bull;&nbsp;
      <a href="http://identi.ca/launchpadstatus">System status</a>
      </span>
    </div>
  </div>
</body>
</html>
</DefineVar>


<!-- What do the next/prev links look like? -->
<IDXLABEL>
Date index
</IDXLABEL>

<TIDXLABEL>
Thread index
</TIDXLABEL>

<!-- The text is reversed because the messages are sorted in reverse. -->
<PREVPGLINK>
<a href="$PG(FIRST)$">Last</a> &bull; <a href="$PG(PREV)$">Next</a>
</PREVPGLINK>

<PREVPGLINKIA>
<span class="inactive">Last &bull; Next</span>
</PREVPGLINKIA>

<TPREVPGLINK>
<a href="$PG(TFIRST)$">Last</a> &bull; <a href="$PG(TPREV)$">Next</a>
</TPREVPGLINK>

<TPREVPGLINKIA>
<span class="inactive">Last &bull; Next</span>
</TPREVPGLINKIA>

<NEXTPGLINK>
<a class="next" href="$PG(NEXT)$">Previous</a>
  &bull; <a href="$PG(LAST)$">First</a>
</NEXTPGLINK>

<NEXTPGLINKIA>
<span class="next inactive">Previous</span>
  &bull; <span class="inactive">First</span>
</NEXTPGLINKIA>

<TNEXTPGLINK>
<a class="next" href="$PG(TNEXT)$">Previous</a>
   &bull; <a href="$PG(TLAST)$">First</a>
</TNEXTPGLINK>

<TNEXTPGLINKIA>
<span class="next inactive">Previous</span>
  &bull;<span class="inactive">First</span>
</TNEXTPGLINKIA>


<!-- Thread index pages -->
<TIDXPGBEGIN>
$PAGE-TOP-START$
Messages by thread : Mailing list archive : $ML-NAME$ team in Launchpad
$PAGE-TOP-END$
</TIDXPGBEGIN>

<TIDXPGEND>
$PAGE-BOTTOM$
</TIDXPGEND>

<!-- Formatting for the start of thread page.
     See http://www.mhonarc.org/MHonArc/doc/resources/thead.html. -->
<THEAD>
      <ul class="facetmenu">
          <li title="View messages by thread"
            class="active"><span>Thread</span></li>
          <li title="View messages by date"><a href="$IDXFNAME$">Date</a></li>
      </ul>
    </div>
  </div>

<ol class="breadcrumbs">
  <li>
    <img src="https://launchpad.net/@@/team" alt=""/>
    <a href="https://launchpad.net/~$ML-NAME$">$ML-NAME$ team</a>
  </li>
  <li>
    <a href="$TIDXFNAME$">Mailing list archive</a>
  </li>
  <li>
    Messages by thread
  </li>
</ol>

<h2>Messages by thread</h2>

<p>
Messages sent to the $ML-NAME$ mailing list, ordered by thread from the
newest to oldest.
</p>

<table class="wide upper-batch-nav">
  <tr>
    <td>
      $NUMOFIDXMSG$ of $NUMOFMSG$ messages, page $PGLINKLIST(T5;T5)$
    </td>
    <td class="batch-navigation-links">
      $PGLINK(TPREV)$ &bull; $PGLINK(TNEXT)$
    </td>
  </tr>
</table>

<ul class="mail wide message-count-$NUMOFMSG$">
</THEAD>

<TFOOT>
</ul>
<table class="wide lower-batch-nav message-count-$NUMOFMSG$">
  <tr>
    <td>
      $NUMOFIDXMSG$ of $NUMOFMSG$ messages, page $PGLINKLIST(T5;T5)$
    </td>
    <td class="batch-navigation-links">
      $PGLINK(TPREV)$ &bull; $PGLINK(TNEXT)$
    </td>
  </tr>
</table>
</TFOOT>


<!-- Date index pages -->
<IDXPGBEGIN>
$PAGE-TOP-START$
Messages by date : Mailing list archive : $ML-NAME$ team in Launchpad
$PAGE-TOP-END$
</IDXPGBEGIN>

<IDXPGEND>
$PAGE-BOTTOM$
</IDXPGEND>

<!-- Formatting for the start of list page.
     See http://www.mhonarc.org/MHonArc/doc/resources/listbegin.html. -->
<LISTBEGIN>
    <ul class="facetmenu">
        <li title="View messages by thread">
            <a href="$TIDXFNAME$">Thread</a>
        </li>
        <li title="View messages by date" class="active">
          <span>Date</span>
        </li>
    </ul>
  </div>
</div>

<ol class="breadcrumbs">
  <li>
    <img src="https://launchpad.net/@@/team" alt=""/>
    <a href="https://launchpad.net/~$ML-NAME$">$ML-NAME$ team</a>
  </li>
  <li>
    <a href="$TIDXFNAME$">Mailing list archive</a>
  </li>
  <li>
    Messages by date
  </li>
</ol>

<h2>Messages by date</h2>

<p>
Messages sent to the $ML-NAME$ mailing list, ordered by date from the
newest to oldest.
</p>

<table class="wide upper-batch-nav">
  <tr>
    <td>
      $NUMOFIDXMSG$ of $NUMOFMSG$ messages, page $PGLINKLIST(5;5)$
    </td>
    <td class="batch-navigation-links">
      $PGLINK(PREV)$ &bull; $PGLINK(NEXT)$
    </td>
  </tr>
</table>

<ul class="mail wide message-count-$NUMOFMSG$">
</LISTBEGIN>

<LISTEND>
</ul>
<table class="wide lower-batch-nav message-count-$NUMOFMSG$">
  <tr>
    <td>
      $NUMOFIDXMSG$ of $NUMOFMSG$ messages, page $PGLINKLIST(5;5)$
    </td>
    <td class="batch-navigation-links">
      $PGLINK(PREV)$ &bull; $PGLINK(NEXT)$
    </td>
  </tr>
</table>
</LISTEND>


<!-- Message item formatting for all lists. -->
<DefineVar>
MESSAGE-LIST-ITEM
<li>
  <strong>$SUBJECT$</strong>
  <br />From: $FROMNAME$, $MSGGMTDATE(CUR;%Y-%m-%d)$
</li>
</DefineVar>

<LITEMPLATE>
$MESSAGE-LIST-ITEM$
</LITEMPLATE>

<TTOPBEGIN>
$MESSAGE-LIST-ITEM$
</TTOPBEGIN>

<TLITXT>
$MESSAGE-LIST-ITEM$
</TLITXT>

<TSINGLETXT>
$MESSAGE-LIST-ITEM$
</TSINGLETXT>


<!-- Message pages -->
<MSGPGBEGIN>
$PAGE-TOP-START$
$SUBJECTNA$ : Mailing list archive : $ML-NAME$ team in Launchpad
$PAGE-TOP-END$
</MSGPGBEGIN>

<MSGPGEND>
$PAGE-BOTTOM$
</MSGPGEND>

<SUBJECTHEADER>
  <!-- Supress the header section since it was moved before the top links. -->
</SUBJECTHEADER>

<!-- Message navigation links -->
<TopLinks>
    <ul class="facetmenu">
        <li title="View messages by thread"
          class="active"><a href="$TIDXFNAME$">Thread</a></li>
        <li title="View messages by date"><a href="$IDXFNAME$">Date</a></li>
    </ul>
  </div>
</div>

<ol class="breadcrumbs">
  <li>
    <img src="https://launchpad.net/@@/team" alt=""/>
    <a href="https://launchpad.net/~$ML-NAME$">$ML-NAME$ team</a>
  </li>
  <li>
    <a href="$TIDXFNAME$">Mailing list archive</a>
  </li>
  <li>
    Message #$MSGNUM$
  </li>
</ol>

<h2>$SUBJECTNA$</h2>

<table class="wide upper-batch-nav">
  <tr>
    <td>
      &nbsp;
    </td>
    <td class="batch-navigation-links">
      <a href="$MSG(TPREV)$">Thread Previous</a> &bull;
      <a href="$MSG(PREV)$">Date Previous</a> &bull;
      <a class="next" href="$MSG(NEXT)$">Date Next</a> &bull;
      <a href="$MSG(TNEXT)$">Thread Next</a>
    </td>
  </tr>
</table>
</TopLinks>

<BotLinks>
<table class="wide lower-batch-nav">
  <tr>
    <td>
      &nbsp;
    </td>
    <td class="batch-navigation-links">
      <a href="$MSG(TPREV)$">Thread Previous</a> &bull;
      <a href="$MSG(PREV)$">Date Previous</a> &bull;
      <a class="next" href="$MSG(NEXT)$">Date Next</a> &bull;
      <a href="$MSG(TNEXT)$">Thread Next</a>
    </td>
  </tr>
</table>
</BotLinks>

<!-- Exclude noisy message fields -->
<EXCS>
subject
list-
dkim-
Domainkey-
precendence
References
</EXCS>

<!-- Format message header in a definition list. -->

<Fieldsbeg>
<ul class="iconed">
</FieldsBeg>

<LabelBeg>
<li>
  <strong>
</LabelBeg>

<LabelEnd>
</strong>:
</LabelEnd>

<FldBeg>
</FldBeg>

<FldEnd>
</li>
</FldEnd>

<FieldsEnd>
</ul>
</FieldsEnd>

<LabelStyles>
-default-:strong
</LabelStyles>

<FOLUPBEGIN>
<h3>Follow ups</h3>
<ul class="mail wide">
</FOLUPBEGIN>

<FOLUPLITXT>
$MESSAGE-LIST-ITEM$
</FOLUPLITXT>

<FOLUPEND>
</ul>
</FOLUPEND>


<REFSBEGIN>
<h3>References</h3>
<ul class="mail wide">
</REFSBEGIN>

<REFSLITXT>
$MESSAGE-LIST-ITEM$
</REFSLITXT>

<REFSEND>
</ul>
</REFSEND>
