/* db.h -- Database interface
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

#ifndef _DB_H_
#define _DB_H_

#include "ug.h"

int ug_openDB(char * path, struct UGCorpus * corpus);
int ug_closeDB(struct UGCorpus * corpus);
int ug_createDB(char * path, struct UGCorpus * corpus);

void ug_beginRO(struct UGCorpus * corpus);
void ug_beginRW(struct UGCorpus * corpus);
void ug_commit(struct UGCorpus * corpus);

uint64_t ug_readUInt64ByC(struct  UGCorpus * corpus, char * cKey);
void ug_writeUInt64ByC(struct  UGCorpus * corpus, char * cKey, uint64_t value);

#endif /* _DB_H_ */