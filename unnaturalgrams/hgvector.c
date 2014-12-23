/* hgvector.h -- UnnaturalGram Hsu-Glass Vector
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

#include <string.h>
#include <stdlib.h>
#include "copper.h"
#include "hgvector.h"
#include "db.h"

struct ug_HGVector ug_getHGVector(struct ug_Attribute attribute,
                                  ug_GramOrder order)
{
  struct ug_HGVector v = {attribute, order};
  return v;
}

ug_Index ug_lookupGram(
  struct ug_HGVector v,
  ug_Vocab vocab,
  ug_Index history)
{
  struct ug_GramKey key = {
    ug_GRAM_LOOKUP,
    v.attributeID,
    v.order,
    vocab,
    history
  };
  return ug_readUInt64OrZero(v.corpus, sizeof(key), &key);
}

static ug_Index ug_getVectorLength(struct ug_HGVector v)
{
  struct ug_VectorLengthKey key = {
    ug_VECTOR_LENGTH,
    v.attributeID,
    v.order
  };
  return ug_readUInt64(v.corpus, sizeof(key), &key);
}

size_t ug_getVectorChunkCount(struct ug_HGVector v)
{
  return ug_getVectorLength(v)/ug_CHUNKSIZE;
}


static struct ug_VectorElement * ug_getChunk(
  struct ug_HGVector v,
  ug_Index index
)
{
  struct ug_VectorElement * chunkStart = NULL;
  struct ug_VectorKey key = { ug_VECTOR, v.attributeID, v.order, index };
  
  chunkStart = ug_readNOrNull(v.corpus, sizeof(key), &key,
                              sizeof(struct ug_VectorElement) * ug_CHUNKSIZE);
  if (chunkStart == NULL) {
    return NULL;
  }
  return chunkStart;
}

static struct ug_VectorElement * ug_getWritableChunk(
  struct ug_HGVector v,
  ug_Index index)
{
  struct ug_VectorKey key = { ug_VECTOR, v.attributeID, v.order, index };
  ug_Index chunk = index/ug_CHUNKSIZE;
  struct ug_VectorElement * chunkStart = NULL;
  
  if (v.corpus->dirtyChunks == NULL) {
    ASYS(( (
      v.corpus->dirtyChunks 
        = calloc(sizeof(struct ug_VectorElement *),
                 v.corpus->nAttributes)
    ) != NULL ));
  }

  if (v.corpus->dirtyChunks[v.attributeID] == NULL) {
    ASYS(( (
      v.corpus->dirtyChunks[v.attributeID] =
        calloc(sizeof(struct ug_VectorElement *),
               v.corpus->gramOrder)
    ) != NULL ));
  }

  if (v.corpus->dirtyChunks[v.attributeID][v.order] == NULL) {
    ASYS(( (
      v.corpus->dirtyChunks[v.attributeID][v.order]
        = calloc(sizeof(struct ug_VectorElement *),
                 ug_getVectorLength(v))
    ) != NULL ));
  }
  
  if (v.corpus->dirtyChunks[v.attributeID][v.order][chunk] == NULL) {
    ASYS(( (
      v.corpus->dirtyChunks[v.attributeID][v.order][chunk]
        = ug_overwriteBuffer(
                             v.corpus,
                             sizeof(key),
                             &key,
                             sizeof(struct ug_VectorElement) * ug_CHUNKSIZE
                            )
    ) != NULL ));
    
    chunkStart = ug_getChunk(v, index);
    
    if (chunkStart != NULL) {
      memcpy(v.corpus->dirtyChunks[v.attributeID][v.order][chunk],
            chunkStart,
            sizeof(struct ug_VectorElement) * ug_CHUNKSIZE);
    } else {
      memset(v.corpus->dirtyChunks[v.attributeID][v.order][chunk],
             0,
             sizeof(struct ug_VectorElement) * ug_CHUNKSIZE);
    }
  }
  
  return v.corpus->dirtyChunks[v.attributeID][v.order][chunk];
}

struct ug_VectorElement * ug_getElement(
  struct ug_HGVector v,
  ug_Index index
)
{
  ug_Index chunkOffsetInVector = (index/ug_CHUNKSIZE)*ug_CHUNKSIZE;
  ug_Index offsetInChunk = index%ug_CHUNKSIZE;
  struct ug_VectorElement * chunkStart = NULL;

  chunkStart = ug_getChunk(v, chunkOffsetInVector);

  if (chunkStart == NULL) {
    return NULL;
  }
  return &(chunkStart[offsetInChunk]);
}

static struct ug_VectorElement * ug_getWritableElement(
  struct ug_HGVector v,
  ug_Index index
)
{
  ug_Index chunkOffsetInVector = (index/ug_CHUNKSIZE)*ug_CHUNKSIZE;
  ug_Index offsetInChunk = index%ug_CHUNKSIZE;
  struct ug_VectorElement * chunkStart = NULL;

  chunkStart = ug_getWritableChunk(v, chunkOffsetInVector);

  return &(chunkStart[offsetInChunk]);
}

static ug_Index ug_incrVectorLength(
  struct ug_HGVector v
)
{
  struct ug_VectorLengthKey key = {
    ug_VECTOR_LENGTH,
    v.attributeID,
    v.order
  };
  key.attributeID = v.attributeID;
  ug_Index newLength = ug_getVectorLength(v)+1;
  ug_overwriteUInt64(v.corpus, sizeof(key), &key, newLength);
  return newLength;
}

ug_Index ug_assignFreeIndex(
  struct ug_HGVector v
)
{
  return ug_incrVectorLength(v)-1;
}

void ug_updateElement (
  struct ug_HGVector v,
  ug_Index index,
  struct ug_VectorElement data
)
{
  struct ug_VectorElement * elementPointer = NULL;
  
  elementPointer = ug_getWritableElement(v, index);
  
  (*elementPointer) = data;
}

ug_Index ug_addElement (
  struct ug_HGVector v,
  struct ug_VectorElement data
)
{
  struct ug_GramKey lookup = {
    ug_GRAM_LOOKUP, 
    v.attributeID, 
    v.order, 
    data.vocab, 
    data.historyIndex
  };
  ug_Index newIndex = 0;
  
  newIndex = ug_assignFreeIndex(v);
  Ds(("ug_addElement order %u index %u", v.order, newIndex));

  ug_writeUInt64(v.corpus, sizeof(lookup), &lookup, newIndex);
  
  ug_updateElement(v, newIndex, data);
  
  return newIndex;
}

double ug_bincount (
  struct ug_HGVector v,
  ug_Index i
)
{
  return 0.0;
};
