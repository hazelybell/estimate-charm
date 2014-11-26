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
  return corpus;
}

int ug_closeCorpus(struct UGCorpus * ugc) {
  A((ugc->open));
  return 0;
}

struct UGCorpus ug_createCorpus(char * path, UGPropertyID nProperties) {
  struct UGCorpus corpus = {
    .nProperties = 0,
    .open = 0
  };
  return corpus;
}

TEST(ug_createCorpus("/tmp/ugCorpus", 1).open);