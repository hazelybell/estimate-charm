/* vocabulary.h -- Word indexing routines
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

#ifndef _VOCABULARY_H_
#define _VOCABULARY_H_

#include "ug.h"
#include "hsuglass.h"

#define ug_VOCAB_KEY_PREFIX_LENGTH \
    (sizeof(ug_KeyMagic) + sizeof(ug_AttributeID))

#define ug_MAX_WORD_LENGTH (511-ug_VOCAB_KEY_PREFIX_LENGTH)

#define ug_VOCAB_UNKNOWN ((uint64_t) 0)

struct __attribute__((packed)) ug_VocabCountKey {
  ug_KeyMagic magic; /* should be ug_VOCAB_COUNT */
  ug_AttributeID attributeID;
};

struct __attribute__((packed)) ug_FeatureKey {
  ug_KeyMagic magic; /* should be ug_VOCAB */
  ug_AttributeID attributeID;
  char value[ug_MAX_WORD_LENGTH];
};

struct __attribute__((packed)) ug_Vocab {
  ug_KeyMagic magic; /* should be ug_VOCAB */
  ug_AttributeID attributeID;
  ug_Vocab id;
};

struct __attribute__((packed)) ug_VocabKey {
  ug_KeyMagic magic; /* should be ug_VOCAB */
  ug_AttributeID attributeID;
  ug_Vocab id;
};

void ug_initVocab(struct ug_Corpus * corpus,
                                 ug_AttributeID attr);

ug_Vocab ug_mapFeatureToVocab(struct ug_Corpus * corpus,
                     ug_AttributeID attr,
                     struct ug_Feature v);


void ug_mapFeaturesToVocabsOrCreate(struct ug_Corpus * corpus,
                       ug_AttributeID attr,
                       size_t length,
                       struct ug_Feature string[length],
                       ug_Vocab (* ids)[length]
                       );


#endif /* _VOCABULARY_H_ */