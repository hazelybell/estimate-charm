/* smoothing.h -- Smoothing-related routines
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

#ifndef _SMOOTHING_H_
#define _SMOOTHING_H_

#include "ug.h"

#define ug_CHUNKSIZE (1024*1024)
#define ug_MAX_ORDER (0xFFFFFFFF)


struct __attribute__((packed)) ug_VectorKey {
  ug_KeyMagic magic; /* should be ug_VECTOR */
  ug_AttributeID attributeID;
  ug_GramOrder gramOrder;
  ug_Index startOffset;
};

struct __attribute__((packed)) ug_VectorElement {
  ug_Index historyIndex;
  ug_ValueID word;
  double probability;
  double backoffWeight;
  ug_Index backoffIndex;
};

struct __attribute__((packed)) ug_VectorLengthKey {
  ug_KeyMagic magic; /* should be ug_VECTOR_LENGTH */
  ug_AttributeID attributeID;
  ug_GramOrder gramOrder;
};

struct __attribute__((packed)) ug_VectorLength {
  ug_Index vectorLength; /* for allocation */
};

ug_GramOrder ug_setSmoothing(struct ug_Corpus * corpus, ug_GramOrder order);
void ug_initSmoothing(struct ug_Corpus * corpus);

#endif /* _SMOOTHING_H_ */
