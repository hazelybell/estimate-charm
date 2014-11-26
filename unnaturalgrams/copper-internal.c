/* copper-internal.c -- Run tests.
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

#include <string.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include "copper.h"

extern int copper_tests_count;
extern struct test_result (*tests[])(void);

struct test_result copper_global_test_result;
#define SHORT_TEST_OUTPUT_LENGTH 60
static char short_test_output[SHORT_TEST_OUTPUT_LENGTH+1];

static void cu_testdriver_exit(int x) {
        copper_global_test_result.pass = 0;
}

static int cu_testdriver_vprintf(char const *f, va_list args) {
        int r;
        va_list args_copy;
        
        va_copy(args_copy, args);
        
        r = vfprintf(stderr, f, args);
        
        if (copper_global_test_result.text != short_test_output) {
          vsnprintf(short_test_output, SHORT_TEST_OUTPUT_LENGTH,
                    f, args_copy);
          copper_global_test_result.text = short_test_output;
          short_test_output[60] = '\0';
        }
        
        return r;
}

int main (int argc, char ** argv) {
	int i, j;
	pid_t child;
	int status;
	int test;
	struct test_result r;
	cu_enabledebug("all");
	EA((argc > 1),("Specify tests to run."));
	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "all") == 0) {
			for (j = 0; j < copper_tests_count; j++) {
				child = fork();
				if (child > 0) {
					wait(&status);
					if (WIFEXITED(status)) {
						D(("Child exited with status %i", WEXITSTATUS(status)));
						if (WEXITSTATUS(status)) {
							return WEXITSTATUS(status);
						}
					} else if (WIFSIGNALED(status)) {
						D(("Child exited with signal %i", WTERMSIG(status) ));
						return WTERMSIG(status);
					} else {
						D(("Child exited with %i", status));
						return status;
					}
				} else {
					r = (*tests[j])();
					return (!r.pass);
				}
			}
		} else if (sscanf(argv[i], "%i", &test) && test < copper_tests_count) {
			D(("Trying test %s", argv[i]));
                        cu_set_handlers(cu_testdriver_exit, cu_testdriver_vprintf);
			r = (*tests[test])();
                        cu_set_handlers(NULL, NULL);
                        if (r.pass) {
                          D(("Test passed: %s", r.name));
                        } else {
                          D(("Test failed: %s", r.name));
                          D(("    %s", r.text));
                        }
			return (!r.pass);
		} else {
			E(("Unknown test specification."));
			return 1;
		}
	}
	return 1;
}
