// getopt_win.h
// Minimal getopt implementation for Windows/MSVC compatibility

#ifndef GETOPT_WIN_H
#define GETOPT_WIN_H

#ifdef _WIN32

// Option argument constants
#define no_argument 0
#define required_argument 1
#define optional_argument 2

// Global variables
extern char *optarg;
extern int optind;
extern int opterr;
extern int optopt;

// Option structure
struct option {
  const char *name;
  int has_arg;
  int *flag;
  int val;
};

// Function declarations
int getopt_long(int argc, char *const argv[], const char *optstring,
                const struct option *longopts, int *longindex);

#endif // _WIN32

#endif // GETOPT_WIN_H
