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
#include "corpus.h"

/* Compute the cross-entropy of a short string vs. corpus */
double ug_crossEntropy(struct ug_Corpus * ugc, struct ug_Gram query);

/* Make a prediction */
struct ug_Predictions ug_predict(struct ug_Corpus * ugc,
                  struct ug_Gram prefix,
                  size_t min,
                  size_t max,
                  struct ug_Gram postfix
                 );

int ug_addToCorpus(struct ug_Corpus * ugc, struct ug_GramWeighted text);

struct ug_Corpus ug_openCorpus(char * path);

void ug_closeCorpus(struct ug_Corpus * ugc);

struct ug_Corpus ug_createCorpus(char * path,
                                ug_AttributeID nAttributes,
                                size_t gramOrder
                               ); 

#endif /* _UGAPI_H_ */
