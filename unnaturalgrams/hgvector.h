/* hgvector.h -- UnnaturalGram Hsu-Glass Vector
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

#ifndef _HGVECTOR_H_
#define _HGVECTOR_H_

#include "attribute.h"

#define ug_CHUNKSIZE (1024)
#define ug_MAX_ORDER (0xFFFFFFFF)

#define ug_NGRAM_UNKNOWN ((ug_Index) 0)

struct __attribute__((packed)) ug_VectorKey {
  ug_KeyMagic magic; /* should be ug_VECTOR */
  ug_AttributeID attributeID;
  ug_GramOrder gramOrder; /* 1-based! */
  ug_Index startOffset;
};

struct __attribute__((packed)) ug_VectorElement {
  ug_Index historyIndex;
  ug_Vocab vocab;
  double weight;
  double backoffWeight;
  ug_Index backoffIndex;
};

struct __attribute__((packed)) ug_VectorLengthKey {
  ug_KeyMagic magic; /* should be ug_VECTOR_LENGTH */
  ug_AttributeID attributeID;
  ug_GramOrder gramOrder; /* 1-based! */
};

struct __attribute__((packed)) ug_VectorLength {
  ug_Index vectorLength; /* for allocation */
};

struct __attribute__((packed)) ug_GramKey {
  ug_KeyMagic magic; /* should be ug_GRAM_LOOKUP */
  ug_AttributeID attributeID;
  ug_GramOrder gramOrder; /* 1-based! */
  ug_Vocab vocab;
  ug_Index historyIndex;
};


/* Instance/Context for a UG Hsu-Glass order vector */
struct ug_HGVector {
  struct ug_Attribute;
  ug_GramOrder order; /* 1-based! */
};

struct ug_HGVector ug_getHGVector (
  struct ug_Attribute attribute,
  ug_GramOrder order /* 1-based! */
);

ug_Index ug_lookupGram (
  struct ug_HGVector v,
  ug_Vocab vocab,
  ug_Index history
);

ug_Index ug_addElement (
  struct ug_HGVector v,
  struct ug_VectorElement data
);

struct ug_VectorElement * ug_getElement (
  struct ug_HGVector v,
  ug_Index index
);

void ug_updateElement (
  struct ug_HGVector v,
  ug_Index index,
  struct ug_VectorElement data
);

#endif /* _HGVECTOR_H_ */