# Copyright 2011-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Notification for uploads and copies."""

__metaclass__ = type

__all__ = [
    'notify',
    ]


from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import os

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.utils import get_ppa_reference
from lp.archiveuploader.changesfile import ChangesFile
from lp.archiveuploader.utils import (
    ParseMaintError,
    safe_fix_maintainer,
    )
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.config import config
from lp.services.encoding import (
    ascii_smash,
    guess as guess_encoding,
    )
from lp.services.mail.helpers import get_email_template
from lp.services.mail.sendmail import (
    format_address,
    format_address_for_person,
    sendmail,
    )
from lp.services.webapp import canonical_url
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet


def reject_changes_file(blamer, changes_file_path, changes, archive,
                        distroseries, reason, logger=None):
    """Notify about a rejection where all of the details are not known.

    :param blamer: The `IPerson` that is to blame for this notification.
    :param changes_file_path: The path to the changes file.
    :param changes: A dictionary of the parsed changes file.
    :param archive: The `IArchive` the notification is regarding.
    :param distroseries: The `IDistroSeries` the notification is regarding.
    :param reason: The reason for the rejection.
    """
    ignored, filename = os.path.split(changes_file_path)
    information = {
        'SUMMARY': reason,
        'CHANGESFILE': '',
        'DATE': '',
        'CHANGEDBY': '',
        'MAINTAINER': '',
        'SIGNER': '',
        'ORIGIN': '',
        'ARCHIVE_URL': '',
        'USERS_ADDRESS': config.launchpad.users_address,
    }
    subject = '%s rejected' % filename
    if archive and archive.is_ppa:
        subject = '[PPA %s] %s' % (get_ppa_reference(archive), subject)
        information['ARCHIVE_URL'] = '\n%s' % canonical_url(archive)
    template = get_template(archive, 'rejected')
    body = template % information
    to_addrs = get_upload_notification_recipients(
        blamer, archive, distroseries, logger, changes=changes)
    debug(logger, "Sending rejection email.")
    if not to_addrs:
        debug(logger, "No recipients have a preferred email.")
        return
    send_mail(None, archive, to_addrs, subject, body, False, logger=logger)


def get_template(archive, action):
    """Return the appropriate e-mail template."""
    template_name = 'upload-'
    if action in ('new', 'accepted', 'announcement'):
        template_name += action
    elif action == 'unapproved':
        template_name += 'accepted'
    elif action == 'rejected':
        template_name += 'rejection'
    if archive.is_ppa:
        template_name = 'ppa-%s' % template_name
    template_name += '.txt'
    return get_email_template(template_name, app='soyuz')


ACTION_DESCRIPTIONS = {
    'new': 'New',
    'unapproved': 'Waiting for approval',
    'rejected': 'Rejected',
    'accepted': 'Accepted',
    'announcement': 'Accepted',
    }


def calculate_subject(spr, bprs, customfiles, archive, distroseries,
                      pocket, action):
    """Return the e-mail subject for the notification."""
    suite = distroseries.getSuite(pocket)
    names = set()
    version = '-'
    if spr:
        names.add(spr.name)
        version = spr.version
    elif bprs:
        names.add(bprs[0].build.source_package_release.name)
        version = bprs[0].build.source_package_release.version
    for custom in customfiles:
        names.add(custom.libraryfilealias.filename)
    name_str = ', '.join(names)
    subject = '[%s/%s] %s %s (%s)' % (
        distroseries.distribution.name, suite, name_str, version,
        ACTION_DESCRIPTIONS[action])
    if archive.is_ppa:
        subject = '[PPA %s] %s' % (get_ppa_reference(archive), subject)
    return subject


def notify(blamer, spr, bprs, customfiles, archive, distroseries, pocket,
           summary_text=None, changes=None, changesfile_content=None,
           changesfile_object=None, action=None, dry_run=False,
           logger=None, announce_from_person=None, previous_version=None):
    """Notify about an upload or package copy.

    :param blamer: The `IPerson` who is to blame for this notification.
    :param spr: The `ISourcePackageRelease` that was created.
    :param bprs: A list of `IBinaryPackageRelease` that were created.
    :param customfiles: An `ILibraryFileAlias` that was created.
    :param archive: The target `IArchive`.
    :param distroseries: The target `IDistroSeries`.
    :param pocket: The target `PackagePublishingPocket`.
    :param summary_text: The summary of the notification.
    :param changes: A dictionary of the parsed changes file.
    :param changesfile_content: The raw content of the changes file, so it
        can be attached to the mail if desired.
    :param changesfile_object: The raw object of the changes file. Only used
        to work out the filename for `reject_changes_file`.
    :param action: A string of what action to notify for, such as 'new',
        'accepted'.
    :param dry_run: If True, only log the mail.
    :param announce_from_person: If passed, use this `IPerson` as the From: in
        announcement emails.  If the person has no preferred email address,
        the person is ignored and the default From: is used instead.
    :param previous_version: If specified, the change log on the email will
        include all of the source package's change logs after that version
        up to and including the passed spr's version.
    """
    # If this is a binary or mixed upload, we don't send *any* emails
    # provided it's not a rejection or a security upload:
    if (
        bprs and action != 'rejected' and
        pocket != PackagePublishingPocket.SECURITY):
        debug(logger, "Not sending email; upload is from a build.")
        return

    if spr and spr.source_package_recipe_build and action == 'accepted':
        debug(logger, "Not sending email; upload is from a recipe.")
        return

    if spr is None and not bprs and not customfiles:
        # We do not have enough context to do a normal notification, so
        # reject what we do have.
        if changesfile_object is None:
            return
        reject_changes_file(
            blamer, changesfile_object.name, changes, archive, distroseries,
            summary_text, logger=logger)
        return

    # "files" will contain a list of tuples of filename,component,section.
    # If files is empty, we don't need to send an email if this is not
    # a rejection.
    try:
        files = build_uploaded_files_list(spr, bprs, customfiles, logger)
    except LanguagePackEncountered:
        # Don't send emails for language packs.
        return

    if not files and action != 'rejected':
        return

    recipients = get_upload_notification_recipients(
        blamer, archive, distroseries, logger, changes=changes, spr=spr,
        bprs=bprs)

    # There can be no recipients if none of the emails are registered
    # in LP.
    if not recipients:
        debug(logger, "No recipients on email, not sending.")
        return

    if action == 'rejected':
        default_recipient = "%s <%s>" % (
            config.uploader.default_recipient_name,
            config.uploader.default_recipient_address)
        if not recipients:
            recipients = [default_recipient]
        debug(logger, "Sending rejection email.")
        summarystring = summary_text
    else:
        summary = build_summary(spr, files, action)
        if summary_text:
            summary.append(summary_text)
        summarystring = "\n".join(summary)

    attach_changes = not archive.is_ppa

    def build_and_send_mail(action, recipients, from_addr=None, bcc=None,
                            previous_version=None):
        subject = calculate_subject(
            spr, bprs, customfiles, archive, distroseries, pocket, action)
        body = assemble_body(
            blamer, spr, bprs, archive, distroseries, summarystring, changes,
            action, previous_version=previous_version)
        body = body.encode("utf8")
        send_mail(
            spr, archive, recipients, subject, body, dry_run,
            changesfile_content=changesfile_content,
            attach_changes=attach_changes, from_addr=from_addr, bcc=bcc,
            logger=logger)

    build_and_send_mail(
        action, recipients, previous_version=previous_version)

    info = fetch_information(spr, bprs, changes)
    from_addr = info['changedby']
    if announce_from_person is not None:
        if announce_from_person.preferredemail is not None:
            from_addr = format_address_for_person(announce_from_person)

    # If we're sending an acceptance notification for a non-PPA upload,
    # announce if possible. Avoid announcing backports, binary-only
    # security uploads, or autosync uploads.
    if (action == 'accepted' and distroseries.changeslist
        and not archive.is_ppa
        and pocket != PackagePublishingPocket.BACKPORTS
        and not (pocket == PackagePublishingPocket.SECURITY and spr is None)
        and not is_auto_sync_upload(spr, bprs, pocket, from_addr)):
        name = None
        bcc_addr = None
        if spr:
            name = spr.name
        elif bprs:
            name = bprs[0].build.source_package_release.name
        if name:
            email_base = distroseries.distribution.package_derivatives_email
            if email_base:
                bcc_addr = email_base.format(package_name=name)

        build_and_send_mail(
            'announcement', [str(distroseries.changeslist)], from_addr,
            bcc_addr, previous_version=previous_version)


def assemble_body(blamer, spr, bprs, archive, distroseries, summary, changes,
                  action, previous_version=None):
    """Assemble the e-mail notification body."""
    if changes is None:
        changes = {}
    info = fetch_information(
        spr, bprs, changes, previous_version=previous_version)
    information = {
        'STATUS': ACTION_DESCRIPTIONS[action],
        'SUMMARY': summary,
        'DATE': 'Date: %s' % info['date'],
        'CHANGESFILE': info['changelog'],
        'DISTRO': distroseries.distribution.title,
        'ANNOUNCE': 'No announcement sent',
        'CHANGEDBY': '',
        'MAINTAINER': '',
        'ORIGIN': '',
        'SIGNER': '',
        'SPR_URL': '',
        'ARCHIVE_URL': '\n%s' % canonical_url(archive),
        'USERS_ADDRESS': config.launchpad.users_address,
        }
    if spr:
        # Yay, circular imports.
        from lp.soyuz.model.distroseriessourcepackagerelease import (
            DistroSeriesSourcePackageRelease,
            )
        dsspr = DistroSeriesSourcePackageRelease(distroseries, spr)
        information['SPR_URL'] = canonical_url(dsspr)
    changedby_displayname = info['changedby_displayname']
    if changedby_displayname:
        information['CHANGEDBY'] = '\nChanged-By: %s' % changedby_displayname
    origin = changes.get('Origin')
    if origin:
        information['ORIGIN'] = '\nOrigin: %s' % origin
    if action == 'unapproved':
        information['SUMMARY'] += (
            "\nThis upload awaits approval by a distro manager\n")
    if distroseries.changeslist:
        information['ANNOUNCE'] = "Announcing to %s" % (
            distroseries.changeslist)

    # Some syncs (e.g. from Debian) will involve packages whose
    # changed-by person was auto-created in LP and hence does not have a
    # preferred email address set.  We'll get a None here.
    changedby_person = email_to_person(info['changedby'])

    if blamer is not None and blamer != changedby_person:
        signer_signature = person_to_email(blamer)
        if signer_signature != info['changedby']:
            information['SIGNER'] = '\nSigned-By: %s' % signer_signature
    # Add maintainer if present and different from changed-by.
    maintainer = info['maintainer']
    changedby = info['changedby']
    if maintainer and maintainer != changedby:
        information['MAINTAINER'] = '\nMaintainer: %s' % maintainer
    return get_template(archive, action) % information


def send_mail(
    spr, archive, to_addrs, subject, mail_text, dry_run, from_addr=None,
    bcc=None, changesfile_content=None, attach_changes=False, logger=None):
    """Send an email to to_addrs with the given text and subject.

    :param spr: The `ISourcePackageRelease` to be notified about.
    :param archive: The target `IArchive`.
    :param to_addrs: A list of email addresses to be used as recipients.
        Each email must be a valid ASCII str instance or a unicode one.
    :param subject: The email's subject.
    :param mail_text: The text body of the email. Unicode is preserved in the
        email.
    :param dry_run: Whether or not an email should actually be sent. But
        please note that this flag is (largely) ignored.
    :param from_addr: The email address to be used as the sender. Must be a
        valid ASCII str instance or a unicode one.  Defaults to the email
        for config.uploader.
    :param bcc: Optional email Blind Carbon Copy address(es).
    :param param changesfile_content: The content of the actual changesfile.
    :param attach_changes: A flag governing whether the original changesfile
        content shall be attached to the email.
    """
    extra_headers = {'X-Katie': 'Launchpad actually'}

    # Include the 'X-Launchpad-PPA' header for PPA upload notfications
    # containing the PPA owner name.
    if archive.is_ppa:
        extra_headers['X-Launchpad-PPA'] = get_ppa_reference(archive)

    # Include a 'X-Launchpad-Component' header with the component and
    # the section of the source package uploaded in order to facilitate
    # filtering on the part of the email recipients.
    if spr:
        xlp_component_header = 'component=%s, section=%s' % (
            spr.component.name, spr.section.name)
        extra_headers['X-Launchpad-Component'] = xlp_component_header

    if from_addr is None:
        from_addr = format_address(
            config.uploader.default_sender_name,
            config.uploader.default_sender_address)

    # `sendmail`, despite handling unicode message bodies, can't
    # cope with non-ascii sender/recipient addresses, so ascii_smash
    # is used on all addresses.

    # All emails from here have a Bcc to the default recipient.
    bcc_text = format_address(
        config.uploader.default_recipient_name,
        config.uploader.default_recipient_address)
    if bcc:
        bcc_text = "%s, %s" % (bcc_text, bcc)
    extra_headers['Bcc'] = ascii_smash(bcc_text)

    recipients = ascii_smash(", ".join(to_addrs))
    if isinstance(from_addr, unicode):
        # ascii_smash only works on unicode strings.
        from_addr = ascii_smash(from_addr)
    else:
        from_addr.encode('ascii')

    if dry_run and logger is not None:
        debug(logger, "Would have sent a mail:")
    else:
        debug(logger, "Sent a mail:")
    debug(logger, "  Subject: %s" % subject)
    debug(logger, "  Sender: %s" % from_addr)
    debug(logger, "  Recipients: %s" % recipients)
    if 'Bcc' in extra_headers:
        debug(logger, "  Bcc: %s" % extra_headers['Bcc'])
    debug(logger, "  Body:")
    for line in mail_text.splitlines():
        if isinstance(line, str):
            line = line.decode('utf-8', 'replace')
        debug(logger, line)

    if not dry_run:
        # Since we need to send the original changesfile as an
        # attachment the sendmail() method will be used as opposed to
        # simple_sendmail().
        message = MIMEMultipart()
        message['from'] = from_addr
        message['subject'] = subject
        message['to'] = recipients

        # Set the extra headers if any are present.
        for key, value in extra_headers.iteritems():
            message.add_header(key, value)

        # Add the email body.
        message.attach(
            MIMEText(sanitize_string(mail_text).encode('utf-8'),
                'plain', 'utf-8'))

        if attach_changes:
            # Add the original changesfile as an attachment.
            if changesfile_content is not None:
                changesfile_text = sanitize_string(changesfile_content)
            else:
                changesfile_text = ("Sorry, changesfile not available.")

            attachment = MIMEText(
                changesfile_text.encode('utf-8'), 'plain', 'utf-8')
            attachment.add_header(
                'Content-Disposition',
                'attachment; filename="changesfile"')
            message.attach(attachment)

        # And finally send the message.
        sendmail(message)


def sanitize_string(s):
    """Make sure string does not trigger 'ascii' codec errors.

    Convert string to unicode if needed so that characters outside
    the (7-bit) ASCII range do not cause errors like these:

        'ascii' codec can't decode byte 0xc4 in position 21: ordinal
        not in range(128)
    """
    if isinstance(s, unicode):
        return s
    else:
        return guess_encoding(s)


def debug(logger, msg, *args, **kwargs):
    """Shorthand debug notation for publish() methods."""
    if logger is not None:
        logger.debug(msg, *args, **kwargs)


def is_valid_uploader(person, distribution):
    """Is `person` an uploader for `distribution`?

    A `None` person is not an uploader.
    """
    if person is None:
        return None
    else:
        return not getUtility(IArchivePermissionSet).componentsForUploader(
            distribution.main_archive, person).is_empty()


def get_upload_notification_recipients(blamer, archive, distroseries,
                                       logger=None, changes=None, spr=None,
                                       bprs=None):
    """Return a list of recipients for notification emails."""
    debug(logger, "Building recipients list.")
    candidate_recipients = [blamer]
    info = fetch_information(spr, bprs, changes)

    changer = email_to_person(info['changedby'])
    maintainer = email_to_person(info['maintainer'])

    if blamer is None and not archive.is_copy:
        debug(logger, "Changes file is unsigned; adding changer as recipient.")
        candidate_recipients.append(changer)

    if archive.is_ppa:
        # For PPAs, any person or team mentioned explicitly in the
        # ArchivePermissions as uploaders for the archive will also
        # get emailed.
        candidate_recipients.extend([
            permission.person
            for permission in archive.getUploadersForComponent()])
    elif archive.is_copy:
        # For copy archives, notifying anyone else will probably only
        # confuse them.
        pass
    else:
        # If this is not a PPA, we also consider maintainer and changed-by.
        if blamer is not None:
            if is_valid_uploader(maintainer, distroseries.distribution):
                debug(logger, "Adding maintainer to recipients")
                candidate_recipients.append(maintainer)

            if is_valid_uploader(changer, distroseries.distribution):
                debug(logger, "Adding changed-by to recipients")
                candidate_recipients.append(changer)

    # Collect email addresses to notify.  Skip persons who do not have a
    # preferredemail set, such as people who have not activated their
    # Launchpad accounts (and are therefore not expecting this email).
    recipients = [
        format_address_for_person(person)
        for person in filter(None, set(candidate_recipients))
            if person.preferredemail is not None]

    for recipient in recipients:
        debug(logger, "Adding recipient: '%s'", recipient)

    return recipients


def build_uploaded_files_list(spr, builds, customfiles, logger):
    """Return a list of tuples of (filename, component, section).

    Component and section are only set where the file is a source upload.
    If an empty list is returned, it means there are no files.
    Raises LanguagePackRejection if a language pack is detected.
    No emails should be sent for language packs.
    """
    files = []
    # Bail out early if this is an upload for the translations
    # section.
    if spr:
        if spr.section.name == 'translations':
            debug(logger,
                "Skipping acceptance and announcement, it is a "
                "language-package upload.")
            raise LanguagePackEncountered
        for sprfile in spr.files:
            files.append(
                (sprfile.libraryfile.filename, spr.component.name,
                spr.section.name))

    # Component and section don't get set for builds and custom, since
    # this information is only used in the summary string for source
    # uploads.
    for build in builds:
        for bpr in build.build.binarypackages:
            files.extend([
                (bpf.libraryfile.filename, '', '') for bpf in bpr.files])

    if customfiles:
        files.extend(
            [(file.libraryfilealias.filename, '', '') for file in customfiles])

    return files


def build_summary(spr, files, action):
    """Build a summary string based on the files present in the upload."""
    summary = []
    for filename, component, section in files:
        if action == 'new':
            summary.append("NEW: %s" % filename)
        else:
            summary.append(" OK: %s" % filename)
            if filename.endswith("dsc"):
                summary.append("     -> Component: %s Section: %s" % (
                    component, section))
    return summary


def email_to_person(fullemail):
    """Return an `IPerson` given an RFC2047 email address.

    :param fullemail: Potential email address.
    :return: `IPerson` with the given email address.  None if there
        isn't one, or if `fullemail` isn't a proper email address.
    """
    if not fullemail:
        return None

    try:
        # The 2nd arg to s_f_m() doesn't matter as it won't fail since every-
        # thing will have already parsed at this point.
        rfc822, rfc2047, name, email = safe_fix_maintainer(fullemail, "email")
        return getUtility(IPersonSet).getByEmail(email)
    except ParseMaintError:
        return None


def person_to_email(person):
    """Return a string of full name <e-mail address> given an IPerson."""
    if person and person.preferredemail:
        # This will use email.Header to encode any non-ASCII characters.
        return format_address_for_person(person)


def is_auto_sync_upload(spr, bprs, pocket, changed_by_email):
    """Return True if this is a (Debian) auto sync upload.

    Sync uploads are source-only, unsigned and not targeted to
    the security pocket. The Changed-By field is also the Katie
    user (archive@ubuntu.com).
    """
    changed_by = email_to_person(changed_by_email)
    return (
        spr and
        not bprs and
        changed_by == getUtility(ILaunchpadCelebrities).katie and
        pocket != PackagePublishingPocket.SECURITY)


def fetch_information(spr, bprs, changes, previous_version=None):
    changedby = None
    changedby_displayname = None
    maintainer = None
    maintainer_displayname = None

    if changes:
        changesfile = ChangesFile.formatChangesComment(
            sanitize_string(changes.get('Changes')))
        date = changes.get('Date')
        changedby = sanitize_string(changes.get('Changed-By'))
        maintainer = sanitize_string(changes.get('Maintainer'))
        changedby_displayname = changedby
        maintainer_displayname = maintainer
    elif spr or bprs:
        if not spr and bprs:
            spr = bprs[0].build.source_package_release
        changesfile = spr.aggregate_changelog(previous_version)
        date = spr.dateuploaded
        changedby = person_to_email(spr.creator)
        maintainer = person_to_email(spr.maintainer)
        if changedby:
            addr = formataddr((spr.creator.displayname,
                               spr.creator.preferredemail.email))
            changedby_displayname = sanitize_string(addr)
        if maintainer:
            addr = formataddr((spr.maintainer.displayname,
                               spr.maintainer.preferredemail.email))
            maintainer_displayname = sanitize_string(addr)
    else:
        changesfile = date = None

    return {
        'changelog': changesfile,
        'date': date,
        'changedby': changedby,
        'changedby_displayname': changedby_displayname,
        'maintainer': maintainer,
        'maintainer_displayname': maintainer_displayname,
        }


class LanguagePackEncountered(Exception):
    """Thrown when not wanting to email notifications for language packs."""
