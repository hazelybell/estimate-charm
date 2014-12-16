/* 
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
#include "smoothing.h"
#include "db.h"

size_t ug_setSmoothing(struct ug_Corpus * corpus, size_t order) {
    size_t j = 0;
    size_t i = 0;
    
    /* This operation can only be done on a new brain so, there is no data
     * present. */
    struct ug_VectorLength metadata = {0};
    struct ug_VectorLengthKey metakey = {ug_VECTOR_LENGTH, 0, 0};
    
    As(( order >= 1 ));
    
      /* Save the model order. */
      ug_writeUInt64ByC(corpus, "gramOrder", order);
      corpus->gramOrder = order;
      /* Save the chunking size. */
      ug_writeUInt64ByC(corpus, "chunkSize", ug_CHUNKSIZE);
      /* Save the vector lengths */
      for (i = 0; i < corpus->nAttributes; i++) {
        for (j = 0; j < corpus->gramOrder; j++) {
          metakey.attributeID = i;
          metakey.gramOrder = j;
          ug_writeStructByStruct(corpus, metakey, metadata);
        }
      }
    
    
    return order;
}

void ug_initSmoothing(struct ug_Corpus * corpus) {
    size_t j = 0;
    size_t i = 0;
    uint64_t dbChunksize = 0;
    
    /* This operation can only be done on a new brain so, there is no data
     * present. */
    struct ug_VectorLength metadata = {0};
    struct ug_VectorLengthKey metakey = {ug_VECTOR_LENGTH, 0, 0};
   
      /* Save the model order. */
      corpus->gramOrder = ug_readUInt64ByC(corpus, "gramOrder");
      As(( corpus->gramOrder >= 1 ));
      /* Save the chunking size. */
      dbChunksize= ug_readUInt64ByC(corpus, "chunkSize");
      As((dbChunksize == ug_CHUNKSIZE));
      /* Save the vector lengths */
      for (i = 0; i < corpus->nAttributes; i++) {
        for (j = 0; j < corpus->gramOrder; j++) {
          metakey.attributeID = i;
          metakey.gramOrder = j;
          ug_readStructByStruct(corpus, metakey, metadata);
        }
      }
}

void ug_addPropertyStringToCorpus(struct ug_Corpus * corpus,
                                  ug_AttributeID attr,
                                  size_t length,
                                  uint64_t * string) {
    size_t i = 0;
    for (i = 0; i < length; i++) {
      
    }
}