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
  
  corpus->open = 1;
  return 0;
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
