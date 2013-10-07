# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""lp.services namespace package

WARNING: This is a namespace package, it should only include other packages,
but no actual code or modules.

In this namespace live the packages providing system-level services to the
rest of the Launchpad application. Things like languages, countries, geoip,
GPG handling, email, etc.

Packages in this namespace can only use general LAZR or library functionality.
"""
