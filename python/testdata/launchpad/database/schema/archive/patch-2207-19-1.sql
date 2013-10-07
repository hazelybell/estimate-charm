SET client_min_messages=ERROR;

CREATE INDEX bugtask__bugwatch__idx
ON BugTask(bugwatch) WHERE bugwatch IS NOT NULL;

CREATE INDEX translationimportqueueentry__productseries__idx
ON TranslationImportQueueEntry(productseries)
WHERE productseries IS NOT NULL;

CREATE INDEX translationimportqueueentry__sourcepackagename__idx
ON TranslationImportQueueEntry(sourcepackagename)
WHERE sourcepackagename IS NOT NULL;

CREATE INDEX translationimportqueueentry__path__idx
ON TranslationImportQueueEntry(path);

CREATE INDEX translationimportqueueentry__pofile__idx
ON TranslationImportQueueEntry(pofile)
WHERE pofile IS NOT NULL;

CREATE INDEX translationimportqueueentry__potemplate__idx
ON TranslationImportQueueEntry(potemplate)
WHERE potemplate IS NOT NULL;

CREATE INDEX pofile__from_sourcepackagename__idx
ON POFile(from_sourcepackagename)
WHERE from_sourcepackagename IS NOT NULL;

CREATE INDEX bugwatch__lastchecked__idx ON BugWatch(lastchecked);
CREATE INDEX bugwatch__remotebug__idx ON BugWatch(remotebug);
CREATE INDEX bugwatch__remote_lp_bug_id__idx ON BUgWatch(remote_lp_bug_id)
WHERE remote_lp_bug_id IS NOT NULL;


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 19, 1);
