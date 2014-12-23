/* copper.h Debugging helper header.
 * Copyright 2006, 2007, 2008, 2013, 2014 Joshua Charles Campbell
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

#ifndef _DEBUG_H_
#define _DEBUG_H_

/* debug shit */

/* error: always prints message and exits */
#define E(x) {cu_printf("!!! %s:%i ", __FILE__, __LINE__); cu_printf x; cu_printf("\n"); cu_exit(1);}

/* warning: always prints message */
#define W(x) {cu_printf("/!\\ %s:%i ", __FILE__, __LINE__); cu_printf x; cu_printf("\n");}

/* debug: only prints if enabled */
#ifdef ENABLE_DEBUG
#define DEBUG(l, x) {if(cu_testdebug(l)) {cu_printf("--%c %s:%i ", l, __FILE__, __LINE__); cu_printf x; cu_printf("\n"); }}
#else /* ENABLE_DEBUG */
#define DEBUG(l, x)
#endif /* ENABLE_DEBUG */

/* error assertions: always executed, always checked, prints message */
#define EASSERT(l, x, m) {if (!x) { DEBUG(l, ("Assertion failed: %s", #x)); cu_printf("!!? %s:%i ", __FILE__, __LINE__); cu_printf m; cu_printf("\n"); cu_exit(1);} else { DEBUG(l, ("Assertion passed: %s", #x)) } }
#define EA(x, m) EASSERT('@', x, m)

/* assertions: always executed, always checked */
#define ASSERT(l, x) EASSERT(l, x, ("Assertion failed."))
#define A(x) EA(x, ("Assertion failed."))

/* system assertions: always executed, always checked, prints errno */
#define ASYS(x) EASSERT('/', x, ("%s", cu_err()))

/* sanity check: only executed if enabled */
#ifdef ENABLE_SANITY
#define ES(x, m) {if (!x) { DEBUG('$', ("Sanity check failed: %s", #x)); cu_printf("!!$ %s:%i ", __FILE__, __LINE__); cu_printf m; cu_printf("\n"); cu_exit(1);} else { DEBUG('$', ("Sanity check passed: %s", #x)) } }
#else /* ENABLE_SANITY */
#define ES(x, m)
#endif /* ENABLE_SANITY */
#define S(x) ES(x, ("Sanity check failed."))

/* sanity assertion: always executed, only checked if enabled */
#ifdef ENABLE_SANITY
#define SA(x) S(x)
#else /* ENABLE_SANITY */
#define SA(x) (x)
#endif /* ENABLE_SANITY */

/* shortcuts */
#define D(x) DEBUG('-', x)
#define Dd(x) DEBUG('d', x) /* Database interface code */
#define Ad(x) ASSERT('d', x)
#define Ds(x) DEBUG('s', x) /* HsuGlass code */
#define As(x) ASSERT('s', x)
#define Du(x) DEBUG('u', x) /* Utility code */
#define Au(x) ASSERT('u', x)
#define Dv(x) DEBUG('v', x) /* Vocab code */
#define Av(x) ASSERT('v', x)

#define TEST()

struct test_result {
	int pass;
        char * name;
	char * text;
};

extern struct test_result copper_global_test_result;

/* function prototypes */
extern int cu_printf(const char * format, ...);
extern void cu_exit(int x);
#include <stdarg.h>
extern void cu_set_handlers(void (*provided_exit)(int x), int (*provided_vprintf)(const char *format, va_list args));
extern void cu_enabledebug(char* f);
extern int cu_testdebug(char f);
extern char * cu_err();

/* end debug shit */

#endif /* _DEBUG_H_ */
