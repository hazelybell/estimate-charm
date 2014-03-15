# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


def valid_debian_version(version):
    """
    Returns True if version is a valid debian version string

    As per http://www.debian.org/doc/debian-policy/ch-controlfields.html
    (Except we appear to need to allow ~ characters, which is not documented
    in the spec.)

    >>> valid_debian_version('1')
    True
    >>> valid_debian_version('1.0')
    True
    >>> valid_debian_version('1:1.0')
    True
    >>> valid_debian_version('1.0-1')
    True
    >>> valid_debian_version("1:1.0-1")
    True
    >>> valid_debian_version("3.4-2.1")
    True
    >>> valid_debian_version("1.5.4-1.woody.0")
    True
    >>> valid_debian_version("1.5.4-1.WOODY.0")
    True
    >>> valid_debian_version("1.6-0+1.5a-4")
    True
    >>> valid_debian_version("1.3~rc1-4")
    True
    >>> valid_debian_version("1:")
    False
    >>> valid_debian_version("1:-")
    False
    >>> valid_debian_version("44-")
    False
    >>> valid_debian_version("~-~")
    False
    >>> valid_debian_version("0~")
    True
    >>> valid_debian_version("0~-~")
    True
    >>> valid_debian_version(":44")
    False
    >>> valid_debian_version("foo:")
    False
    >>> valid_debian_version("12:12:alpha-alpha")
    True
    >>> valid_debian_version("build9-6")
    True
    """
    import re
    m = re.search("""^(?ix)
        ([0-9]+:)?
        ([0-9a-z][a-z0-9+:.~-]*?)
        (-[a-z0-9+.~]+)?
        $""", version)
    if m is None:
        return False
    epoch, version, revision = m.groups()
    if not epoch:
        # Can't contain : if no epoch
        if ":" in version:
            return False
    if not revision:
        # Can't contain - if no revision
        if "-" in version:
            return False
    return True


def sane_version(version):
    '''A sane version number for use by ProductRelease and DistroSeries.

    We may make it less strict if required, but it would be nice if we can
    enforce simple version strings because we use them in URLs

    >>> sane_version('hello')
    True
    >>> sane_version('HELLO')
    True
    >>> sane_version('1.0')
    True
    >>> sane_version('12:45')
    False
    >>> sane_version('1b2')
    True
    >>> sane_version('1-')
    False
    >>> sane_version('1-2')
    True
    >>> sane_version('-2')
    False
    >>> sane_version('uncle sam')
    False
    >>> sane_version('uncle_sam')
    True
    >>> sane_version('uncle-sam')
    True
    '''
    import re
    if re.search("""^(?ix)
        [0-9a-z]
        ( [0-9a-z] | [0-9a-z._-]*[0-9a-z] )*
        $""", version):
        return True
    return False

