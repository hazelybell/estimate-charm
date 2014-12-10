/* ug.h -- Data Structures for UnnaturalGrams
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

#ifndef _UG_H_
#define _UG_H_

#include <stdint.h>
#include <stddef.h>
#include <lmdb.h>

typedef uint64_t UGPropertyID;

/* A single value for a single property for a 1-gram
 * datastructure for API */
struct UGOneGramProperty {
  UGPropertyID id;
  size_t length;
  char * value;
};

/* Basic 1-gram datastructure for API */
struct UGOneGram {
  size_t nProperties;
  struct UGOneGramProperty * properties;
};

/* Weighted 1-gram datastructure for API */
struct UGOneGramWeighted {
  size_t nProperties;
  double weight;
  struct UGOneGramProperty * properties;
};

/* Basic n-gram datastructure for API */
struct UGram {
  size_t length;
  struct UGOneGram * words;
};

/* Weighted n-gram datastructure for API */
struct UGramWeighted {
  size_t length;
  struct UGOneGramWeighted * words;
};

/* The base-2 logarithm of numbers which we consider practically infinite. */
#define UG_INFINITY 70.0

/* Instance/Context for UG */
struct UGCorpus {
  UGPropertyID nProperties;
  size_t gramOrder;
  int open;
  MDB_env * mdbEnv;
  MDB_dbi mdbDbi;
  MDB_txn * mdbTxn;
  int readOnly;
  int inTxn;
};

struct UGPrediction {
  double score;
  struct UGram gram;
};

struct UGPredictions {
  size_t nPredictions;
  struct UGPrediction * predictions;
};

#endif /* _UG_H_ */
