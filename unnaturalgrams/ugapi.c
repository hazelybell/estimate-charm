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
#include <string.h>
#include <stdlib.h>

double ug_crossEntropy(struct UGCorpus * ugc, struct UGram query) {
  return 70.0;
}

struct UGPredictions ug_predict(struct UGCorpus * ugc,
                  struct UGram prefix,
                  size_t min,
                  size_t max,
                  struct UGram postfix
                 ) {
  A((ugc->open));
  struct UGPredictions predictions = {
    .nPredictions = 0,
    .predictions = NULL
  };
  return predictions;
}

int ug_addToCorpus(struct UGCorpus * ugc, struct UGramWeighted text) {
  A((ugc->open));
  return 0;
}

struct UGCorpus ug_openCorpus(char * path) {
  struct UGCorpus corpus = {
    .nProperties = 0,
    .open = 0
  };
  A(( ug_openDB(path, &corpus) == 0 ));
  corpus.open = 1;
  ug_beginRO(&corpus);
  corpus.nProperties = ug_readUInt64ByC(&corpus, "nProperties");
  ug_commit(&corpus);
  return corpus;
}

void ug_closeCorpus(struct UGCorpus * ugc) {
  EA(( ugc->open ), ("DB already closed"));
  A(( ug_closeDB(ugc) == 0 ));
  ugc->open = 0;
}

static int ug_storeSettingsInDB(struct UGCorpus * corpus, UGPropertyID nProperties) {
  ug_beginRW(corpus);
    ug_writeUInt64ByC(corpus, "nProperties", nProperties);
  ug_commit(corpus);
  
  corpus->nProperties = nProperties;
  
  return 0;
}

struct UGCorpus ug_createCorpus(char * path, UGPropertyID nProperties, size_t gramOrder) {
  struct UGCorpus corpus = {
    .nProperties = 0,
    .open = 0,
    .gramOrder = 1
  };
  A(( ug_createDB(path, &corpus) == 0 ));
  A(( ug_storeSettingsInDB(&corpus, nProperties) == 0 ));
  corpus.gramOrder = gramOrder;
  corpus.open = 1;
  return corpus;
}

TEST({
  struct UGCorpus c;
  char * tmpDir;
  char removeCmd[] = "rm -rvf ugtest-XXXXXX";
  char path[] = "ugtest-XXXXXX/corpus";
  tmpDir = &(removeCmd[8]);
  ASYS(( tmpDir == mkdtemp(tmpDir) ));
  memcpy(path, tmpDir, strlen(tmpDir));
  c = ug_createCorpus(path, 1, 10);
  EA((c.open), ("Didn't open."));
  
  A((c.nProperties == 1));
//   A((c.gramOrder == 10));

  ug_closeCorpus(&c);
  A((!c.open));
  c = ug_openCorpus(path);
  
  A((c.nProperties == 1));
//   A((c.gramOrder == 10));
  
  ug_closeCorpus(&c);
  A((!c.open));
  system(removeCmd);
});

// TEST({
//   struct UGCorpus c;
//   char * tmpDir;
//   char removeCmd[] = "rm -rvf ugtest-XXXXXX";
//   char path[] = "ugtest-XXXXXX/corpus";
//   tmpDir = &(removeCmd[8]);
//   ASYS(( tmpDir == mkdtemp(tmpDir) ));
//   memcpy(path, tmpDir, strlen(tmpDir));
//   c = ug_createCorpus(path, 1, 10);
//   EA((c.open), ("Didn't open."));
//   
//   
//   
//   ug_closeCorpus(&c);
//   A((!c.open));
//   system(removeCmd);  
// });

