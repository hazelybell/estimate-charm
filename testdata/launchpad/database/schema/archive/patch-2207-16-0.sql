SET client_min_messages=ERROR;

-- Fill the mirror tables with data.
INSERT INTO lp_TeamParticipation SELECT * FROM TeamParticipation;
INSERT INTO lp_PersonLocation SELECT * FROM PersonLocation;
INSERT INTO lp_Person SELECT * FROM Person;


-- INSERT triggers
CREATE TRIGGER lp_mirror_teamparticipation_ins_t
AFTER INSERT ON TeamParticipation
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_teamparticipation_ins();

CREATE TRIGGER lp_mirror_personlocation_ins_t
AFTER INSERT ON PersonLocation
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_personlocation_ins();

CREATE TRIGGER lp_mirror_person_ins_t
AFTER INSERT ON Person
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_person_ins();


-- UPDATE triggers
CREATE TRIGGER lp_mirror_teamparticipation_upd_t
AFTER UPDATE ON TeamParticipation
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_teamparticipation_upd();

CREATE TRIGGER lp_mirror_personlocation_upd_t
AFTER UPDATE ON PersonLocation
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_personlocation_upd();

CREATE TRIGGER lp_mirror_person_upd_t
AFTER UPDATE ON Person
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_person_upd();

-- DELETE triggers
CREATE TRIGGER lp_mirror_teamparticipation_del_t
AFTER DELETE ON TeamParticipation
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_del();

CREATE TRIGGER lp_mirror_personlocation_del_t
AFTER DELETE ON TeamParticipation
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_del();

CREATE TRIGGER lp_mirror_person_del_t
AFTER DELETE ON Person
FOR EACH ROW EXECUTE PROCEDURE lp_mirror_del();

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 16, 0);

