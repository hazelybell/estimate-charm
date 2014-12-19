/* attribute.h -- UnnaturalGram attribute (type of feature) 
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

#ifndef _ATTRIBUTE_H_
#define _ATTRIBUTE_H_

#include "corpus.h"

struct ug_Attribute {
  struct ug_Corpus * corpus;
  ug_AttributeID attributeID;
};

struct ug_Attribute ug_getAttribute(struct ug_Corpus * corpus,
                                    ug_AttributeID id);

#endif /* _ATTRIBUTE_H_ */