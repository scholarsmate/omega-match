// getopt_win.c
// Minimal getopt implementation for Windows/MSVC compatibility

#ifdef _WIN32

#include "getopt_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Global variables
char *optarg = NULL;
int optind = 1;
int opterr = 1;
int optopt = 0;

// Simple getopt_long implementation for Windows
int getopt_long(int argc, char *const argv[], const char *optstring,
                const struct option *longopts, int *longindex) {
  static int sp = 1;
  static char *lastarg = NULL;

  if (optind >= argc) {
    return -1;
  }

  char *arg = argv[optind];

  // Check for long options (--option)
  if (arg[0] == '-' && arg[1] == '-' && longopts) {
    char *name = arg + 2;
    char *eq = strchr(name, '=');
    size_t name_len = eq ? (size_t)(eq - name) : strlen(name);

    // Find matching long option
    for (int i = 0; longopts[i].name; i++) {
      if (strncmp(longopts[i].name, name, name_len) == 0 &&
          strlen(longopts[i].name) == name_len) {

        optind++;

        if (longopts[i].has_arg == required_argument) {
          if (eq) {
            optarg = eq + 1;
          } else if (optind < argc) {
            optarg = argv[optind++];
          } else {
            if (opterr) {
              fprintf(stderr, "option '--%s' requires an argument\n",
                      longopts[i].name);
            }
            return '?';
          }
        } else if (longopts[i].has_arg == optional_argument) {
          optarg = eq ? eq + 1 : NULL;
        } else {
          optarg = NULL;
          if (eq) {
            if (opterr) {
              fprintf(stderr, "option '--%s' doesn't allow an argument\n",
                      longopts[i].name);
            }
            return '?';
          }
        }

        if (longopts[i].flag) {
          *longopts[i].flag = longopts[i].val;
          return 0;
        } else {
          return longopts[i].val;
        }
      }
    }

    if (opterr) {
      fprintf(stderr, "unrecognized option '--%.*s'\n", (int)name_len, name);
    }
    return '?';
  }

  // Check for short options (-o)
  if (arg[0] == '-' && arg[1] != '\0' && arg[1] != '-') {
    char opt = arg[sp];

    if (opt == '\0') {
      sp = 1;
      optind++;
      return getopt_long(argc, argv, optstring, longopts, longindex);
    }

    char *p = strchr(optstring, opt);
    if (p == NULL) {
      if (opterr) {
        fprintf(stderr, "invalid option -- '%c'\n", opt);
      }
      optopt = opt;
      sp++;
      if (arg[sp] == '\0') {
        sp = 1;
        optind++;
      }
      return '?';
    }

    sp++;

    if (p[1] == ':') {
      // Option requires argument
      if (arg[sp] != '\0') {
        optarg = &arg[sp];
        sp = 1;
        optind++;
      } else if (optind + 1 < argc) {
        optind++;
        optarg = argv[optind];
        sp = 1;
        optind++;
      } else {
        if (opterr) {
          fprintf(stderr, "option requires an argument -- '%c'\n", opt);
        }
        optopt = opt;
        sp = 1;
        optind++;
        return '?';
      }
    } else {
      // Option doesn't require argument
      optarg = NULL;
      if (arg[sp] == '\0') {
        sp = 1;
        optind++;
      }
    }

    return opt;
  }

  return -1;
}

#endif // _WIN32
