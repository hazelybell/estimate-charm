# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['TranslationsOverview']

from zope.interface import implements

from lp.app.enums import (
    InformationType,
    ServiceUsage,
    )
from lp.registry.model.distribution import Distribution
from lp.registry.model.product import Product
from lp.services.database.sqlbase import (
    cursor,
    sqlvalues,
    )
from lp.translations.interfaces.translationsoverview import (
    ITranslationsOverview,
    MalformedKarmaCacheData,
    )


class TranslationsOverview:
    implements(ITranslationsOverview)

    # Project weights will be scaled into [MINIMUM_SIZE, MAXIMUM_SIZE] range.
    MINIMUM_SIZE = 10
    MAXIMUM_SIZE = 18

    def _normalizeSizes(self, pillars, minimum, maximum):
        """Normalize pillar sizes into range [MINIMUM_SIZE, MAXIMUM_SIZE]."""
        if maximum == minimum:
            multiplier = 0
            offset = 0
            real_minimum = (self.MAXIMUM_SIZE + self.MINIMUM_SIZE) / 2.0
        else:
            offset = minimum - self.MINIMUM_SIZE
            multiplier = (float(self.MAXIMUM_SIZE - self.MINIMUM_SIZE) /
                          (maximum - minimum))
            real_minimum = self.MINIMUM_SIZE

        normalized_sizes = []
        for (pillar, size) in pillars:
            new_size = int(round(
                real_minimum +
                (size - offset - real_minimum) * multiplier))
            normalized_sizes.append({'pillar': pillar, 'weight': new_size})
        return normalized_sizes

    def getMostTranslatedPillars(self, limit=50):
        """See `ITranslationsOverview`."""

        # XXX Abel Deuring 2012-10-26 bug=1071751
         # The expression product.information_type IS NULL can be
         # removed once we have the DB constraint
         # "Product.information_type IS NULL".
        query = """
        SELECT LOWER(COALESCE(product_name, distro_name)) AS name,
               product_id,
               distro_id,
               LN(total_karma)/LN(2) AS karma
          FROM (
            SELECT
                product.displayname AS product_name,
                product.id AS product_id,
                distribution.displayname AS distro_name,
                distribution.id AS distro_id,
                SUM(karmavalue) AS total_karma
              FROM karmacache
                   LEFT JOIN product ON
                     product=product.id
                   LEFT JOIN distribution ON
                     distribution=distribution.id
              WHERE category=3 AND
                    (product IS NOT NULL OR distribution IS NOT NULL) AND
                    (product.translations_usage = %s AND
                     (product.information_type = %s OR
                      product.information_type IS NULL) OR
                    distribution.translations_usage = %s)
              GROUP BY product.displayname, product.id,
                       distribution.displayname, distribution.id
              HAVING SUM(karmavalue) > 0
              ORDER BY total_karma DESC
              LIMIT %s) AS something
          ORDER BY name""" % sqlvalues(ServiceUsage.LAUNCHPAD,
                                       InformationType.PUBLIC,
                                       ServiceUsage.LAUNCHPAD,
                                       limit)
        cur = cursor()
        cur.execute(query)

        all_pillars = []

        # Get minimum and maximum relative karma value to be able to normalize
        # them to appropriate font size values.
        minimum = None
        maximum = None
        for (name, product_id, distro_id, relative_karma) in cur.fetchall():
            if minimum is None or relative_karma < minimum:
                minimum = relative_karma
            if maximum is None or relative_karma > maximum:
                maximum = relative_karma
            if product_id is not None:
                pillar = Product.get(product_id)
            elif distro_id is not None:
                pillar = Distribution.get(distro_id)
            else:
                raise MalformedKarmaCacheData(
                    "Lots of karma for non-existing product or distribution.")
            all_pillars.append((pillar, relative_karma))

        # Normalize the relative karma values between MINIMUM_SIZE and
        # MAXIMUM_SIZE.
        return self._normalizeSizes(all_pillars, minimum, maximum)
