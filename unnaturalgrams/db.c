/* db.c -- Database Interface for UnnaturalGrams
 * 
 * Copyright 2014 Joshua Charles Campbell
 *
 * This file is part of UnnaturalCode.
 *
 * UnnaturalCode is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * 
 * UnnaturalCode is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with UnnaturalCode.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "db.h"
#include "copper.h"

#include <sys/stat.h>
#include <unistd.h>
#include <string.h>

void ug_commit(struct UGCorpus * corpus) {
  Ad(( corpus->inTxn  ));
  if (corpus->readOnly) {
    mdb_txn_reset(corpus->mdbTxn);
  } else {  
    Ad(( mdb_txn_commit(corpus->mdbTxn) == 0 ));
    corpus->mdbTxn = NULL;
  }
  corpus->inTxn = 0;
}

void ug_abort(struct UGCorpus * corpus) {
  mdb_txn_abort(corpus->mdbTxn);
  corpus->mdbTxn = NULL;
  corpus->inTxn = 0;
}

void ug_beginRW(struct UGCorpus * corpus) {
  Ad(( ! corpus->inTxn  ));
  if (corpus->readOnly) {
    corpus->readOnly = 0;
    ug_abort(corpus);
  }
  Ad(( corpus->mdbTxn == NULL ));
  Ad(( mdb_txn_begin(corpus->mdbEnv, NULL, 0, &(corpus->mdbTxn)) == 0 ));
  corpus->inTxn = 1;
}

void ug_beginRO(struct UGCorpus * corpus) {
  if (corpus->readOnly) {
    Ad(( corpus->mdbTxn != NULL ));
    mdb_txn_reset(corpus->mdbTxn);
  } else {
    Ad(( corpus->mdbTxn == NULL ));
    Ad(( mdb_txn_begin(corpus->mdbEnv, NULL, MDB_RDONLY, &(corpus->mdbTxn)) == 0 ));    
    corpus->readOnly = 1;
  }
  corpus->inTxn = 1;
}


int ug_openDB(char * path, struct UGCorpus * corpus) {
  struct stat s;
  MDB_txn * mdbTxn = NULL;
  
  ASYS(( stat(path, &s) == 0 ));
  ASYS(( access(path, R_OK | W_OK | X_OK) == 0 ));

  Ad(( mdb_env_create(&(corpus->mdbEnv)) == 0 ));
  Ad(( S_ISDIR(s.st_mode) ));
  Ad(( mdb_env_open(corpus->mdbEnv, path, 0, 0666) == 0 ));
  Ad(( mdb_txn_begin(corpus->mdbEnv, NULL, 0, &mdbTxn) == 0 ));
  Ad(( mdb_dbi_open(mdbTxn, NULL, 0, &(corpus->mdbDbi)) == 0 ));
  Ad(( mdb_txn_commit(mdbTxn) == 0 )); mdbTxn = NULL;
  
  return 0;
}

int ug_closeDB(struct UGCorpus * corpus) {
      mdb_env_close(corpus->mdbEnv); 
      corpus->mdbEnv = NULL;
      return 0;
}

int ug_existsByC(struct  UGCorpus * corpus, char * cKey) {
  struct MDB_val key;
  struct MDB_val data;
  int r;

  key.mv_data = cKey;
  key.mv_size = strlen(key.mv_data)+1;  
  
  r = mdb_get(corpus->mdbTxn, corpus->mdbDbi, &key, &data);
  
  if (r == 0) {
    return 1;
  } else if (r == MDB_NOTFOUND) {
    return 0;
  }
  E(("LMDB Error %i: %s", r, mdb_strerror(r)));
  return 0;
}

uint64_t ug_readUInt64ByC(struct  UGCorpus * corpus, char * cKey) {
  struct MDB_val key;
  struct MDB_val data;
  int r;

  key.mv_data = cKey;
  key.mv_size = strlen(key.mv_data)+1;  
  
  r = mdb_get(corpus->mdbTxn, corpus->mdbDbi, &key, &data);
  
  if (r == 0) {
    Ad(( data.mv_size == sizeof(uint64_t) ));
    return *((uint64_t *) data.mv_data);
  }
  E(("LMDB Error %i: %s", r, mdb_strerror(r)));
  return 0;
}

void ug_writeUInt64ByC(struct  UGCorpus * corpus, char * cKey, uint64_t value) {
  struct MDB_val key;
  struct MDB_val data;
  int r;

  key.mv_data = cKey;
  key.mv_size = strlen(key.mv_data)+1;  
  
  data.mv_data = &value;
  data.mv_size = sizeof(value);
  
  r = mdb_put(corpus->mdbTxn, corpus->mdbDbi, &key, &data, MDB_NOOVERWRITE);
  
  if (r != 0) {
    E(("LMDB Error %i: %s", r, mdb_strerror(r)));
  }
}


int ug_createDB(char * path, struct UGCorpus * corpus) {
  MDB_txn * mdbTxn = NULL;
  MDB_env * mdbEnv = NULL;
  MDB_dbi mdbDbi = 0;
  
  ASYS(( mkdir(path, 0777) == 0 ));
  
  Ad(( mdb_env_create(&mdbEnv) == 0 ));
  Ad(( mdb_env_open(mdbEnv, path, 0, 0666) == 0 ));
  Ad(( mdb_txn_begin(mdbEnv, NULL, 0, &mdbTxn) == 0 ));
  Ad(( mdb_dbi_open(mdbTxn, NULL, MDB_CREATE, &(mdbDbi)) == 0 ));
  Ad(( mdb_txn_commit(mdbTxn) == 0 )); mdbTxn = NULL;
  mdb_env_close(mdbEnv); mdbEnv = NULL;
  
  return ug_openDB(path, corpus);
}
