/*
 * diff.h — Diff computation declarations
 */

#ifndef LUCY_DIFF_H
#define LUCY_DIFF_H

/**
 * Compute a unified diff between old_text and new_text.
 *
 * @param old_text     Original text
 * @param new_text     Modified text
 * @param output       Output buffer for the diff
 * @param output_size  Size of output buffer
 * @return 0 on success, -1 on error
 */
int lucy_diff(
    const char *old_text,
    const char *new_text,
    char *output,
    int output_size
);

#endif /* LUCY_DIFF_H */
