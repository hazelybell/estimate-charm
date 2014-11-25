/* copper-internal.c Run tests.
 * This file is a part of the Copper framework.
 * Copyright 2006-2008 Joshua Charles Campbell.

 * The Copper framework is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 3
 * of the License, or (at your option) any later version.

 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.

 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 */

#include <string.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include "copper.h"

extern int copper_tests_count;
extern struct test_result (*tests[])(void);

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
		} else if (sscanf(argv[i], "%i", &test)) {
			D(("Trying test %s", argv[i]));
			r = (*tests[test])();
			D(("Tested %s", r.text));
			return (!r.pass);
		} else {
			E(("Unknown test specification."));
			return 1;
		}
	}
	return 1;
}
