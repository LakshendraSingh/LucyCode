/*
 * fileio.h — File I/O declarations
 */

#ifndef LUCY_FILEIO_H
#define LUCY_FILEIO_H

/**
 * Check if a file appears to be binary.
 * @return 1 if binary, 0 if text, -1 on error
 */
int lucy_is_binary(const char *path);

/**
 * Count lines in a file using mmap.
 * @return line count, or -1 on error
 */
long lucy_count_lines(const char *path);

/**
 * Read entire file into a buffer using mmap.
 * Caller must free the returned buffer.
 * @param path     File path
 * @param out_size Output: file size
 * @return buffer (caller frees), or NULL on error
 */
char* lucy_read_file(const char *path, long *out_size);

/**
 * Get file size.
 * @return size in bytes, or -1 on error
 */
long lucy_file_size(const char *path);

#endif /* LUCY_FILEIO_H */
