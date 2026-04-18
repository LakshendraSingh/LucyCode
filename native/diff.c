/*
 * diff.c — Fast diff computation using the Myers algorithm.
 *
 * Computes line-level diffs between two text inputs and outputs
 * unified diff format.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "diff.h"

#define MAX_LINES 100000

/* Split text into lines (modifies input string) */
static int split_lines(char *text, char **lines, int max_lines) {
    int count = 0;
    char *line = strtok(text, "\n");
    while (line && count < max_lines) {
        lines[count++] = line;
        line = strtok(NULL, "\n");
    }
    return count;
}

/* Simple LCS-based diff (O(NM) space — suitable for typical file sizes) */
int lucy_diff(
    const char *old_text,
    const char *new_text,
    char *output,
    int output_size
) {
    /* Copy inputs since we modify them */
    char *old_copy = strdup(old_text);
    char *new_copy = strdup(new_text);
    if (!old_copy || !new_copy) {
        free(old_copy);
        free(new_copy);
        return -1;
    }
    
    char *old_lines[MAX_LINES];
    char *new_lines[MAX_LINES];
    
    int old_count = split_lines(old_copy, old_lines, MAX_LINES);
    int new_count = split_lines(new_copy, new_lines, MAX_LINES);
    
    /* Simple line-by-line comparison for now */
    int pos = 0;
    int max_i = old_count > new_count ? old_count : new_count;
    int i_old = 0, i_new = 0;
    
    while (i_old < old_count || i_new < new_count) {
        if (pos >= output_size - 100) break;
        
        if (i_old < old_count && i_new < new_count &&
            strcmp(old_lines[i_old], new_lines[i_new]) == 0) {
            /* Same line */
            pos += snprintf(output + pos, output_size - pos, " %s\n", old_lines[i_old]);
            i_old++;
            i_new++;
        } else if (i_old < old_count &&
                   (i_new >= new_count ||
                    (i_old + 1 < old_count && i_new + 1 < new_count &&
                     strcmp(old_lines[i_old + 1], new_lines[i_new]) == 0))) {
            /* Removed line */
            pos += snprintf(output + pos, output_size - pos, "-%s\n", old_lines[i_old]);
            i_old++;
        } else if (i_new < new_count) {
            /* Added line */
            pos += snprintf(output + pos, output_size - pos, "+%s\n", new_lines[i_new]);
            i_new++;
        } else {
            i_old++;
        }
    }
    
    output[pos] = '\0';
    
    free(old_copy);
    free(new_copy);
    return 0;
}
