SET client_min_messages=ERROR;

/*
The new table, lp_Account, will need to be manually added to a new
replication set. We cannot add it to the existing lpmirror replication
set because that set currently originates on launchpad_prod_3 (because
it is maintained by triggers on lpmain tables and has to have the same
origin). The new table is maintained on triggers on the Account tables
in the authdb replication set so needs the same origin - launchpad_prod_4

Normally, we couldn't alter tables in the authdb replication set.
This is a special case. We actually only want this change made
to nodes that have both the lpmain and authdb replication sets,
and not on nodes that just have the authdb replication set. Those
latter nodes will be split out shortly and should not have the
new trigger.
*/

/* Table is created in patch-2207-35-2.sql. We needed to install the
table on production before the rollout to ensure database permissions
where setup. We just populate it with data here. */
INSERT INTO lp_Account SELECT id, openid_identifier FROM Account;

CREATE TRIGGER lp_mirror_account_ins_t
AFTER INSERT ON Account
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_account_ins();

CREATE TRIGGER lp_mirror_account_upd_t
AFTER UPDATE ON Account
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_account_upd();

CREATE TRIGGER lp_mirror_account_del_t
AFTER DELETE ON Account
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_del();


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 44, 0);
