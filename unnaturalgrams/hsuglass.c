/* hsuglass.c -- implements the Hsu-Glass nGram Vector Datastructure
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
#include "hsuglass.h"
#include "db.h"
#include "hgvector.h"

size_t ug_setHsuGlass(struct ug_Corpus * corpus, size_t order) {
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
        for (j = 1; j <= corpus->gramOrder; j++) {
          metakey.attributeID = i;
          metakey.gramOrder = j;
          ug_writeStructByStruct(corpus, metakey, metadata);
        }
      }
    
    
    return order;
}

void ug_initHsuGlass(struct ug_Corpus * corpus) {
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
        for (j = 1; j <= corpus->gramOrder; j++) {
          metakey.attributeID = i;
          metakey.gramOrder = j;
          ug_readStructByStruct(corpus, metakey, metadata);
        }
      }
}

/* In order to prevent double counting, we only accumulate weights on to
 * nGrams which were on a path that right-recursed ANY amount of times
 * and then left-recursed ANY amount of times, but no other pattern is allowed:
 * Example:
 *                /         \        5-grams      /  history recursion
 *               /           \       4-grams      \  backoff recursion
 *              /            /       3-grams
 *              \           /        2-grams
 *               \          \        1-grams
 *              counted    not
 *
 * Thus we track 3 states:
 * 1) ONLY left-recursion has ever occured
 * 2) ONLY left-recursion followed by ONLY right-recursion has occured 
 * 3) left-right-left has occured, in this state we will not count weights
 * 
 * When called from a sliding window recursionState should be 1 on the first
 * (leftmost) window and 2 otherwise.
 */    
static ug_Index ug_addNGram(struct ug_Attribute attr,
                                    ug_GramOrder order,
                                    ug_Vocab * vocabString,
                                    double * weightString,
                                    int recursionState
                                   )
{
  ug_Index index = ug_NGRAM_UNKNOWN; /* into order order */
  ug_Index history = ug_NGRAM_UNKNOWN; /* into order (order-1) */
  ug_Index backoff = ug_NGRAM_UNKNOWN; /* into order (order-1) */
  struct ug_VectorElement elt;
  struct ug_HGVector v = ug_getHGVector(attr, order);
  
  Ds(("ug_addNGram %u %u %u %p %i", attr.attributeID, order, vocabString[0], 
      weightString, recursionState));
  
  /* recursive base case */
  if (order == 1) {
    history = ug_NGRAM_UNKNOWN; /* Doesn't make sense for unigrams to have a */
                                /* history or a backoff. */
  } else {
    /* Recursively build our prefix trie by adding
     * the prefix if necessary. In state 1 stay in state 1, otherwise
     * goto state 3.
     */
    history = ug_addNGram(attr, order-1,
                          vocabString, weightString,
                          ((recursionState == 1) ? 1 : 3)
                         );
  }
  
  index = ug_lookupGram(v,
                        vocabString[order-1],
                        history);

  Ds(("ug_addNGram index %u", index));
  /* Does it already exist? */
  if (index == ug_NGRAM_UNKNOWN) { /* It does not already exist. */
    if (order == 1) {
      backoff = ug_NGRAM_UNKNOWN;
    } else {
      /* Recursively build our backoff trie by adding
      * the postfix if necessary. In state 1 or 2 goto state 2, otherwise
      * goto state 3.
      */
      backoff = ug_addNGram(attr, order-1,
                            &(vocabString[1]), &(weightString[1]),
                            ((recursionState != 3) ? 2 : 3)
                           );
    }
                         
    Av(( recursionState != 3 ));
    
    elt.historyIndex = history;
    elt.vocab = vocabString[order-1];
    elt.weight = weightString[order-1];
    elt.backoffWeight = 0.0;
    elt.backoffIndex = backoff;
    
    
    index = ug_addElement(v, elt);  
  } else { /* It does already exist. */
    elt = *ug_getElement(v, index);
    
    As(( elt.historyIndex == history ));
    As(( elt.vocab == vocabString[order-1] ));
    
    if (recursionState == 1) {
      if (order == 1) {
        backoff = ug_NGRAM_UNKNOWN;
      } else {
        backoff = ug_addNGram(attr, order-1,
                              &(vocabString[1]), &(weightString[1]),
                              ((recursionState != 3) ? 2 : 3)
                             );
      }
      As(( elt.backoffIndex == backoff ));
    }
    
    if (recursionState != 3) {
      elt.weight += weightString[order-1];
      ug_updateElement(v, index, elt);
    }
  }
  return index;
}

static void ug_addFeatureStringToAttribute(
  struct ug_Attribute attr,
  size_t length,
  ug_Vocab * vocabString,
  double * weightString
) 
{
    size_t iWord = 0;
    /* Sliding window */
    ug_addNGram(attr,
                (length <= attr.corpus->gramOrder ? length : attr.corpus->gramOrder), /* = order */
                &(vocabString[0]),
                &(weightString[0]),
                1
               );
    for (iWord = 1; iWord < length-attr.corpus->gramOrder; iWord++) {
      ug_addNGram(attr,
                  attr.corpus->gramOrder,
                  &(vocabString[iWord]),
                  &(weightString[iWord]),
                  2
                 );
    }
}

void ug_addFeatureStringToCorpus(struct ug_Corpus * corpus,
                                  ug_AttributeID attr,
                                  size_t length,
                                  ug_Vocab vocabString[length],
                                  double weightString[length]
                                ) 
{
  ug_addFeatureStringToAttribute(ug_getAttribute(corpus, attr),
                                 length, vocabString, weightString);
}