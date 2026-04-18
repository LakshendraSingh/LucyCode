/*
 * search.h — File search declarations
 */

#ifndef LUCY_SEARCH_H
#define LUCY_SEARCH_H

typedef struct {
    char filepath[4096];
    int  line_number;
    char line_content[1024];
} SearchResult;

/**
 * Search files for a regex pattern.
 *
 * @param path             File or directory to search
 * @param pattern          POSIX extended regex pattern
 * @param case_insensitive If non-zero, case-insensitive search
 * @param results          Output array of results
 * @param max_results      Maximum results to return
 * @param result_count     Output: number of results found
 * @return 0 on success, -1 on invalid regex, -2 on path not found
 */
int lucy_search(
    const char *path,
    const char *pattern,
    int case_insensitive,
    SearchResult *results,
    int max_results,
    int *result_count
);

#endif /* LUCY_SEARCH_H */
