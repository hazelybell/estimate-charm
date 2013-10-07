-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE OR REPLACE FUNCTION public.bug_summary_dec(bugsummary)
 RETURNS void
 LANGUAGE sql
AS $function$
    -- We own the row reference, so in the absence of bugs this cannot
    -- fail - just decrement the row.
    UPDATE BugSummary SET count = count + $1.count
    WHERE
        ((product IS NULL AND $1.product IS NULL)
            OR product = $1.product)
        AND ((productseries IS NULL AND $1.productseries IS NULL)
            OR productseries = $1.productseries)
        AND ((distribution IS NULL AND $1.distribution IS NULL)
            OR distribution = $1.distribution)
        AND ((distroseries IS NULL AND $1.distroseries IS NULL)
            OR distroseries = $1.distroseries)
        AND ((sourcepackagename IS NULL AND $1.sourcepackagename IS NULL)
            OR sourcepackagename = $1.sourcepackagename)
        AND ((viewed_by IS NULL AND $1.viewed_by IS NULL)
            OR viewed_by = $1.viewed_by)
        AND ((tag IS NULL AND $1.tag IS NULL)
            OR tag = $1.tag)
        AND status = $1.status
        AND ((milestone IS NULL AND $1.milestone IS NULL)
            OR milestone = $1.milestone)
        AND importance = $1.importance
        AND has_patch = $1.has_patch
        AND access_policy IS NOT DISTINCT FROM $1.access_policy;
$function$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 32, 0);
