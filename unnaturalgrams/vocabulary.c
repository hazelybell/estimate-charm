/* vocabulary.c -- maps words to integers and back
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
#include "hsuglass.h"
#include "db.h"
#include <string.h>

ug_Vocab ug_mapFeatureToVocab(struct ug_Corpus * corpus,
                     ug_AttributeID attr,
                     struct ug_Feature v)
{
  struct ug_FeatureKey vkey = {ug_VOCAB, 0, ""};
  Av(( v.length < ug_MAX_WORD_LENGTH ));
  
  vkey.attributeID = attr;
  vkey.magic = ug_VOCAB;
  memcpy(vkey.value, v.value, v.length);
  
  return ug_readUInt64OrZero(corpus, v.length + ug_VOCAB_KEY_PREFIX_LENGTH,
                             &vkey);
}

ug_Vocab ug_getVocabCount(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  struct ug_VocabCountKey key = {0, ug_VOCAB_COUNT};
  key.attributeID = attr;
  return ug_readUInt64(corpus, sizeof(key), &key);
}

ug_Vocab ug_incrVocabCount(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  struct ug_VocabCountKey key = {0, ug_VOCAB_COUNT};
  key.attributeID = attr;
  ug_Vocab newCount = ug_getVocabCount(corpus, attr)+1;
  ug_overwriteUInt64(corpus, sizeof(key), &key, newCount);
  return newCount;
}

ug_Vocab ug_assignFreeVocab(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  return ug_incrVocabCount(corpus, attr)-1;
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
  Av(( v.length < ug_MAX_WORD_LENGTH ));
  
  vkey.attributeID = attr;
  vkey.magic = ug_VOCAB;
  memcpy(vkey.value, v.value, v.length);
  
  ug_writeUInt64(corpus, v.length + ug_VOCAB_KEY_PREFIX_LENGTH,
                             &vkey, new);

  /* Save the new id->word mapping */
  struct ug_VocabKey idkey = {ug_FEATURE, attr, new};
  
  ug_write(corpus, sizeof(idkey), &idkey, v.length, v.value);
  
  Dv(( "Allocated new vocab %u", new ));
  
  return new;
}

void ug_initVocab(struct ug_Corpus * corpus,
                                 ug_AttributeID attr)
{
  ug_Vocab unknownId = 100;
  struct ug_VocabCountKey key = {0, ug_VOCAB_COUNT};
  char unknownString[] = "__UNKNOWN__";
  struct ug_Feature unknownFeature = {strlen(unknownString)+1, unknownString};
  key.attributeID = attr;
  ug_writeUInt64(corpus, sizeof(key), &key, 0);
  unknownId = ug_mapFeatureToVocabOrCreate(corpus, attr, unknownFeature);
  Av((unknownId == 0));
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

#ifdef ENABLE_TESTING
#include "ugapi.h"
#include <stdlib.h>

static struct ug_Feature testAttrArray[] = {
  { 2, "a" },
  { 2, "b" },
  { 2, "c" },
  { 2, "d" },
  { 2, "e" },
  { 2, "f" },
  { 2, "g" },
  { 2, "h" },
  { 2, "i" },
  { 2, "j" },
  { 2, "k" },
  { 2, "l" },
  { 2, "m" },
  { 2, "n" },
  { 2, "o" },
  { 2, "p" },
  { 2, "q" },
  { 2, "r" },
  { 2, "s" },
  { 2, "t" },
  { 2, "u" },
  { 2, "v" },
  { 2, "w" },
  { 2, "x" },
  { 2, "y" },
  { 2, "z" }
};

// static struct ug_WordWeighted testTermArray[] = {
//   { 1, 1.0, testAttrArray+0 },
//   { 1, 1.0, testAttrArray+1 },
//   { 1, 1.0, testAttrArray+2 },
//   { 1, 1.0, testAttrArray+3 },
//   { 1, 1.0, testAttrArray+4 },
//   { 1, 1.0, testAttrArray+5 },
//   { 1, 1.0, testAttrArray+6 },
//   { 1, 1.0, testAttrArray+7 },
//   { 1, 1.0, testAttrArray+8 },
//   { 1, 1.0, testAttrArray+9 },
//   { 1, 1.0, testAttrArray+10 },
//   { 1, 1.0, testAttrArray+11 },
//   { 1, 1.0, testAttrArray+12 },
//   { 1, 1.0, testAttrArray+13 },
//   { 1, 1.0, testAttrArray+14 },
//   { 1, 1.0, testAttrArray+15 },
//   { 1, 1.0, testAttrArray+16 },
//   { 1, 1.0, testAttrArray+17 },
//   { 1, 1.0, testAttrArray+18 },
//   { 1, 1.0, testAttrArray+19 },
//   { 1, 1.0, testAttrArray+20 },
//   { 1, 1.0, testAttrArray+21 },
//   { 1, 1.0, testAttrArray+22 },
//   { 1, 1.0, testAttrArray+23 },
//   { 1, 1.0, testAttrArray+24 },
//   { 1, 1.0, testAttrArray+25 },
// };

// static struct ug_GramWeighted testText = { 20, testTermArray };
  
TEST({
  struct ug_Corpus c;
  char * tmpDir;
  char removeCmd[] = "rm -rvf ugtest-XXXXXX";
  char path[] = "ugtest-XXXXXX/corpus";
  tmpDir = &(removeCmd[8]);
  ASYS(( tmpDir == mkdtemp(tmpDir) ));
  memcpy(path, tmpDir, strlen(tmpDir));
  c = ug_createCorpus(path, 1, 10);
  EA((c.open), ("Didn't open."));
  
  ug_beginRW(&c);
    A(( ug_mapFeatureToVocabOrCreate(&c, 0, testAttrArray[0]) > 0 ));
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[0]) > 0 ));
    A(( ug_mapFeatureToVocabOrCreate(&c, 0, testAttrArray[1]) > 0 ));
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[1]) > 0 ));
  ug_commit(&c);
  ug_beginRO(&c);
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[1]) != 
        ug_mapFeatureToVocab(&c, 0, testAttrArray[0]) ));
  ug_commit(&c);
  
  ug_closeCorpus(&c);
  A((!c.open));
  c = ug_openCorpus(path);

  ug_beginRO(&c);
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[1]) > 0 ));
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[0]) > 0 ));
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[1]) != 
        ug_mapFeatureToVocab(&c, 0, testAttrArray[0]) ));
  ug_commit(&c);
  
  ug_closeCorpus(&c);
  A(( !c.open ));
  system(removeCmd);  
});

#endif /* ENABLE_TESTING */
