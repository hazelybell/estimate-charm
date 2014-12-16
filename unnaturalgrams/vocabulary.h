/* wordmap.h -- Word indexing routines
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

#ifndef _VALUEULARY_H_
#define _VALUEULARY_H_

#include "ug.h"
#include "smoothing.h"

#define ug_VALUE_KEY_PREFIX_LENGTH (16)

#define ug_MAX_WORD_LENGTH (511-ug_VALUE_KEY_PREFIX_LENGTH)

#define ug_VALUE_UNKNOWN ((uint64_t) 0)

struct __attribute__((packed)) ug_ValueCountKey {
  ug_KeyMagic magic; /* should be ug_VALUE_COUNT */
  ug_AttributeID attributeID;
};

struct __attribute__((packed)) ug_ValueKey {
  ug_KeyMagic magic; /* should be ug_VALUE */
  ug_AttributeID attributeID;
  char value[ug_MAX_WORD_LENGTH];
};

struct __attribute__((packed)) ug_ValueID {
  ug_KeyMagic magic; /* should be ug_VALUE_ID */
  ug_AttributeID attributeID;
  ug_ValueID id;
};

struct __attribute__((packed)) ug_IDKey {
  ug_KeyMagic magic; /* should be ug_VALUE_ID */
  ug_AttributeID attributeID;
  ug_ValueID id;
};

void ug_mapValuesToIDsOrCreate(struct ug_Corpus * corpus,
                       ug_AttributeID attr,
                       size_t length,
                       struct ug_Value string[length],
                       ug_ValueID (* ids)[length]
                       );


#endif /* _VALUEULARY_H_ */