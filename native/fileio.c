/*
 * fileio.c — High-performance file I/O with mmap.
 *
 * Provides fast:
 *   - Memory-mapped file reading
 *   - Line counting
 *   - Binary file detection
 *   - UTF-8 validation
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

#include "fileio.h"

/* Check if a file appears to be binary */
int lucy_is_binary(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;

    char buf[8192];
    ssize_t n = read(fd, buf, sizeof(buf));
    close(fd);

    if (n <= 0) return 0; /* Empty or error → not binary */

    for (ssize_t i = 0; i < n; i++) {
        if (buf[i] == '\0') return 1;
    }
    return 0;
}

/* Count lines in a file using mmap */
long lucy_count_lines(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;

    struct stat st;
    if (fstat(fd, &st) < 0 || st.st_size == 0) {
        close(fd);
        return 0;
    }

    char *data = mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);

    if (data == MAP_FAILED) return -1;

    long count = 0;
    for (off_t i = 0; i < st.st_size; i++) {
        if (data[i] == '\n') count++;
    }

    /* Count last line if no trailing newline */
    if (st.st_size > 0 && data[st.st_size - 1] != '\n') {
        count++;
    }

    munmap(data, st.st_size);
    return count;
}

/* Read a file into a buffer using mmap (caller must free) */
char* lucy_read_file(const char *path, long *out_size) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return NULL;

    struct stat st;
    if (fstat(fd, &st) < 0) {
        close(fd);
        return NULL;
    }

    if (st.st_size == 0) {
        close(fd);
        *out_size = 0;
        char *empty = malloc(1);
        if (empty) empty[0] = '\0';
        return empty;
    }

    char *data = mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);

    if (data == MAP_FAILED) return NULL;

    char *buf = malloc(st.st_size + 1);
    if (!buf) {
        munmap(data, st.st_size);
        return NULL;
    }

    memcpy(buf, data, st.st_size);
    buf[st.st_size] = '\0';
    *out_size = st.st_size;

    munmap(data, st.st_size);
    return buf;
}

/* Get file size */
long lucy_file_size(const char *path) {
    struct stat st;
    if (stat(path, &st) < 0) return -1;
    return st.st_size;
}
