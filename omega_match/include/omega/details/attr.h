// attr.h

#ifndef OMEGA_LIST_MATCHER__DETAILS__ATTR_H
#define OMEGA_LIST_MATCHER__DETAILS__ATTR_H

/* Try the standard C23 attribute first *iff* we are compiling as C23+.  */
#if defined(__has_c_attribute)
#if __has_c_attribute(fallthrough) && defined(__STDC_VERSION__) &&             \
    (__STDC_VERSION__ >= 202311L)
#define OLM_FALLTHROUGH [[fallthrough]]
#endif
#endif

/* Otherwise fall back to the GCC / Clang attribute (safe with -pedantic). */
#ifndef OLM_FALLTHROUGH
#if defined(__GNUC__) && (__GNUC__ >= 7)
#define OLM_FALLTHROUGH __attribute__((fallthrough))
#else
/* Last‑chance placeholder still understood by GCC’s -Wimplicit‑fallthrough. */
#define OLM_FALLTHROUGH /* fallthrough */
#endif
#endif

// Cross-platform struct packing macro
#if defined(_MSC_VER)
#define OLM_PACKED_STRUCT(definition)                                          \
  __pragma(pack(push, 1)) definition __pragma(pack(pop))
#else
#define OLM_PACKED_STRUCT(definition) definition __attribute__((packed))
#endif

// Cross-platform always_inline macro
#if defined(_MSC_VER)
#define OLM_ALWAYS_INLINE __forceinline
#elif defined(__GNUC__) || defined(__clang__)
#define OLM_ALWAYS_INLINE __attribute__((always_inline)) inline
#else
#define OLM_ALWAYS_INLINE inline
#endif

// Portable prefetch hint
#if defined(_MSC_VER)
#define OLM_PREFETCH(addr) ((void)0)
#else
#define OLM_PREFETCH(addr) __builtin_prefetch((addr), 0, 1)
#endif

#endif // OMEGA_LIST_MATCHER__DETAILS__ATTR_H
