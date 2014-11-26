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

#ifndef _UGAPI_H_
#define _UGAPI_H_

#include "ug.h"

/* Compute the cross-entropy of a short string vs. corpus */
double ug_crossEntropy(struct UGCorpus * ugc, struct UGram query);

/* Make a prediction */
struct UGPredictions ug_predict(struct UGCorpus * ugc,
                  struct UGram prefix,
                  size_t min,
                  size_t max,
                  struct UGram postfix
                 );

int ug_addToCorpus(struct UGCorpus * ugc, struct UGramWeighted text);

struct UGCorpus ug_openCorpus(char * path);

int ug_closeCorpus(struct UGCorpus * ugc);

struct UGCorpus ug_createCorpus(char * path, UGPropertyID nProperties); 

#endif /* _UGAPI_H_ */
