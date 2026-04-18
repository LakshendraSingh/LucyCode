# Lucy Code Native Extensions — Makefile
#
# Build C extensions for high-performance search, diff, file I/O, and shell.

CC       := gcc
CFLAGS   := -O2 -Wall -Wextra -fPIC
LDFLAGS  := -shared

# Platform detection
UNAME := $(shell uname -s)
ifeq ($(UNAME),Darwin)
    DYLIB_EXT := .dylib
    LDFLAGS   += -dynamiclib
else
    DYLIB_EXT := .so
endif

# Source files
SRCS := search.c diff.c fileio.c shell.c
OBJS := $(SRCS:.c=.o)

# Targets
.PHONY: all clean test

all: liblucy_native$(DYLIB_EXT)

liblucy_native$(DYLIB_EXT): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

search.o: search.c search.h
	$(CC) $(CFLAGS) -c -o $@ $<

diff.o: diff.c diff.h
	$(CC) $(CFLAGS) -c -o $@ $<

fileio.o: fileio.c fileio.h
	$(CC) $(CFLAGS) -c -o $@ $<

shell.o: shell.c shell.h
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f *.o *$(DYLIB_EXT)

test: all
	@echo "Native extensions built successfully."
	@echo "Modules: search, diff, fileio, shell"
	@ls -la liblucy_native$(DYLIB_EXT)
