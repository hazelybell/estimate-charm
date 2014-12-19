/* attribute.h -- UnnaturalGram attribute (type of feature) 
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

#ifndef _CORPUS_H_
#define _CORPUS_H_

#include "ug.h"

/* Instance/Context for a UG corpus */
struct ug_Corpus {
  ug_AttributeID nAttributes;
  ug_GramOrder gramOrder;
  int open;
  MDB_env * mdbEnv;
  MDB_dbi mdbDbi;
  MDB_txn * mdbTxn;
  int readOnlyTxn;
  int inTxn;
  struct ug_VectorElement **** dirtyChunks;
};

#endif /* _CORPUS_H_ */