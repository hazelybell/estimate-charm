/* copper.c Debugging helper.
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

#include "copper.h"
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include <errno.h>

#define MAXFLAGS 128

 /* debug levels */
static int dl[MAXFLAGS];

static int cu_builtin_vprintf(char const *f, va_list args) {
	return vfprintf(stderr, f, args);
}

static int (*cu_vprintf_handler)(const char *format, va_list args) = cu_builtin_vprintf;

int cu_printf(char const *f, ...) {
	va_list args; 
	int i;
	va_start(args, f);
	i = (*cu_vprintf_handler)(f, args);
	va_end (args); 
	return i;
}

static void cu_builtin_exit(int x) {
	exit(x);
}

static void (*cu_exit_handler)(int x) = cu_builtin_exit;

void cu_exit(int x) {
	(*cu_exit_handler)(x);
}

void cu_set_handlers(void (*provided_exit)(int x), int (*provided_vprintf)(const char *format, va_list args)) {
    if (provided_exit == NULL) {
        cu_exit_handler = cu_builtin_exit;
    } else {
        cu_exit_handler = provided_exit;
    }
    if (provided_vprintf == NULL) {
        cu_vprintf_handler = cu_builtin_vprintf;
    } else {
        cu_vprintf_handler = provided_vprintf;
    }
}

static void cu_enable_debug_flags(char *f) {
        unsigned int ifl;
        unsigned int fl;
        if (strcmp(f, "all") == 0) {
                for (ifl = 0; ifl < MAXFLAGS; ifl++) {
                        dl[ifl] = 1;
                }
                D(("Every debug flag enabled."));
                return;
        } else {
                fl = strlen(f);
                for (ifl = 0; ifl < fl; ifl++) {
                        dl[(int)f[ifl]] = 1;
                }
                dl[(int)'-'] = 1;
                D(("Debug flags enabled: %s", f));
                return;
        }
}

void cu_enabledebug(char* f) {
        char * env_flags = NULL;
        env_flags = getenv("DEBUG_FLAGS");
        cu_enable_debug_flags(f);
        if (env_flags != NULL) cu_enable_debug_flags(env_flags);
}

int cu_testdebug(char f) {
	return dl[(int)f];
}

char * cu_err() {
	return strerror(errno);
}
