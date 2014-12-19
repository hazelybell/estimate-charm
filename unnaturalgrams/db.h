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
#include "corpus.h"

int ug_openDB(char * path, struct ug_Corpus * corpus);
int ug_closeDB(struct ug_Corpus * corpus);
int ug_createDB(char * path, struct ug_Corpus * corpus);

void ug_beginRO(struct ug_Corpus * corpus);
void ug_beginRW(struct ug_Corpus * corpus);
void ug_commit(struct ug_Corpus * corpus);

void * ug_readNOrNull(struct  ug_Corpus * corpus, size_t keyLength, void * keyData,
              size_t valueSize);
void * ug_readN(struct  ug_Corpus * corpus, size_t keyLength, void * keyData,
              size_t valueSize);
uint64_t ug_readUInt64ByC(struct  ug_Corpus * corpus, char * cKey);
#define ug_readStructByStruct(corpus, key, value) ( \
      value = *((typeof(&value)) ug_readN(corpus, \
                                          sizeof(key), &key, \
                                          sizeof(value)))\
    )
uint64_t ug_readUInt64(struct  ug_Corpus * corpus,
                       size_t keyLength, void * keyData);
uint64_t ug_readUInt64OrZero(struct  ug_Corpus * corpus,
                       size_t keyLength, void * keyData);
                                                            

void ug_write(struct  ug_Corpus * corpus, size_t keyLength, void * keyData,
              size_t valueLength, void * valueData);
void ug_writeUInt64ByC(struct  ug_Corpus * corpus, char * cKey, uint64_t value);
#define ug_writeStructByStruct(corpus, key, value) (ug_write(corpus, \
                                                     sizeof(key), &key, \
                                                     sizeof(value), &value))
                                                     
void ug_writeUInt64(struct  ug_Corpus * corpus,
                        size_t keyLength, void * keyData,
                        uint64_t value);

void ug_overwriteUInt64(struct  ug_Corpus * corpus,
                        size_t keyLength, void * keyData,
                        uint64_t value);

void * ug_overwriteBuffer(
  struct  ug_Corpus * corpus,
  size_t keyLength,
  void * keyData,
  size_t valueLength
);

#endif /* _DB_H_ */