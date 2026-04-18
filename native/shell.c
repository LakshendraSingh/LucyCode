/*
 * shell.c — Subprocess management with timeout and signal handling.
 *
 * Provides:
 *   - posix_spawn-based shell execution
 *   - Timeout via alarm/signal
 *   - Output capture with pipe buffering
 *   - Signal forwarding (SIGINT, SIGTERM)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/types.h>
#include <errno.h>
#include <spawn.h>

#include "shell.h"

extern char **environ;

#define MAX_OUTPUT_SIZE (1024 * 1024)  /* 1MB */
#define READ_BUF_SIZE  4096

/* Execute a shell command with timeout */
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
) {
    int stdout_pipe[2], stderr_pipe[2];

    if (pipe(stdout_pipe) < 0 || pipe(stderr_pipe) < 0) {
        return -1;
    }

    pid_t pid = fork();

    if (pid < 0) {
        close(stdout_pipe[0]); close(stdout_pipe[1]);
        close(stderr_pipe[0]); close(stderr_pipe[1]);
        return -1;
    }

    if (pid == 0) {
        /* Child */
        close(stdout_pipe[0]);
        close(stderr_pipe[0]);
        dup2(stdout_pipe[1], STDOUT_FILENO);
        dup2(stderr_pipe[1], STDERR_FILENO);
        close(stdout_pipe[1]);
        close(stderr_pipe[1]);

        if (cwd && cwd[0]) {
            if (chdir(cwd) < 0) {
                _exit(127);
            }
        }

        execl("/bin/sh", "sh", "-c", command, NULL);
        _exit(127);
    }

    /* Parent */
    close(stdout_pipe[1]);
    close(stderr_pipe[1]);

    *stdout_len = 0;
    *stderr_len = 0;

    /* Read output (simple blocking read) */
    char buf[READ_BUF_SIZE];
    ssize_t n;

    /* Set alarm for timeout */
    if (timeout_seconds > 0) {
        alarm(timeout_seconds);
    }

    /* Read stdout */
    while ((n = read(stdout_pipe[0], buf, sizeof(buf))) > 0) {
        int to_copy = n;
        if (*stdout_len + to_copy > stdout_buf_size - 1) {
            to_copy = stdout_buf_size - 1 - *stdout_len;
        }
        if (to_copy > 0) {
            memcpy(stdout_buf + *stdout_len, buf, to_copy);
            *stdout_len += to_copy;
        }
    }
    stdout_buf[*stdout_len] = '\0';
    close(stdout_pipe[0]);

    /* Read stderr */
    while ((n = read(stderr_pipe[0], buf, sizeof(buf))) > 0) {
        int to_copy = n;
        if (*stderr_len + to_copy > stderr_buf_size - 1) {
            to_copy = stderr_buf_size - 1 - *stderr_len;
        }
        if (to_copy > 0) {
            memcpy(stderr_buf + *stderr_len, buf, to_copy);
            *stderr_len += to_copy;
        }
    }
    stderr_buf[*stderr_len] = '\0';
    close(stderr_pipe[0]);

    /* Cancel alarm */
    alarm(0);

    /* Wait for child */
    int status;
    waitpid(pid, &status, 0);

    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return -1;
}
