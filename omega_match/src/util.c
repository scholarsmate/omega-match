// util.c

#include <ctype.h> // for toupper
#include <stddef.h>
#include <stdint.h>

#include "omega/details/common.h"
#include "omega/details/util.h"
#include "omega/list_matcher.h"

#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0602 // Compile for Windows 8 or later
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

// Define target architecture for Windows headers
#if defined(_M_X64) || defined(__x86_64__)
#ifndef _AMD64_
#define _AMD64_
#endif
#elif defined(_M_IX86) || defined(__i386__)
#ifndef _X86_
#define _X86_
#endif
#elif defined(_M_ARM64) || defined(__aarch64__)
#ifndef _ARM64_
#define _ARM64_
#endif
#elif defined(_M_ARM) || defined(__arm__)
#ifndef _ARM_
#define _ARM_
#endif
#endif

#include <io.h> // for _get_osfhandle
#include <memoryapi.h>
#include <windows.h>

int oa_matcher_access(const char *restrict filename) {
  if (!filename) {
    ABORT("oa_matcher_access: invalid filename");
  }

  // Check if the file exists and is readable
  return _access(filename, 4); // 4 = R_OK
}

uint8_t *omega_matcher_map_file(FILE *restrict file, size_t *restrict size,
                                const int prefetch_sequential) {
  if (!file) {
    ABORT("omega_matcher_map_file: invalid file pointer");
  }

  int fd = _fileno(file);
  if (fd < 0) {
    ABORT("omega_matcher_map_file: invalid file descriptor");
  }

  // Reopen file handle from descriptor
  intptr_t os_handle = _get_osfhandle(fd);
  if (os_handle == -1) {
    ABORT(
        "omega_matcher_map_file: failed to get OS handle from file descriptor");
  }

  HANDLE hMap =
      CreateFileMappingA((HANDLE)os_handle, NULL, PAGE_READONLY, 0, 0, NULL);
  if (hMap == NULL) {
    ABORT("omega_matcher_map_file: CreateFileMapping failed");
  }

  void *addr = MapViewOfFile(hMap, FILE_MAP_READ, 0, 0, 0);
  CloseHandle(hMap);

  if (addr && size) {
    LARGE_INTEGER fileSize;
    HANDLE hFile = (HANDLE)os_handle;
    if (GetFileSizeEx(hFile, &fileSize)) {
      *size = (size_t)fileSize.QuadPart;
    }
  }

#if (_WIN32_WINNT >= 0x0602)
  if (addr && prefetch_sequential) {
    WIN32_MEMORY_RANGE_ENTRY range;
    range.VirtualAddress = addr;
    range.NumberOfBytes = (SIZE_T)(*size);

    PrefetchVirtualMemory(GetCurrentProcess(), 1, &range, 0);
  }
#else
  (void)prefetch_sequential;
#endif

  return (addr == NULL) ? NULL : (uint8_t *)addr;
}

uint8_t *omega_matcher_map_filename(const char *restrict filename,
                                    size_t *restrict size,
                                    const int prefetch_sequential) {
  if (!filename) {
    ABORT("omega_matcher_map_filename: invalid filename");
  }

  FILE *file = fopen(filename, "rb");
  if (!file) {
    perror("fopen");
    ABORT("omega_matcher_map_filename: failed to open file");
  }

  uint8_t *addr = omega_matcher_map_file(file, size, prefetch_sequential);
  fclose(file); // Safe to close, mapping remains valid

  return addr;
}

int omega_matcher_unmap_file(const uint8_t *addr, const size_t size) {
  (void)size; // size is not needed for UnmapViewOfFile
  if (!addr) {
    ABORT("omega_matcher_unmap_file: invalid address");
  }
  UnmapViewOfFile((void *)addr);
  return 0;
}

#else // POSIX

#include <fcntl.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

int oa_matcher_access(const char *restrict filename) {
  if (!filename) {
    ABORT("oa_matcher_access: invalid filename");
  }

  // Check if the file exists and is readable
  return access(filename, R_OK);
}

// Map a file descriptor into memory for reading.
static inline uint8_t *map_file_descriptor(const int file_descriptor,
                                           size_t *restrict size,
                                           int prefetch_sequential) {
  if (unlikely(file_descriptor <= 0)) {
    ABORT("map_file_descriptor: invalid file descriptor");
  }

  struct stat st;
  if (unlikely(fstat(file_descriptor, &st) < 0)) {
    perror("fstat");
    ABORT("map_file_descriptor: failed to stat file");
  }

  if (size) {
    *size = st.st_size;
  }

  if (unlikely(st.st_size == 0)) {
    fprintf(stderr, "File is empty\n");
    return NULL;
  }

  if (unlikely(!S_ISREG(st.st_mode))) {
    ABORT("map_file_descriptor: file is not regular");
  }

  // Check explicitly for readability
  const int flags = fcntl(file_descriptor, F_GETFL);
  if (unlikely(flags == -1)) {
    perror("fcntl");
    ABORT("map_file_descriptor: failed to get file flags");
  }

  if (unlikely((flags & O_ACCMODE) == O_WRONLY)) {
    ABORT("map_file_descriptor: file descriptor is write-only");
  }

  void *addr =
      mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, file_descriptor, 0);
  if (unlikely(addr == MAP_FAILED)) {
    perror("mmap");
    ABORT("map_file_descriptor: mmap failed");
  }

  // Advise kernel to prefetch pages sequentially (macros defined in
  // <sys/mman.h>)
#ifdef POSIX_MADV_WILLNEED
  if (prefetch_sequential) {
    posix_madvise(addr, st.st_size, POSIX_MADV_SEQUENTIAL);
  }
#elif defined(MADV_WILLNEED)
  if (prefetch_sequential) {
    madvise(addr, st.st_size, MADV_SEQUENTIAL);
  }
#endif

  return addr;
}

// Map a file into memory for reading.
uint8_t *omega_matcher_map_file(FILE *restrict file, size_t *restrict size,
                                const int prefetch_sequential) {
  if (unlikely(!file)) {
    ABORT("omega_matcher_map_file: invalid file pointer");
  }

  // Get the file descriptor from the FILE pointer
  const int fd = fileno(file);
  if (unlikely(fd < 0)) {
    ABORT("omega_matcher_map_file: invalid file descriptor");
  }

  return map_file_descriptor(fd, size, prefetch_sequential);
}

// Map a file into memory for reading
uint8_t *omega_matcher_map_filename(const char *restrict filename,
                                    size_t *restrict size,
                                    const int prefetch_sequential) {
  if (unlikely(!filename)) {
    ABORT("omega_matcher_map_filename: invalid filename");
  }

  // Open the file descriptor
  const int fd = open(filename, O_RDONLY);
  if (unlikely(fd < 0)) {
    perror("open");
    ABORT("omega_matcher_map_filename: failed to open file");
  }

  // Map the file into memory
  uint8_t *addr = map_file_descriptor(fd, size, prefetch_sequential);
  close(fd); // Close the file descriptor after mapping
  return addr;
}

// Unmap a memory-mapped region
int omega_matcher_unmap_file(const uint8_t *restrict addr, const size_t size) {
  if (unlikely(!addr || size <= 0)) {
    ABORT("omega_matcher_unmap_file: invalid address or size");
  }
  munmap((void *)addr, size);
  return 0;
}

#endif
