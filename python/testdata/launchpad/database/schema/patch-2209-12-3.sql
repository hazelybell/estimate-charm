-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE OR REPLACE FUNCTION bug_maintain_bug_summary() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO public
    AS $$
BEGIN
    -- There is no INSERT logic, as a bug will not have any summary
    -- information until BugTask rows have been attached.
    IF TG_OP = 'UPDATE' THEN
        IF OLD.duplicateof IS DISTINCT FROM NEW.duplicateof
            OR OLD.information_type IS DISTINCT FROM NEW.information_type
            OR (OLD.latest_patch_uploaded IS NULL)
                <> (NEW.latest_patch_uploaded IS NULL) THEN
            PERFORM unsummarise_bug(OLD);
            PERFORM summarise_bug(NEW);
        END IF;

    ELSIF TG_OP = 'DELETE' THEN
        PERFORM unsummarise_bug(OLD);
    END IF;

    PERFORM bug_summary_flush_temp_journal();
    RETURN NULL; -- Ignored - this is an AFTER trigger
END;
$$;

CREATE OR REPLACE FUNCTION bugsubscription_maintain_bug_summary() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO public
    AS $$
BEGIN
    -- This trigger only works if we are inserting, updating or deleting
    -- a single row per statement.
    IF TG_OP = 'INSERT' THEN
        IF (bug_row(NEW.bug)).information_type IN (1, 2) THEN
            -- Public subscriptions are not aggregated.
            RETURN NEW;
        END IF;
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(NEW.bug));
        ELSE
            PERFORM summarise_bug(bug_row(NEW.bug));
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        IF (bug_row(OLD.bug)).information_type IN (1, 2) THEN
            -- Public subscriptions are not aggregated.
            RETURN OLD;
        END IF;
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(OLD.bug));
        ELSE
            PERFORM summarise_bug(bug_row(OLD.bug));
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN OLD;
    ELSE
        IF (OLD.person IS DISTINCT FROM NEW.person
            OR OLD.bug IS DISTINCT FROM NEW.bug) THEN
            IF TG_WHEN = 'BEFORE' THEN
                IF (bug_row(OLD.bug)).information_type IN (3, 4, 5) THEN
                    -- Public subscriptions are not aggregated.
                    PERFORM unsummarise_bug(bug_row(OLD.bug));
                END IF;
                IF OLD.bug <> NEW.bug AND (bug_row(NEW.bug)).information_type IN (3, 4, 5) THEN
                    -- Public subscriptions are not aggregated.
                    PERFORM unsummarise_bug(bug_row(NEW.bug));
                END IF;
            ELSE
                IF (bug_row(OLD.bug)).information_type IN (3, 4, 5) THEN
                    -- Public subscriptions are not aggregated.
                    PERFORM summarise_bug(bug_row(OLD.bug));
                END IF;
                IF OLD.bug <> NEW.bug AND (bug_row(NEW.bug)).information_type IN (3, 4, 5) THEN
                    -- Public subscriptions are not aggregated.
                    PERFORM summarise_bug(bug_row(NEW.bug));
                END IF;
            END IF;
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN NEW;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION bugsummary_viewers(bug_row bug) RETURNS SETOF bugsubscription
    LANGUAGE sql STABLE
    AS $_$
    SELECT *
    FROM BugSubscription
    WHERE
        bugsubscription.bug=$1.id
        AND $1.information_type IN (3, 4, 5);
$_$;

CREATE OR REPLACE FUNCTION calculate_bug_heat(bug_id integer) RETURNS integer
 LANGUAGE sql STABLE STRICT AS $$
    SELECT
        (CASE information_type WHEN 1 THEN 0 WHEN 2 THEN 250
            WHEN 3 THEN 400 ELSE 150 END)
        + (number_of_duplicates * 6)
        + (users_affected_count * 4)
        + (
            SELECT COUNT(DISTINCT person) * 2 
            FROM BugSubscription
            JOIN Bug AS SubBug ON BugSubscription.bug = SubBug.id
            WHERE SubBug.id = $1 OR SubBug.duplicateof = $1)::integer AS heat
    FROM Bug WHERE Bug.id = $1;
$$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 12, 3);
