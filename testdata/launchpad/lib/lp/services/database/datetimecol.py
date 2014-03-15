# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

'''UtcDateTimeCol for SQLObject'''

__all__ = ['UtcDateTimeCol']

import pytz
import storm.sqlobject


class UtcDateTimeCol(storm.sqlobject.UtcDateTimeCol):
    _kwargs = {'tzinfo': pytz.timezone('UTC')}
