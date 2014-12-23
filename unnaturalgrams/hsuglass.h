/* hsuglass.c -- Implements the Hsu-Glass nGram Vector Datastructure
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

#ifndef _HSUGLASS_H_
#define _HSUGLASS_H_

#include "ug.h"
#include "corpus.h"
#include "attribute.h"

ug_GramOrder ug_setHsuGlass(struct ug_Corpus * corpus, ug_GramOrder order);
void ug_initHsuGlass(struct ug_Corpus * corpus);
void ug_addFeatureStringToCorpus(struct ug_Corpus * corpus,
                                  ug_AttributeID attr,
                                  size_t length,
                                  ug_Vocab vocabString[length],
                                  double weightString[length]
                                );


#endif /* _HSUGLASS_H_ */
