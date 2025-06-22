// main.c

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#include <getopt.h>
#include <unistd.h>
#else
// Windows compatibility for POSIX functions
#include "getopt_win.h"
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#define STDOUT_FILENO 1
#define write _write
#define fileno _fileno
#define ssize_t int
#endif

#include <omp.h>

#include "omega/details/common.h"
#include "omega/details/util.h"
#include "omega/list_matcher.h"

#define OUTPUT_BUFFER_SIZE (256 * 1024)

typedef enum { MODE_UNDEFINED = 0, MODE_COMPILE, MODE_MATCH } omg_app_mode_t;

// Flush helper: writes to console or raw file
#ifdef _WIN32
static void flush_buffer(const char *buf, size_t len) {
  HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
  DWORD written;
  if ((GetFileType(hOut) & ~FILE_TYPE_REMOTE) == FILE_TYPE_CHAR) {
    WriteConsoleA(hOut, buf, (DWORD)len, &written, NULL);
  } else {
    _write(_fileno(stdout), buf, (int)len);
  }
}
#else
static void flush_buffer(const char *buf, size_t len) {
  const ssize_t written = write(STDOUT_FILENO, buf, len);
  if (unlikely(written < 0)) {
    perror("write");
    ABORT("write");
  }
}
#endif

// Print pattern store statistics with pretty formatting
static void
print_pattern_store_stats(const omega_match_pattern_store_stats_t *s,
                          FILE *fp) {
  char buf_count[32], buf_sm[32], buf_lg[32], buf_dups[32], buf_in[32],
      buf_st[32];
  fprintf(fp,
          "Stored pattern count: %s, smallest %s, largest %s, duplicates "
          "removed: %s, input bytes: %s, stored bytes: %s, ratio: %.2f\n",
          format_u64(s->stored_pattern_count, buf_count),
          format_u64(s->smallest_pattern_length, buf_sm),
          format_u64(s->largest_pattern_length, buf_lg),
          format_u64(s->duplicate_patterns, buf_dups),
          format_u64(s->total_input_bytes, buf_in),
          format_u64(s->total_stored_bytes, buf_st),
          (float)s->total_stored_bytes / (float)s->total_input_bytes);
}

// Print match statistics with pretty formatting
static void print_match_stats(const omega_match_stats_t *stats,
                              const omega_match_results_t *results, FILE *fp) {
  char buf_hits[32], buf_filt[32], buf_miss[32], buf_att[32], buf_comp[32],
      buf_mat[32];
  fprintf(fp,
          "Total attempts: %s, filtered: %s, misses: %s, hits: %s, compares: "
          "%s, matches: %s, compare to match ratio: %.2f\n",
          format_u64(stats->total_attempts, buf_att),
          format_u64(stats->total_filtered, buf_filt),
          format_u64(stats->total_misses, buf_miss),
          format_u64(stats->total_hits, buf_hits),
          format_u64(stats->total_comparisons, buf_comp),
          format_u64(results->count, buf_mat),
          (float)stats->total_comparisons / (float)results->count);
}

// Print match results to given file descriptor or console
static void print_results_buffered_fd(const omega_match_results_t *results,
                                      const int fd, const int use_console_api) {
  char *output_buffer = calloc(1, OUTPUT_BUFFER_SIZE);
  if (unlikely(!output_buffer)) {
    ABORT("calloc output_buffer");
  }

  size_t pos = 0;
  for (size_t i = 0; i < results->count; ++i) {
    int n = snprintf(output_buffer + pos, OUTPUT_BUFFER_SIZE - pos,
                     "%zu:%.*s\n",
                     results->matches[i].offset,
                     results->matches[i].len,
                     (const char *)results->matches[i].match);
    if (n < 0) continue;
    pos += (size_t)n;

    if (pos > OUTPUT_BUFFER_SIZE - 128) {
      if (use_console_api) {
        flush_buffer(output_buffer, pos);
      } else {
        const ssize_t written = write(fd, output_buffer, pos);
        if (unlikely(written < 0)) {
          perror("write");
          ABORT("write");
        }
      }
      pos = 0;
    }
  }

  if (pos > 0) {
    if (use_console_api) {
      flush_buffer(output_buffer, pos);
    } else {
      const ssize_t written = write(fd, output_buffer, pos);
      if (unlikely(written < 0)) {
        perror("write");
        ABORT("write");
      }
    }
  }

  free(output_buffer);
}

// General help
static void usage(const char *prog) {
  fprintf(stderr, "Usage: %s [-h, --help] [-v, --verbose] <command> [<args>]\n",
          prog);
  fprintf(stderr, "\n");
  fprintf(stderr, "Commands:\n");
  fprintf(stderr, "  compile    Compile patterns\n");
  fprintf(stderr, "  match      Match patterns\n");
  fprintf(stderr, "\n");
  fprintf(stderr,
          "Run \"%s <command> --help\" for more information on a command.\n",
          prog);
  fprintf(stderr, "\n");
  fprintf(stderr, "Version: %s\n", omega_matcher_version());
}

// Help for 'compile'
static void compile_usage(const char *prog) {
  fprintf(stderr, "Usage: %s compile [options] COMPILED PATTERNS\n", prog);
  fprintf(stderr, "\nOptions:\n");
  fprintf(stderr, "  --ignore-case         Ignore case in patterns\n");
  fprintf(stderr, "  --ignore-punctuation  Ignore punctuation in patterns\n");
  fprintf(stderr, "  --elide-whitespace    Remove whitespace in patterns\n");
  fprintf(stderr, "  -v, --verbose         Enable verbose output\n");
  fprintf(stderr, "  -h, --help            Show this help message\n");
  fprintf(stderr, "\n");
  fprintf(stderr, "Version: %s\n", omega_matcher_version());
}

// Help for 'match'
static void match_usage(const char *prog) {
  fprintf(stderr, "Usage: %s match [options] COMPILED HAYSTACK\n", prog);
  fprintf(stderr, "\nOptions:\n");
  fprintf(stderr,
    "  -o, --output FILE     Write results to FILE instead of stdout "
    "(UTF-8 and LF EOL)\n");
  fprintf(stderr, "  --ignore-case         Ignore case during matching\n");
  fprintf(stderr,
          "  --ignore-punctuation  Ignore punctuation during matching\n");
  fprintf(stderr,
          "  --elide-whitespace    Remove whitespace during matching\n");
  fprintf(stderr, "  --longest             Only return longest matches\n");
  fprintf(stderr, "  --no-overlap          Avoid overlapping matches\n");
  fprintf(stderr, "  --word-boundary       Only match at word boundaries\n");
  fprintf(stderr, "  --word-prefix         Only match at word prefixes\n");
  fprintf(stderr, "  --word-suffix         Only match at word suffixes\n");
  fprintf(stderr,
          "  --line-start          Only match at the start of a line\n");
  fprintf(stderr, "  --line-end            Only match at the end of a line\n");
  fprintf(stderr, "  --threads N           Number of threads to use\n");
  fprintf(stderr,
          "  --chunk-size N        Chunk size for parallel processing\n");
  fprintf(stderr, "  -v, --verbose         Enable verbose output\n");
  fprintf(stderr, "  -h, --help            Show this help message\n");
  fprintf(stderr, "\n");
  fprintf(stderr, "Version: %s\n", omega_matcher_version());
}

int main(const int argc, char *argv[]) {
#ifdef _WIN32
  // 1) Console interprets bytes as UTF-8
  SetConsoleOutputCP(CP_UTF8);
  // 2) Disable CRT text‐mode translation on the stdout handle
  _setmode(_fileno(stdout), _O_BINARY);
#endif

  if (argc < 2) {
    usage(argv[0]);
    return EXIT_FAILURE;
  }

  // Special-case "-h compile" or "-h match"
  if ((strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) &&
      argc >= 3) {
    if (strcmp(argv[2], "compile") == 0) {
      compile_usage(argv[0]);
      return EXIT_SUCCESS;
    }
    if (strcmp(argv[2], "match") == 0) {
      match_usage(argv[0]);
      return EXIT_SUCCESS;
    }
  }
  // Global help
  if (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) {
    usage(argv[0]);
    return EXIT_SUCCESS;
  }

  // Scan for mode and any global "-v/--verbose" before mode
  omg_app_mode_t mode_flag = MODE_UNDEFINED;
  int mode_idx = -1;
  int verbose = 0;
  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "compile") == 0) {
      mode_flag = MODE_COMPILE;
      mode_idx = i;
      break;
    }
    if (strcmp(argv[i], "match") == 0) {
      mode_flag = MODE_MATCH;
      mode_idx = i;
      break;
    }
    if (strcmp(argv[i], "-v") == 0 || strcmp(argv[i], "--verbose") == 0) {
      verbose = 1;
      continue;
    }
    if (argv[i][0] == '-') {
      fprintf(stderr, "Unknown option: '%s'\n\n", argv[i]);
      usage(argv[0]);
      return EXIT_FAILURE;
    }
    fprintf(stderr, "Unknown command or misplaced argument: '%s'\n\n", argv[i]);
    usage(argv[0]);
    return EXIT_FAILURE;
  }
  if (mode_idx < 0) {
    fprintf(stderr, "No mode specified.\n\n");
    usage(argv[0]);
    return EXIT_FAILURE;
  }
  if (verbose) {
    fprintf(stderr, "Verbose mode enabled.\n");
  }

  // Build a new argv array for parsing just the subcommand's arguments
  const int new_argc = argc - mode_idx;
  char **new_argv = malloc((new_argc + 1) * sizeof(char *));
  if (!new_argv) {
    perror("malloc");
    return EXIT_FAILURE;
  }
  new_argv[0] = argv[0];
  for (int i = mode_idx + 1; i < argc; i++) {
    new_argv[i - mode_idx] = argv[i];
  }
  new_argv[new_argc] = NULL;

  // Subcommand-specific flags
  int ignore_case = 0, ignore_punctuation = 0, elide_whitespace = 0,
      longest_only = 0, no_overlap = 0, word_boundary = 0, word_prefix = 0,
      word_suffix = 0, line_start = 0, line_end = 0, threads = 0,
      chunk_size = 0, output_to_file = 0;
  const char *output_path = NULL;

  const struct option long_opts[] = {
      {"help", no_argument, NULL, 'h'},
      {"ignore-case", no_argument, &ignore_case, 1},
      {"ignore-punctuation", no_argument, &ignore_punctuation, 1},
      {"elide-whitespace", no_argument, &elide_whitespace, 1},
      {"longest", no_argument, &longest_only, 1},
      {"no-overlap", no_argument, &no_overlap, 1},
      {"word-boundary", no_argument, &word_boundary, 1},
      {"word-prefix", no_argument, &word_prefix, 1},
      {"word-suffix", no_argument, &word_suffix, 1},
      {"line-start", no_argument, &line_start, 1},
      {"line-end", no_argument, &line_end, 1},
      {"verbose", no_argument, &verbose, 1},
      {"output", required_argument, NULL, 'o'},
      {"threads", required_argument, NULL, 't'},
      {"chunk-size", required_argument, NULL, 'C'},
      {NULL, 0, NULL, 0}};

  // Parse the subcommand options
  optind = 1;
  int opt;
  while ((opt = getopt_long(new_argc, new_argv, "vt:C:", long_opts, NULL)) !=
         -1) {
    switch (opt) {
    case 'h':
      // user asked for help _inside_ the subcommand
      if (mode_flag == MODE_COMPILE) {
        compile_usage(argv[0]);
      } else {
        match_usage(argv[0]);
      }
      free(new_argv);
      return EXIT_SUCCESS;
    case 0:
      // flag was set by long_opts
      break;
    case 'v':
      verbose = 1;
      break;
    case 'o':
      output_path = optarg;
      output_to_file = 1;
      break;
    case 't':
      threads = atoi(optarg);
      if (threads <= 0) {
        fprintf(stderr, "Invalid --threads value: %s\n", optarg);
        free(new_argv);
        return EXIT_FAILURE;
      }
      break;
    case 'C':
      chunk_size = atoi(optarg);
      if (chunk_size <= 0) {
        fprintf(stderr, "Invalid --chunk-size value: %s\n", optarg);
        free(new_argv);
        return EXIT_FAILURE;
      }
      break;
    case '?':
    default:
      if (mode_flag == MODE_COMPILE) {
        compile_usage(argv[0]);
      } else {
        match_usage(argv[0]);
      }
      free(new_argv);
      return EXIT_FAILURE;
    }
  }

  // Remaining positional args
  const int pos = new_argc - optind;
  if (pos != 2) {
    if (mode_flag == MODE_COMPILE) {
      compile_usage(argv[0]);
    } else {
      match_usage(argv[0]);
    }
    free(new_argv);
    return EXIT_FAILURE;
  }
  const char *arg1 = new_argv[optind];
  const char *arg2 = new_argv[optind + 1];

  // Open output if requested
  FILE *out_fp = stdout;
  int out_fd = STDOUT_FILENO;
  int use_console_api = 0;
#ifdef _WIN32
  use_console_api = !output_to_file;
#endif
  if (output_to_file) {
    out_fp = fopen(output_path, "wb");
    if (!out_fp) { perror("fopen output file"); return EXIT_FAILURE; }
    out_fd = fileno(out_fp);
  }

  // Dispatch
  switch (mode_flag) {
  case MODE_COMPILE: {
    omega_match_pattern_store_stats_t pattern_store_stats = {0};
    omega_list_matcher_compile_patterns_filename(
        arg1, arg2, ignore_case, ignore_punctuation, elide_whitespace,
        &pattern_store_stats);
    if (verbose) {
      print_pattern_store_stats(&pattern_store_stats, stderr);
      fputs("Compile completed successfully.\n", stderr);
    }
  } break;
  case MODE_MATCH: {
    // Create the matcher
    omega_match_pattern_store_stats_t pattern_store_stats = {0};
    omega_list_matcher_t *matcher =
        omega_list_matcher_create(arg1, ignore_case, ignore_punctuation,
                                  elide_whitespace, &pattern_store_stats);
    if (verbose) {
      omega_list_matcher_emit_header_info(matcher, stderr);
    }
    // Check if matcher creation was successful
    if (!matcher) {
      fprintf(stderr, "Error: Failed to create matcher from '%s'.\n", arg1);
      free(new_argv);
      return EXIT_FAILURE;
    }
    // Print the pattern store statistics
    if (verbose && pattern_store_stats.stored_pattern_count > 0) {
      print_pattern_store_stats(&pattern_store_stats, stderr);
      omega_list_matcher_emit_header_info(matcher, stderr);
    }
    // Perform the matching
    size_t haystack_size = 0;
    const uint8_t *haystack =
        omega_matcher_map_filename(arg2, &haystack_size, 1);
    if (!haystack) {
      fprintf(stderr, "Error: Failed to map file '%s'.\n", arg2);
      omega_list_matcher_destroy(matcher);
      free(new_argv);
      return EXIT_FAILURE;
    }
    omega_match_stats_t stats = {0};
    omega_list_matcher_add_stats(matcher, &stats);
    if (threads > 0) {
      if (omega_matcher_set_num_threads(matcher, threads) != 0) {
        fprintf(stderr, "Error: thread count must be 1..%d\n",
                omp_get_max_threads());
        free(new_argv);
        return EXIT_FAILURE;
      }
    }
    if (chunk_size > 0) {
      if (omega_matcher_set_chunk_size(matcher, chunk_size) != 0) {
        fputs("Error: chunk size must be > 0\n", stderr);
        free(new_argv);
        return EXIT_FAILURE;
      }
    }
    if (verbose) {
      fprintf(stderr, "OMP threads: %d, chunk size: %d\n",
              omega_matcher_get_num_threads(matcher),
              omega_matcher_get_chunk_size(matcher));
    }
    omega_match_results_t *results = omega_list_matcher_match(
        matcher, haystack, haystack_size, no_overlap, longest_only,
        word_boundary, word_prefix, word_suffix, line_start, line_end);
    // Print the match statistics
    if (verbose) {
      // Print match statistics with pretty formatting
      print_match_stats(&stats, results, stderr);
    }
    // Print the results
    print_results_buffered_fd(results, out_fd, use_console_api);
    // Free the results
    omega_match_results_destroy(results);
    // Destroy the matcher
    omega_list_matcher_destroy(matcher);
    // Unmap the haystack file
    omega_matcher_unmap_file(haystack, haystack_size);
  } break;
  default:
    // This should never happen
    ABORT("Invalid mode");
  }
  if (output_to_file) fclose(out_fp);
  free(new_argv);
  return EXIT_SUCCESS;
}
