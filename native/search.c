/*
 * search.c — High-performance file search (ripgrep-inspired)
 *
 * Provides fast regex search across files with:
 * - POSIX regex (or PCRE2 when available)
 * - Directory traversal with .gitignore-style skipping
 * - Result limiting
 * - Binary file detection
 *
 * Compiled as a Python C extension via module.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>
#include <regex.h>
#include <errno.h>

#include "search.h"

#define MAX_LINE_LEN 4096
#define MAX_RESULTS  50

/* Directories to skip */
static const char *SKIP_DIRS[] = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".cache", "coverage", NULL
};

/* Check if a filename is in the skip list */
static int should_skip_dir(const char *name) {
    for (int i = 0; SKIP_DIRS[i] != NULL; i++) {
        if (strcmp(name, SKIP_DIRS[i]) == 0) return 1;
    }
    return 0;
}

/* Check if a file appears to be binary (contains null bytes in first 8KB) */
static int is_binary_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    
    char buf[8192];
    size_t n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    
    for (size_t i = 0; i < n; i++) {
        if (buf[i] == '\0') return 1;
    }
    return 0;
}

/* Search a single file for a pattern */
static int search_file(
    const char *filepath,
    const regex_t *regex,
    SearchResult *results,
    int *result_count,
    int max_results
) {
    if (*result_count >= max_results) return 0;
    if (is_binary_file(filepath)) return 0;
    
    FILE *f = fopen(filepath, "r");
    if (!f) return 0;
    
    char line[MAX_LINE_LEN];
    int line_no = 0;
    
    while (fgets(line, sizeof(line), f) && *result_count < max_results) {
        line_no++;
        
        /* Remove trailing newline */
        size_t len = strlen(line);
        if (len > 0 && line[len - 1] == '\n') line[len - 1] = '\0';
        
        if (regexec(regex, line, 0, NULL, 0) == 0) {
            SearchResult *r = &results[*result_count];
            strncpy(r->filepath, filepath, sizeof(r->filepath) - 1);
            r->filepath[sizeof(r->filepath) - 1] = '\0';
            r->line_number = line_no;
            strncpy(r->line_content, line, sizeof(r->line_content) - 1);
            r->line_content[sizeof(r->line_content) - 1] = '\0';
            (*result_count)++;
        }
    }
    
    fclose(f);
    return 0;
}

/* Recursively search a directory */
static int search_directory(
    const char *dirpath,
    const regex_t *regex,
    SearchResult *results,
    int *result_count,
    int max_results
) {
    if (*result_count >= max_results) return 0;
    
    DIR *dir = opendir(dirpath);
    if (!dir) return -1;
    
    struct dirent *entry;
    char path[4096];
    
    while ((entry = readdir(dir)) != NULL && *result_count < max_results) {
        /* Skip . and .. */
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;
        
        /* Skip hidden files/dirs (except .gitignore-like) */
        if (entry->d_name[0] == '.' && strcmp(entry->d_name, ".") != 0)
            continue;
        
        snprintf(path, sizeof(path), "%s/%s", dirpath, entry->d_name);
        
        struct stat st;
        if (stat(path, &st) != 0) continue;
        
        if (S_ISDIR(st.st_mode)) {
            if (!should_skip_dir(entry->d_name)) {
                search_directory(path, regex, results, result_count, max_results);
            }
        } else if (S_ISREG(st.st_mode)) {
            search_file(path, regex, results, result_count, max_results);
        }
    }
    
    closedir(dir);
    return 0;
}

/* Main search function */
int lucy_search(
    const char *path,
    const char *pattern,
    int case_insensitive,
    SearchResult *results,
    int max_results,
    int *result_count
) {
    *result_count = 0;
    
    if (max_results > MAX_RESULTS) max_results = MAX_RESULTS;
    
    /* Compile regex */
    regex_t regex;
    int flags = REG_EXTENDED | REG_NEWLINE;
    if (case_insensitive) flags |= REG_ICASE;
    
    int ret = regcomp(&regex, pattern, flags);
    if (ret != 0) {
        return -1;  /* Invalid regex */
    }
    
    struct stat st;
    if (stat(path, &st) != 0) {
        regfree(&regex);
        return -2;  /* Path not found */
    }
    
    if (S_ISREG(st.st_mode)) {
        search_file(path, &regex, results, result_count, max_results);
    } else if (S_ISDIR(st.st_mode)) {
        search_directory(path, &regex, results, result_count, max_results);
    }
    
    regfree(&regex);
    return 0;
}
