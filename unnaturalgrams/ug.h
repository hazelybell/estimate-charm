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

/* ID of attribute (determinable) 
   e.g. 0 = spelling 
        1 = part of speech */
typedef uint64_t ug_AttributeID; 

/* ID of the value (determinant) that the attribute takes
   e.g. 0 = "aaaaa"
        1 = "aaaab" */
typedef uint64_t ug_Vocab;

typedef uint64_t ug_GramOrder;

typedef uint32_t ug_KeyMagic;

typedef uint64_t ug_Index;

/* A single value (determinant) for a single property for a 1-gram
 * datastructure for API.
 * This is the not-yet-indexed form of ug_Vocab. */
struct ug_Feature {
  size_t length;
  char * value;
};

/* Basic 1-gram datastructure for API */
struct ug_Word {
  size_t nAttributes;
  struct ug_Feature * values;
};

/* Weighted 1-gram datastructure for API */
struct ug_WordWeighted {
  size_t nAttributes;
  double weight;
  struct ug_Feature * values;
};

/* Basic n-gram datastructure for API */
struct ug_Gram {
  size_t length;
  struct ug_Word * words;
};

/* Weighted n-gram datastructure for API */
struct ug_GramWeighted {
  size_t length;
  struct ug_WordWeighted * words;
};

/* The base-2 logarithm of numbers which we consider practically infinite. */
#define UG_INFINITY 70.0

struct ug_Prediction {
  double score;
  struct ug_Gram gram;
};

struct ug_Predictions {
  size_t nPredictions;
  struct ug_Prediction * predictions;
};

typedef enum {
  ug_VECTOR,
  ug_VECTOR_LENGTH,
  ug_VOCAB, /* for mapping words to vocab IDs */
  ug_VOCAB_COUNT, /* for storing the current size of the vocabulary */
  ug_FEATURE, /* for mapping IDs back to real words */
  ug_GRAM_LOOKUP, /* for mapping (vocab, history) pairs to indices in the vector */
} ug_KeyType;


#endif /* _UG_H_ */
