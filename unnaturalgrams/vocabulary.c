/* vocabulary.h -- maps words to integers and back
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

#include "copper.h"
#include "vocabulary.h"
#include "smoothing.h"
#include "db.h"
#include <string.h>

ug_Vocab ug_mapFeatureToVocab(struct ug_Corpus * corpus,
                     ug_AttributeID attr,
                     struct ug_Feature v)
{
  struct ug_FeatureKey vkey = {ug_VOCAB, 0, ""};
  A(( v.length < ug_MAX_WORD_LENGTH ));
  
  vkey.attributeID = attr;
  vkey.magic = ug_VOCAB;
  memcpy(vkey.value, v.value, v.length);
  
  return ug_readUInt64OrZero(corpus, v.length + ug_VOCAB_KEY_PREFIX_LENGTH,
                             &vkey);
}

ug_Vocab ug_getValueCount(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  struct ug_VocabCountKey key = {0, ug_VOCAB_COUNT};
  key.attributeID = attr;
  return ug_readUInt64(corpus, sizeof(key), &key);
}

ug_Vocab ug_incrValueCount(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  struct ug_VocabCountKey key = {0, ug_VOCAB_COUNT};
  key.attributeID = attr;
  ug_Vocab newCount = ug_getValueCount(corpus, attr)+1;
  ug_overwriteUInt64(corpus, sizeof(key), &key, newCount);
  return newCount;
}

ug_Vocab ug_assignFreeVocab(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  return ug_incrValueCount(corpus, attr)-1;
}

ug_Vocab ug_mapFeatureToVocabOrCreate(struct ug_Corpus * corpus,
                     ug_AttributeID attr,
                     struct ug_Feature v)
{
  ug_Vocab existing = 0;
  ug_Vocab new = 0;
  
  existing = ug_mapFeatureToVocab(corpus, attr, v);
  if (existing != ug_VOCAB_UNKNOWN) {
    return existing;
  }
  
  new = ug_assignFreeVocab(corpus, attr);
  
  /* Save the new word->id mapping */
  struct ug_FeatureKey vkey = {ug_VOCAB, attr, ""};
  A(( v.length < ug_MAX_WORD_LENGTH ));
  
  vkey.attributeID = attr;
  vkey.magic = ug_VOCAB;
  memcpy(vkey.value, v.value, v.length);
  
  ug_writeUInt64(corpus, v.length + ug_VOCAB_KEY_PREFIX_LENGTH,
                             &vkey, new);

  /* Save the new id->word mapping */
  struct ug_VocabKey idkey = {ug_FEATURE, attr, new};
  
  ug_write(corpus, sizeof(idkey), &idkey, v.length, v.value);
  
  return new;
}

void ug_mapFeaturesToVocabs(struct ug_Corpus * corpus,
                       ug_AttributeID attr,
                       size_t length,
                       struct ug_Feature string[length],
                       ug_Vocab (* ids)[length]
                       ) {
    size_t i = 0;
    for (i = 0; i < length; i++) {
        (*ids)[i] = ug_mapFeatureToVocab(corpus, attr, string[i]);
    }
}

void ug_mapFeaturesToVocabsOrCreate(struct ug_Corpus * corpus,
                       ug_AttributeID attr,
                       size_t length,
                       struct ug_Feature string[length],
                       ug_Vocab (* ids)[length]
                       ) {
    size_t i = 0;
    for (i = 0; i < length; i++) {
        (*ids)[i] = ug_mapFeatureToVocabOrCreate(corpus, attr, string[i]);
    }
}

