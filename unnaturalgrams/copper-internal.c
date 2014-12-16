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
#include <stdlib.h>
#include "copper.h"

extern int copper_tests_count;
extern struct test_result (*tests[])(void);

struct test_result copper_global_test_result;
#define MAX_OUTPUT_CAPTURE_LENGTH (1024*1024)
static char output_capture[MAX_OUTPUT_CAPTURE_LENGTH+1];
static size_t output_capture_pos = 0;

static void cu_test_fail_exit(struct test_result r, int status) {
    DEBUG('#', ("Test failed: %s", r.name));
    DEBUG('#', ("\n---Begin Test Failure Log---\n%s---End Test Failure Log---", r.text));
    abort();
}

static void cu_testdriver_exit(int x) {
        copper_global_test_result.pass = 0;
        cu_test_fail_exit(copper_global_test_result, x);
}

static int cu_testdriver_vprintf(char const *f, va_list args) {
        int r = 0;
        va_list args_copy;
        
        va_copy(args_copy, args);
        
        vfprintf(stderr, f, args);
        
        if (MAX_OUTPUT_CAPTURE_LENGTH-output_capture_pos > 0) {
          r = vsnprintf(output_capture+output_capture_pos,
                    MAX_OUTPUT_CAPTURE_LENGTH-output_capture_pos,
                    f, args_copy);
          output_capture_pos += r;
        }
        copper_global_test_result.text = output_capture;
        output_capture[MAX_OUTPUT_CAPTURE_LENGTH] = '\0';
        
        return r;
}

int main (int argc, char ** argv) {
	int i, j;
	pid_t child;
	int status;
	int test;
	struct test_result r;
	cu_enabledebug("#@");
	EASSERT('-',(argc > 1),("Specify tests to run."));
	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "all") == 0) {
			for (j = 0; j < copper_tests_count; j++) {
				child = fork();
				if (child > 0) {
					wait(&status);
					if (WIFEXITED(status)) {
						DEBUG('#', ("Child exited with status %i", WEXITSTATUS(status)));
						if (WEXITSTATUS(status)) {
							return WEXITSTATUS(status);
						}
					} else if (WIFSIGNALED(status)) {
						DEBUG('#', ("Child exited with signal %i", WTERMSIG(status) ));
						return WTERMSIG(status);
					} else {
						DEBUG('#', ("Child exited with %i", status));
						return status;
					}
				} else {
					r = (*tests[j])();
					return (!r.pass);
				}
			}
		} else if (sscanf(argv[i], "%i", &test) && test < copper_tests_count) {
			// DEBUG('#', ("Trying test %s", argv[i]));
                        output_capture[0] = '\0';
                        output_capture_pos = 0;
                        cu_set_handlers(cu_testdriver_exit, cu_testdriver_vprintf);
			r = (*tests[test])();
                        cu_set_handlers(NULL, NULL);
                        if (r.pass) {
                          DEBUG('#', ("Test passed: %s", r.name));
                        } else {
                          cu_test_fail_exit(r, 1);
                        }
			return (!r.pass);
		} else {
			E(("Unknown test specification."));
			return 1;
		}
	}
	return 1;
}
