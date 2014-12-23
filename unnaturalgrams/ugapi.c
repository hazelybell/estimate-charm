/* ugapi.c -- API Interface for UnnaturalGrams
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
#include "ugapi.h"
#include "db.h"
#include "hsuglass.h"
#include "vocabulary.h"
#include <string.h>
#include <stdlib.h>

double ug_crossEntropy(struct ug_Corpus * corpus, struct ug_Gram query) {
  return 70.0;
}

struct ug_Predictions ug_predict(struct ug_Corpus * corpus,
                  struct ug_Gram prefix,
                  size_t min,
                  size_t max,
                  struct ug_Gram postfix
                 ) {
  A((corpus->open));
  struct ug_Predictions predictions = {
    .nPredictions = 0,
    .predictions = NULL
  };
  return predictions;
}

static void ug_parallelProperties(
  struct ug_Corpus * corpus,
  struct ug_GramWeighted text,
  struct ug_Feature (* lists)[corpus->nAttributes][text.length],
  double (* weights)[text.length]
) {
    size_t i;
    size_t j;
    for (i = 0; i < text.length; i++) {
      for (j = 0; j < text.words[i].nAttributes; j++) {
        Au(( text.words[i].nAttributes == corpus->nAttributes ));
        (*lists)[j][i] = text.words[i].values[j];
      }
      (*weights)[i] = text.words[i].weight;
    }
}

int ug_addToCorpus(struct ug_Corpus * corpus, struct ug_GramWeighted text) {
  size_t i = 0;
  struct ug_Feature lists[corpus->nAttributes][text.length];
  double weights[text.length];
  ug_Vocab ids[text.length];
  A((corpus->open));
  A((text.length > 0));

  ug_parallelProperties(corpus, text, &lists, &weights);
  
  ug_beginRW(corpus);

    for (i = 0; i < corpus->nAttributes; i++) {
      ug_mapFeaturesToVocabsOrCreate(corpus, i, text.length, lists[i], &ids);
      ug_addFeatureStringToCorpus(corpus, i, text.length, ids, weights);
    }
    
  
  ug_commit(corpus);
  return i;
}

struct ug_Corpus ug_openCorpus(char * path) {
  struct ug_Corpus corpus = {
    .nAttributes = 0,
    .open = 0,
    .gramOrder = 0
  };
  A(( ug_openDB(path, &corpus) == 0 ));
  corpus.open = 1;
  ug_beginRO(&corpus);
    corpus.nAttributes = ug_readUInt64ByC(&corpus, "nAttributes");
    ug_initHsuGlass(&corpus);
  ug_commit(&corpus);
  return corpus;
}

void ug_closeCorpus(struct ug_Corpus * corpus) {
  EA(( corpus->open ), ("DB already closed"));
  A(( ug_closeDB(corpus) == 0 ));
  corpus->open = 0;
}

static int ug_storeSettingsInDB(struct ug_Corpus * corpus, ug_AttributeID nAttributes) {
  ug_writeUInt64ByC(corpus, "nAttributes", nAttributes);
  
  corpus->nAttributes = nAttributes;
  
  return 0;
}

struct ug_Corpus ug_createCorpus(char * path, ug_AttributeID nAttributes, size_t gramOrder) {
  struct ug_Corpus corpus = {
    .nAttributes = 0,
    .open = 0,
    .gramOrder = 0
  };
  ug_AttributeID ia;
  A(( ug_createDB(path, &corpus) == 0 ));
  ug_beginRW(&corpus);
  A(( ug_storeSettingsInDB(&corpus, nAttributes) == 0 ));
  A(( ug_setHsuGlass(&corpus, gramOrder) == gramOrder ));
  for (ia = 0; ia < nAttributes; ia++) {
    ug_initVocab(&corpus, ia);
  }
  ug_commit(&corpus);
  corpus.open = 1;
  return corpus;
}

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
  
  A((c.nAttributes == 1));
  A((c.gramOrder == 10));

  ug_closeCorpus(&c);
  A((!c.open));
  c = ug_openCorpus(path);
  
  A((c.nAttributes == 1));
  A((c.gramOrder == 10));
  
  ug_closeCorpus(&c);
  A((!c.open));
  system(removeCmd);
});

#ifdef ENABLE_TESTING

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

static struct ug_WordWeighted testTermArray[] = {
  { 1, 1.0, testAttrArray+0 },
  { 1, 1.0, testAttrArray+1 },
  { 1, 1.0, testAttrArray+2 },
  { 1, 1.0, testAttrArray+3 },
  { 1, 1.0, testAttrArray+4 },
  { 1, 1.0, testAttrArray+5 },
  { 1, 1.0, testAttrArray+6 },
  { 1, 1.0, testAttrArray+7 },
  { 1, 1.0, testAttrArray+8 },
  { 1, 1.0, testAttrArray+9 },
  { 1, 1.0, testAttrArray+10 },
  { 1, 1.0, testAttrArray+11 },
  { 1, 1.0, testAttrArray+12 },
  { 1, 1.0, testAttrArray+13 },
  { 1, 1.0, testAttrArray+14 },
  { 1, 1.0, testAttrArray+15 },
  { 1, 1.0, testAttrArray+16 },
  { 1, 1.0, testAttrArray+17 },
  { 1, 1.0, testAttrArray+18 },
  { 1, 1.0, testAttrArray+19 },
  { 1, 1.0, testAttrArray+20 },
  { 1, 1.0, testAttrArray+21 },
  { 1, 1.0, testAttrArray+22 },
  { 1, 1.0, testAttrArray+23 },
  { 1, 1.0, testAttrArray+24 },
  { 1, 1.0, testAttrArray+25 },
};

static struct ug_GramWeighted testText = { 20, testTermArray };
  
static struct ug_Word testTermQueryArray[] = {
  { 1, testAttrArray+0 },
  { 1, testAttrArray+1 },
  { 1, testAttrArray+2 },
  { 1, testAttrArray+3 },
  { 1, testAttrArray+4 },
  { 1, testAttrArray+5 },
  { 1, testAttrArray+6 },
  { 1, testAttrArray+7 },
  { 1, testAttrArray+8 },
  { 1, testAttrArray+9 },
  { 1, testAttrArray+10 },
  { 1, testAttrArray+11 },
  { 1, testAttrArray+12 },
  { 1, testAttrArray+13 },
  { 1, testAttrArray+14 },
  { 1, testAttrArray+15 },
  { 1, testAttrArray+16 },
  { 1, testAttrArray+17 },
  { 1, testAttrArray+18 },
  { 1, testAttrArray+19 },
  { 1, testAttrArray+20 },
  { 1, testAttrArray+21 },
  { 1, testAttrArray+22 },
  { 1, testAttrArray+23 },
  { 1, testAttrArray+24 },
  { 1, testAttrArray+25 },
};

static struct ug_Gram testQuery = { 20, testTermQueryArray };


#endif /* ENABLE_TESTING */

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
  
  A(( ug_addToCorpus(&c, testText) ));
  ug_beginRO(&c);
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[0]) > 0 ));
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[1]) > 0 ));
    A(( ug_mapFeatureToVocab(&c, 0, testAttrArray[1]) != 
        ug_mapFeatureToVocab(&c, 0, testAttrArray[0]) ));
  ug_commit(&c);
  A(( ug_crossEntropy(&c, testQuery) < 69.0 ));
  
  ug_closeCorpus(&c);
  A(( !c.open ));
  system(removeCmd);  
});

