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

ug_ValueID ug_mapValueToID(struct ug_Corpus * corpus,
                     ug_AttributeID attr,
                     struct ug_Value v)
{
  struct ug_ValueKey vkey = {ug_VALUE, 0, ""};
  A(( v.length < ug_MAX_WORD_LENGTH ));
  
  vkey.attributeID = attr;
  vkey.magic = ug_VALUE;
  memcpy(vkey.value, v.value, v.length);
  
  return ug_readUInt64OrZero(corpus, v.length + ug_VALUE_KEY_PREFIX_LENGTH,
                             &vkey);
}

ug_ValueID ug_getValueCount(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  struct ug_ValueCountKey key = {0, ug_VALUE_COUNT};
  key.attributeID = attr;
  return ug_readUInt64(corpus, sizeof(key), &key);
}

ug_ValueID ug_incrValueCount(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  struct ug_ValueCountKey key = {0, ug_VALUE_COUNT};
  key.attributeID = attr;
  ug_ValueID newCount = ug_getValueCount(corpus, attr)+1;
  ug_overwriteUInt64(corpus, sizeof(key), &key, newCount);
  return newCount;
}

ug_ValueID ug_assignFreeValue(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  return ug_incrValueCount(corpus, attr)-1;
}

ug_ValueID ug_mapValueToIDOrCreate(struct ug_Corpus * corpus,
                     ug_AttributeID attr,
                     struct ug_Value v)
{
  ug_ValueID existing = 0;
  ug_ValueID new = 0;
  
  existing = ug_mapValueToID(corpus, attr, v);
  if (existing != ug_VALUE_UNKNOWN) {
    return existing;
  }
  
  new = ug_assignFreeValue(corpus, attr);
  
  /* Save the new word->id mapping */
  struct ug_ValueKey vkey = {ug_VALUE, attr, ""};
  A(( v.length < ug_MAX_WORD_LENGTH ));
  
  vkey.attributeID = attr;
  vkey.magic = ug_VALUE;
  memcpy(vkey.value, v.value, v.length);
  
  ug_writeUInt64(corpus, v.length + ug_VALUE_KEY_PREFIX_LENGTH,
                             &vkey, new);

  /* Save the new id->word mapping */
  struct ug_IDKey idkey = {ug_VALUE_ID, attr, new};
  
  ug_write(corpus, sizeof(idkey), &idkey, v.length, v.value);
  
  return new;
}

void ug_mapValuesToIDs(struct ug_Corpus * corpus,
                       ug_AttributeID attr,
                       size_t length,
                       struct ug_Value string[length],
                       ug_ValueID (* ids)[length]
                       ) {
    size_t i = 0;
    for (i = 0; i < length; i++) {
        (*ids)[i] = ug_mapValueToID(corpus, attr, string[i]);
    }
}

void ug_mapValuesToIDsOrCreate(struct ug_Corpus * corpus,
                       ug_AttributeID attr,
                       size_t length,
                       struct ug_Value string[length],
                       ug_ValueID (* ids)[length]
                       ) {
    size_t i = 0;
    for (i = 0; i < length; i++) {
        (*ids)[i] = ug_mapValueToIDOrCreate(corpus, attr, string[i]);
    }
}

