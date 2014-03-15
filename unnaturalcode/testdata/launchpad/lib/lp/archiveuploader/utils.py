# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Archive uploader utilities."""

__metaclass__ = type

__all__ = [
    'determine_binary_file_type',
    'determine_source_file_type',
    'DpkgSourceError',
    'extract_dpkg_source',
    'get_source_file_extension',
    'parse_and_merge_file_lists',
    'ParseMaintError',
    'prefix_multi_line_string',
    're_taint_free',
    're_isadeb',
    're_issource',
    're_is_component_orig_tar_ext',
    're_no_epoch',
    're_no_revision',
    're_valid_version',
    're_valid_pkg_name',
    're_changes_file_name',
    're_extract_src_version',
    'safe_fix_maintainer',
    'UploadError',
    'UploadWarning',
    ]


from collections import defaultdict
import email.Header
import os
import re
import signal
import subprocess

from lp.services.encoding import (
    ascii_smash,
    guess as guess_encoding,
    )
from lp.soyuz.enums import BinaryPackageFileType


class UploadError(Exception):
    """All upload errors are returned in this form."""


class UploadWarning(Warning):
    """All upload warnings are returned in this form."""


class DpkgSourceError(Exception):

    _fmt = "Unable to unpack source package (%(result)s): %(output)s"

    def __init__(self, command, output, result):
        super(DpkgSourceError, self).__init__(
            self._fmt % {
                "output": output, "result": result, "command": command})
        self.output = output
        self.result = result
        self.command = command


re_taint_free = re.compile(r"^[-+~/\.\w]+$")

re_isadeb = re.compile(r"(.+?)_(.+?)_(.+)\.(u?d?deb)$")

source_file_exts = [
    'orig(?:-.+)?\.tar\.(?:gz|bz2|xz)', 'diff.gz',
    '(?:debian\.)?tar\.(?:gz|bz2|xz)', 'dsc']
re_issource = re.compile(
    r"([^_]+)_(.+?)\.(%s)" % "|".join(ext for ext in source_file_exts))
re_is_component_orig_tar_ext = re.compile(r"^orig-(.+).tar.(?:gz|bz2|xz)$")
re_is_orig_tar_ext = re.compile(r"^orig.tar.(?:gz|bz2|xz)$")
re_is_debian_tar_ext = re.compile(r"^debian.tar.(?:gz|bz2|xz)$")
re_is_native_tar_ext = re.compile(r"^tar.(?:gz|bz2|xz)$")

re_no_epoch = re.compile(r"^\d+\:")
re_no_revision = re.compile(r"-[^-]+$")

re_valid_version = re.compile(r"^([0-9]+:)?[0-9A-Za-z\.\-\+~:]+$")
re_valid_pkg_name = re.compile(r"^[\dA-Za-z][\dA-Za-z\+\-\.]+$")
re_changes_file_name = re.compile(r"([^_]+)_([^_]+)_([^\.]+).changes")
re_extract_src_version = re.compile(r"(\S+)\s*\((.*)\)")

re_parse_maintainer = re.compile(r"^\s*(\S.*\S)\s*\<([^\>]+)\>")


def get_source_file_extension(filename):
    """Get the extension part of a source file name."""
    match = re_issource.match(filename)
    if match is None:
        return None
    return match.group(3)


def determine_source_file_type(filename):
    """Determine the SourcePackageFileType of the given filename."""
    # Avoid circular imports.
    from lp.registry.interfaces.sourcepackage import SourcePackageFileType

    extension = get_source_file_extension(filename)
    if extension is None:
        return None
    elif extension == "dsc":
        return SourcePackageFileType.DSC
    elif extension == "diff.gz":
        return SourcePackageFileType.DIFF
    elif re_is_orig_tar_ext.match(extension):
        return SourcePackageFileType.ORIG_TARBALL
    elif re_is_component_orig_tar_ext.match(extension):
        return SourcePackageFileType.COMPONENT_ORIG_TARBALL
    elif re_is_debian_tar_ext.match(extension):
        return SourcePackageFileType.DEBIAN_TARBALL
    elif re_is_native_tar_ext.match(extension):
        return SourcePackageFileType.NATIVE_TARBALL
    else:
        return None


def determine_binary_file_type(filename):
    """Determine the BinaryPackageFileType of the given filename."""
    if filename.endswith(".deb"):
        return BinaryPackageFileType.DEB
    elif filename.endswith(".udeb"):
        return BinaryPackageFileType.UDEB
    elif filename.endswith(".ddeb"):
        return BinaryPackageFileType.DDEB
    else:
        return None


def prefix_multi_line_string(str, prefix, include_blank_lines=0):
    """Utility function to split an input string and prefix,

    Each line with a token or tag. Can be used for quoting text etc.
    """
    out = ""
    for line in str.split('\n'):
        line = line.strip()
        if line or include_blank_lines:
            out += "%s%s\n" % (prefix, line)
    # Strip trailing new line
    if out:
        out = out[:-1]
    return out


def extract_component_from_section(section, default_component="main"):
    component = ""
    if section.find("/") != -1:
        component, section = section.split("/")
    else:
        component = default_component

    return (section, component)


def force_to_utf8(s):
    """Forces a string to UTF-8.

    If the string isn't already UTF-8, it's assumed to be ISO-8859-1.
    """
    try:
        unicode(s, 'utf-8')
        return s
    except UnicodeError:
        latin1_s = unicode(s, 'iso8859-1')
        return latin1_s.encode('utf-8')


def rfc2047_encode(s):
    """Encodes a (header) string per RFC2047 if necessary.

    If the string is neither ASCII nor UTF-8, it's assumed to be ISO-8859-1.
    """
    if not s:
        return ''
    try:
        s.decode('us-ascii')
        #encodings.ascii.Codec().decode(s)
        return s
    except UnicodeError:
        pass
    try:
        s.decode('utf8')
        #encodings.utf_8.Codec().decode(s)
        h = email.Header.Header(s, 'utf-8', 998)
        return str(h)
    except UnicodeError:
        h = email.Header.Header(s, 'iso-8859-1', 998)
        return str(h)


class ParseMaintError(Exception):
    """Exception raised for errors in parsing a maintainer field.

    Attributes:
       message -- explanation of the error
    """

    def __init__(self, message):
        Exception.__init__(self)
        self.args = (message, )
        self.message = message


def fix_maintainer(maintainer, field_name="Maintainer"):
    """Parses a Maintainer or Changed-By field and returns:

    (1) an RFC822 compatible version,
    (2) an RFC2047 compatible version,
    (3) the name
    (4) the email

    The name is forced to UTF-8 for both (1) and (3).  If the name field
    contains '.' or ',', (1) and (2) are switched to 'email (name)' format.
    """
    maintainer = maintainer.strip()
    if not maintainer:
        return ('', '', '', '')

    if maintainer.find("<") == -1:
        email = maintainer
        name = ""
    elif (maintainer[0] == "<" and maintainer[-1:] == ">"):
        email = maintainer[1:-1]
        name = ""
    else:
        m = re_parse_maintainer.match(maintainer)
        if not m:
            raise ParseMaintError(
                "%s: doesn't parse as a valid %s field."
                % (maintainer, field_name))
        name = m.group(1)
        email = m.group(2)
        # Just in case the maintainer ended up with nested angles; check...
        while email.startswith("<"):
            email = email[1:]

    # Get an RFC2047 compliant version of the name
    rfc2047_name = rfc2047_encode(name)

    # Force the name to be UTF-8
    name = force_to_utf8(name)

    # If the maintainer's name contains a full stop then the whole field will
    # not work directly as an email address due to a misfeature in the syntax
    # specified in RFC822; see Debian policy 5.6.2 (Maintainer field syntax)
    # for details.
    if name.find(',') != -1 or name.find('.') != -1:
        rfc822_maint = "%s (%s)" % (email, name)
        rfc2047_maint = "%s (%s)" % (email, rfc2047_name)
    else:
        rfc822_maint = "%s <%s>" % (name, email)
        rfc2047_maint = "%s <%s>" % (rfc2047_name, email)

    if email.find("@") == -1 and email.find("buildd_") != 0:
        raise ParseMaintError(
            "%s: no @ found in email address part." % maintainer)

    return (rfc822_maint, rfc2047_maint, name, email)


def safe_fix_maintainer(content, fieldname):
    """Wrapper for fix_maintainer() to handle unicode and string argument.

    It verifies the content type and transform it in a unicode with guess()
    before call ascii_smash(). Then we can safely call fix_maintainer().
    """
    if type(content) != unicode:
        content = guess_encoding(content)

    content = ascii_smash(content)

    return fix_maintainer(content, fieldname)


def extract_dpkg_source(dsc_filepath, target, vendor=None):
    """Extract a source package by dsc file path.

    :param dsc_filepath: Path of the DSC file
    :param target: Target directory
    """

    def subprocess_setup():
        # Python installs a SIGPIPE handler by default. This is usually not
        # what non-Python subprocesses expect.
        # http://www.chiark.greenend.org.uk/ucgi/~cjwatson/ \
        #   blosxom/2009-07-02-python-sigpipe.html
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    args = ["dpkg-source", "-sn", "-x", dsc_filepath]
    env = dict(os.environ)
    if vendor is not None:
        env["DEB_VENDOR"] = vendor
    dpkg_source = subprocess.Popen(
        args, stdout=subprocess.PIPE, cwd=target, stderr=subprocess.PIPE,
        preexec_fn=subprocess_setup, env=env)
    output, unused = dpkg_source.communicate()
    result = dpkg_source.wait()
    if result != 0:
        dpkg_output = prefix_multi_line_string(output, "  ")
        raise DpkgSourceError(result=result, output=dpkg_output, command=args)


def parse_file_list(s, field_name, count):
    if s is None:
        return None
    processed = []
    for line in s.strip().split('\n'):
        split = line.strip().split()
        if len(split) != count:
            raise UploadError(
                "Wrong number of fields in %s field line." % field_name)
        processed.append(split)
    return processed


def merge_file_lists(files, checksums_sha1, checksums_sha256, changes=True):
    """Merge Files, Checksums-Sha1 and Checksums-Sha256 fields.

    Turns lists of (MD5, size, [extras, ...,] filename),
    (SHA1, size, filename) and (SHA256, size, filename) into a list of
    (filename, {algo: hash}, size, [extras, ...], filename).

    Duplicate filenames, size conflicts, and files with missing hashes
    will cause an UploadError.

    'extras' is (section, priority) if changes=True, otherwise it is omitted.
    """
    # Preprocess the additional hashes, counting each (filename, size)
    # that we see.
    file_hashes = defaultdict(dict)
    hash_files = defaultdict(lambda: defaultdict(int))
    for (algo, checksums) in [
            ('SHA1', checksums_sha1), ('SHA256', checksums_sha256)]:
        if checksums is None:
            continue
        for hash, size, filename in checksums:
            file_hashes[filename][algo] = hash
            hash_files[algo][(filename, size)] += 1

    # Produce a file list containing all of the present hashes, counting
    # each filename and (filename, size) that we see. We'll throw away
    # the complete list later if we discover that there are duplicates
    # or mismatches with the Checksums-* fields.
    complete_files = []
    file_counter = defaultdict(int)
    for attrs in files:
        if changes:
            md5, size, section, priority, filename = attrs
        else:
            md5, size, filename = attrs
        file_hashes[filename]['MD5'] = md5
        file_counter[filename] += 1
        hash_files['MD5'][(filename, size)] += 1
        if changes:
            complete_files.append(
                (filename, file_hashes[filename], size, section, priority))
        else:
            complete_files.append(
                (filename, file_hashes[filename], size))

    # Ensure that each filename was only listed in Files once.
    if set(file_counter.itervalues()) - set([1]):
        raise UploadError("Duplicate filenames in Files field.")

    # Ensure that the Checksums-Sha1 and Checksums-Sha256 fields, if
    # present, list the same filenames and sizes as the Files field.
    for field, algo in [
            ('Checksums-Sha1', 'SHA1'), ('Checksums-Sha256', 'SHA256')]:
        if algo in hash_files and hash_files[algo] != hash_files['MD5']:
            raise UploadError("Mismatch between %s and Files fields." % field)
    return complete_files


def parse_and_merge_file_lists(tag_dict, changes=True):
    files_lines = parse_file_list(
        tag_dict['Files'], 'Files', 5 if changes else 3)
    sha1_lines = parse_file_list(
        tag_dict.get('Checksums-Sha1'), 'Checksums-Sha1', 3)
    sha256_lines = parse_file_list(
        tag_dict.get('Checksums-Sha256'), 'Checksums-Sha256', 3)
    return merge_file_lists(
        files_lines, sha1_lines, sha256_lines, changes=changes)
