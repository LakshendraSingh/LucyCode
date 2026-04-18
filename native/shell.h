/*
 * shell.h — Shell execution declarations
 */

#ifndef LUCY_SHELL_H
#define LUCY_SHELL_H

/**
 * Execute a shell command with timeout and output capture.
 *
 * @param command         Shell command string
 * @param cwd             Working directory (NULL for current)
 * @param timeout_seconds Timeout in seconds (0 for no timeout)
 * @param stdout_buf      Buffer for stdout
 * @param stdout_buf_size Size of stdout buffer
 * @param stdout_len      Output: bytes written to stdout_buf
 * @param stderr_buf      Buffer for stderr
 * @param stderr_buf_size Size of stderr buffer
 * @param stderr_len      Output: bytes written to stderr_buf
 * @return exit code, or -1 on error
 */
int lucy_exec(
    const char *command,
    const char *cwd,
    int timeout_seconds,
    char *stdout_buf,
    int stdout_buf_size,
    int *stdout_len,
    char *stderr_buf,
    int stderr_buf_size,
    int *stderr_len
);

#endif /* LUCY_SHELL_H */
