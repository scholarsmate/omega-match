cmake_minimum_required(VERSION 3.15)
project(omega_match VERSION 0.1.0 LANGUAGES C)

# Project Version - try to determine from git first, then fallback to hardcoded
find_package(Git QUIET)
if (Git_FOUND)
    # Try to get version from git tag
    execute_process(
        COMMAND ${GIT_EXECUTABLE} describe --tags --match "v*" --abbrev=0
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        OUTPUT_VARIABLE GIT_TAG
        ERROR_QUIET
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    
    if (GIT_TAG)
        # Extract version numbers from tag (e.g., v1.0.1 -> 1.0.1)
        string(REGEX REPLACE "^v([0-9]+)\\.([0-9]+)\\.([0-9]+).*" "\\1;\\2;\\3" VERSION_PARTS "${GIT_TAG}")
        list(LENGTH VERSION_PARTS VERSION_PARTS_COUNT)
        
        if (VERSION_PARTS_COUNT EQUAL 3)
            list(GET VERSION_PARTS 0 PROJECT_VERSION_MAJOR)
            list(GET VERSION_PARTS 1 PROJECT_VERSION_MINOR)
            list(GET VERSION_PARTS 2 PROJECT_VERSION_PATCH)
            message(STATUS "Version extracted from git tag: ${GIT_TAG}")
        else()
            message(WARNING "Could not parse git tag '${GIT_TAG}', using fallback version")
            set(PROJECT_VERSION_MAJOR 0)
            set(PROJECT_VERSION_MINOR 0)
            set(PROJECT_VERSION_PATCH 0)
        endif()
    else()
        message(STATUS "No git tag found, using fallback version")
        set(PROJECT_VERSION_MAJOR 0)
        set(PROJECT_VERSION_MINOR 0)
        set(PROJECT_VERSION_PATCH 0)
    endif()
else()
    message(STATUS "Git not found, using fallback version")
    set(PROJECT_VERSION_MAJOR 0)
    set(PROJECT_VERSION_MINOR 0)
    set(PROJECT_VERSION_PATCH 0)
endif()

set(PROJECT_VERSION "${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}.${PROJECT_VERSION_PATCH}")
message(STATUS "Project version: ${PROJECT_VERSION}")

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
option(OMEGA_MATCH_BUILD_CLI "Build the olm CLI tool" ON)
option(OMEGA_MATCH_WARNINGS_AS_ERRORS "Treat warnings as errors" ON)

# Enable sanitizers for memory and undefined behavior
option(ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
if(ENABLE_SANITIZERS)
  message(STATUS "Enabling AddressSanitizer and UndefinedBehaviorSanitizer")
  add_compile_options(-fsanitize=address -fsanitize=undefined)
  add_link_options(-fsanitize=address -fsanitize=undefined)
endif()

# ---------------------------------------------------------------------------
# Sources and include dirs
# ---------------------------------------------------------------------------
file(GLOB OMEGA_MATCH_SOURCES CONFIGURE_DEPENDS
        "omega_match/src/bloom.c"
        "omega_match/src/common.c"
        "omega_match/src/compiler.c"
        "omega_match/src/dedupe_set.c"
        "omega_match/src/hash_table.c"
        "omega_match/src/matcher.c"
        "omega_match/src/pattern_store.c"
        "omega_match/src/pattern_store_append.c"
        "omega_match/src/transform_table.c"
        "omega_match/src/util.c"
        "omega_match/src/version.c"
)

configure_file(
        omega_match/include/omega/details/version.h.in
        ${CMAKE_CURRENT_BINARY_DIR}/version.h
        @ONLY
)

# Make sure this generated file is in your include path
include_directories(${CMAKE_CURRENT_BINARY_DIR})

file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/version.txt "${PROJECT_VERSION}")

# ---------------------------------------------------------------------------
# Library targets: Build both static and shared versions
# ---------------------------------------------------------------------------
add_library(omega_match_static STATIC ${OMEGA_MATCH_SOURCES})
set_target_properties(omega_match_static PROPERTIES
    POSITION_INDEPENDENT_CODE ON               # Enable PIC for static library
    OUTPUT_NAME omega_match_static)            # libomega_match_static.a
target_include_directories(omega_match_static
    PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/omega_match/include>
    $<INSTALL_INTERFACE:include>)
target_compile_features(omega_match_static PUBLIC c_std_17)

add_library(omega_match_shared SHARED ${OMEGA_MATCH_SOURCES})
set_target_properties(omega_match_shared PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    OUTPUT_NAME omega_match)                   # libomega_match.(so|dylib) or omega_match.dll
target_include_directories(omega_match_shared
    PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/omega_match/include>
    $<INSTALL_INTERFACE:include>)
target_compile_features(omega_match_shared PUBLIC c_std_17)

# Export all symbols for Windows DLL
if (WIN32)
    # Enable automatic symbol export on Windows
    set_target_properties(omega_match_shared PROPERTIES
        WINDOWS_EXPORT_ALL_SYMBOLS TRUE
        ARCHIVE_OUTPUT_NAME omega_match        # omega_match.lib (import library)
        RUNTIME_OUTPUT_NAME omega_match        # omega_match.dll
    )
endif ()

# Create the main alias for external use (defaults to shared when available)
add_library(omega_match ALIAS omega_match_shared)


# ---------------------------------------------------------------------------
# Common library configuration (OpenMP, warnings, etc.)
# ---------------------------------------------------------------------------

# Find OpenMP (always required)
# On macOS, help CMake find libomp (which is keg-only in Homebrew)
if (APPLE)
    # Set explicit paths for macOS Homebrew libomp (keg-only package)
    set(CMAKE_PREFIX_PATH "/opt/homebrew/opt/libomp;/usr/local/opt/libomp;${CMAKE_PREFIX_PATH}")
    set(OpenMP_C_FLAGS "-Xpreprocessor -fopenmp")
    set(OpenMP_C_LIB_NAMES "omp")
    set(OpenMP_omp_LIBRARY /opt/homebrew/opt/libomp/lib/libomp.dylib)
    
    # Add fallback paths if main path doesn't exist
    if(NOT EXISTS ${OpenMP_omp_LIBRARY})
        set(OpenMP_omp_LIBRARY /usr/local/opt/libomp/lib/libomp.dylib)
    endif()
    if(NOT EXISTS ${OpenMP_omp_LIBRARY})
        find_library(OpenMP_omp_LIBRARY 
            NAMES omp gomp iomp5
            PATHS /opt/homebrew/opt/libomp/lib /usr/local/opt/libomp/lib
            NO_DEFAULT_PATH)
    endif()
    
    # Add include directories (use the keg-only paths)
    include_directories(/opt/homebrew/opt/libomp/include)
    if(EXISTS /usr/local/opt/libomp/include)
        include_directories(/usr/local/opt/libomp/include)
    endif()
    
    # Set CMake hints for OpenMP discovery
    set(OpenMP_ROOT /opt/homebrew/opt/libomp)
    if(NOT EXISTS /opt/homebrew/opt/libomp/include/omp.h AND EXISTS /usr/local/opt/libomp/include/omp.h)
        set(OpenMP_ROOT /usr/local/opt/libomp)
    endif()
endif()

find_package(OpenMP REQUIRED)

# Helper macro to avoid code duplication
macro(configure_omega_match_target target_name)
    # Always link OpenMP (required dependency)
    target_link_libraries(${target_name} PUBLIC OpenMP::OpenMP_C)
    target_compile_definitions(${target_name} PUBLIC OMEGA_MATCH_USE_OPENMP=1)

    # Compiler-specific warnings
    if (MSVC)
        target_compile_options(${target_name} PRIVATE /W4 $<$<BOOL:${OMEGA_MATCH_WARNINGS_AS_ERRORS}>:/WX>)
    else ()
        # On macOS with OpenMP, disable pedantic warnings to avoid issues with libomp headers
        if (APPLE)
            target_compile_options(${target_name} PRIVATE -Wall -Wextra
                    $<$<BOOL:${OMEGA_MATCH_WARNINGS_AS_ERRORS}>:-Werror>)
        else ()
            target_compile_options(${target_name} PRIVATE -Wall -Wextra -pedantic
                    $<$<BOOL:${OMEGA_MATCH_WARNINGS_AS_ERRORS}>:-Werror>)
        endif ()
    endif ()
endmacro()

# Apply configuration to both libraries
configure_omega_match_target(omega_match_static)
configure_omega_match_target(omega_match_shared)

# ---------------------------------------------------------------------------
# Optional CLI tool (always uses static library to avoid DLL issues)
# ---------------------------------------------------------------------------
if (OMEGA_MATCH_BUILD_CLI)
    if (WIN32)
        # On Windows, include our custom getopt implementation
        add_executable(olm omega_match/main.c omega_match/getopt_win.c)
    else()
        add_executable(olm omega_match/main.c)
    endif()

    target_include_directories(olm
            PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/omega_match/include
    )

    # Always link CLI tool against static library for simplicity and portability
    target_link_libraries(olm PRIVATE omega_match_static)
    target_compile_features(olm PRIVATE c_std_17)

    # Always link OpenMP for CLI tool (required dependency)
    target_link_libraries(olm PRIVATE OpenMP::OpenMP_C)

    install(TARGETS olm RUNTIME DESTINATION bin)
endif ()

# ---------------------------------------------------------------------------
# Cross-platform test suite
# ---------------------------------------------------------------------------
enable_testing()

# Find Python interpreter for cross-platform tests
find_package(Python3 COMPONENTS Interpreter REQUIRED)

if (OMEGA_MATCH_BUILD_CLI)
    # Visual Studio specific configuration for tests
    if(MSVC)
        # This ensures tests can find the executable in configuration subdirectories
        set(CMAKE_CTEST_ARGUMENTS "--build-config \${CTEST_CONFIGURATION_TYPE}")

        # For VS builds, print a helpful message about running tests
        message(STATUS "Visual Studio build: To run tests, use 'ctest -C Debug' or 'ctest -C Release'")
    endif()

    # Helper macro to add a test with properties
    macro(omega_add_test name)
        add_test(NAME ${name} COMMAND $<TARGET_FILE:olm> ${ARGN})
        set_tests_properties(${name} PROPERTIES LABELS "olm")
    endmacro()

    omega_add_test(help_test --help)
    set_tests_properties(help_test PROPERTIES PASS_REGULAR_EXPRESSION "Usage:")

    omega_add_test(version_test --help)
    set_tests_properties(version_test PROPERTIES PASS_REGULAR_EXPRESSION "Version: [0-9]+\\.[0-9]+\\.[0-9]+")

    omega_add_test(compile_test compile
        "${CMAKE_CURRENT_BINARY_DIR}/test_patterns.olm"
        "${CMAKE_CURRENT_SOURCE_DIR}/data/small_pats.txt")
    set_tests_properties(compile_test PROPERTIES TIMEOUT 30)

    omega_add_test(match_test match
        "${CMAKE_CURRENT_BINARY_DIR}/test_patterns.olm"
        "${CMAKE_CURRENT_SOURCE_DIR}/data/small_hay.txt")
    set_tests_properties(match_test PROPERTIES DEPENDS compile_test TIMEOUT 30)

    # Cross-platform Python tests
    file(REAL_PATH "${CMAKE_CURRENT_SOURCE_DIR}/data" DATA_DIR_ABS)

    # Helper function for Python-based tests
    function(omega_match_add_python_test name script)
        add_test(NAME ${name}
                COMMAND ${Python3_EXECUTABLE} "${script}" $<TARGET_FILE:olm> "${DATA_DIR_ABS}" ${ARGN})
        set_tests_properties(${name} PROPERTIES
                LABELS "olm_extended"
                ENVIRONMENT "VALGRIND=${VALGRIND}"
                TIMEOUT 120)
    endfunction()

    # Add comprehensive Python test suite
    omega_match_add_python_test(aio "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio.py")
    omega_match_add_python_test(aio_wp "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_wp.py")
    omega_match_add_python_test(aio_ws "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_ws.py")
    omega_match_add_python_test(aio_longest_no_overlap "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_longest_no_overlap.py")
    omega_match_add_python_test(aio_longest_no_overlap_ci "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_longest_no_overlap_ci.py")
    omega_match_add_python_test(aio_longest_no_overlap_ci_wb "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_longest_no_overlap_ci_wb.py")
    omega_match_add_python_test(aio_longest_no_overlap_wb "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_longest_no_overlap_wb.py")
    omega_match_add_python_test(aio_line_start "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_line_start.py")
    omega_match_add_python_test(aio_line_end "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_line_end.py")
    omega_match_add_python_test(aio_line_start_wb "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_line_start_wb.py")
    omega_match_add_python_test(aio_line_exact_match "${CMAKE_CURRENT_SOURCE_DIR}/tests/aio_line_exact_match.py")
    omega_match_add_python_test(compile_match "${CMAKE_CURRENT_SOURCE_DIR}/tests/compile_match.py")

    message(STATUS "Added core cross-platform tests: help, version, basic_match, compile")
    message(STATUS "Added Python-based cross-platform extended tests")
endif()

# ---------------------------------------------------------------------------
# Install rules
# ---------------------------------------------------------------------------

# Always install static library
install(TARGETS omega_match_static
        EXPORT omega_matchTargets
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin)

# Conditionally install shared library
install(TARGETS omega_match_shared
        EXPORT omega_matchTargets
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin)

install(DIRECTORY omega_match/include/ DESTINATION omega_match/include)

# ---------------------------------------------------------------------------
# CMake package config (optional but now functional)
# ---------------------------------------------------------------------------
include(CMakePackageConfigHelpers)

export(EXPORT omega_matchTargets
        FILE "${CMAKE_CURRENT_BINARY_DIR}/omega_matchTargets.cmake"
        NAMESPACE omega_match::)

write_basic_package_version_file(
        "${CMAKE_CURRENT_BINARY_DIR}/omega_matchConfigVersion.cmake"
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion)

configure_package_config_file(
        cmake/omega_matchConfig.cmake.in                    # small template – see below
        "${CMAKE_CURRENT_BINARY_DIR}/omega_matchConfig.cmake"
        INSTALL_DESTINATION lib/cmake/omega_match)

install(FILES
        "${CMAKE_CURRENT_BINARY_DIR}/omega_matchConfig.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/omega_matchConfigVersion.cmake"
        DESTINATION lib/cmake/omega_match)

install(EXPORT omega_matchTargets
        FILE omega_matchTargets.cmake
        NAMESPACE omega_match::
        DESTINATION lib/cmake/omega_match)

# ---------------------------------------------------------------------------
# Packaging with CPack
# ---------------------------------------------------------------------------
include(InstallRequiredSystemLibraries)

set(CPACK_PACKAGE_NAME "omega_matchmatch")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_PACKAGE_CONTACT "omega_matchmatch maintainers")
set(CPACK_PACKAGE_FILE_NAME
    "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-${CMAKE_SYSTEM_NAME}-${CMAKE_SYSTEM_PROCESSOR}")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE")

if(CMAKE_SYSTEM_NAME STREQUAL "Windows")
    set(CPACK_GENERATOR "ZIP")
    find_program(WIX_CANDLE_EXECUTABLE NAMES candle.exe candle)
    if(WIX_CANDLE_EXECUTABLE)
        # Copy license file with .txt extension for WiX
        configure_file("${CMAKE_CURRENT_SOURCE_DIR}/LICENSE"
                       "${CMAKE_CURRENT_BINARY_DIR}/LICENSE.txt" COPYONLY)
        set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_BINARY_DIR}/LICENSE.txt")
        list(APPEND CPACK_GENERATOR "WIX")
        set(CPACK_WIX_UPGRADE_GUID "0d7858ad-85b2-446d-8e5b-54f876ed5277")
    endif()
else()
    set(CPACK_GENERATOR "TGZ")
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        list(APPEND CPACK_GENERATOR "DEB" "RPM")
        set(CPACK_DEBIAN_PACKAGE_MAINTAINER "omega_matchmatch maintainers")
        set(CPACK_RPM_PACKAGE_LICENSE "Apache 2.0")
    endif()
endif()

include(CPack)

# ---------------------------------------------------------------------------
# Copy shared library to Python bindings with platform-specific name
# ---------------------------------------------------------------------------
set(PYBINDINGS_LIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/bindings/python/omega_match/native/lib")
file(MAKE_DIRECTORY ${PYBINDINGS_LIB_DIR})

if (WIN32)
    # Only x64 currently provided for Windows
    if (CMAKE_SIZEOF_VOID_P EQUAL 8)
        add_custom_command(TARGET omega_match_shared POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:omega_match_shared>
                "${PYBINDINGS_LIB_DIR}/libomega_match-windows-x64.dll"
            COMMENT "Copying Windows x64 DLL to Python bindings native/lib directory"
        )
    endif()
elseif(APPLE)
    if (CMAKE_OSX_ARCHITECTURES MATCHES "arm64" OR CMAKE_SYSTEM_PROCESSOR MATCHES "arm64")
        add_custom_command(TARGET omega_match_shared POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:omega_match_shared>
                "${PYBINDINGS_LIB_DIR}/libomega_match-macos-arm64.dylib"
            COMMENT "Copying macOS arm64 dylib to Python bindings native/lib directory"
        )
    elseif (CMAKE_OSX_ARCHITECTURES MATCHES "x86_64" OR CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64")
        add_custom_command(TARGET omega_match_shared POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:omega_match_shared>
                "${PYBINDINGS_LIB_DIR}/libomega_match-macos-x64.dylib"
            COMMENT "Copying macOS x64 dylib to Python bindings native/lib directory"
        )
    endif()
elseif(UNIX)
    if (CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64")
        add_custom_command(TARGET omega_match_shared POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:omega_match_shared>
                "${PYBINDINGS_LIB_DIR}/libomega_match-linux-x64.so"
            COMMENT "Copying Linux x64 .so to Python bindings native/lib directory"
        )
    elseif (CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" OR CMAKE_SYSTEM_PROCESSOR MATCHES "arm64")
        add_custom_command(TARGET omega_match_shared POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:omega_match_shared>
                "${PYBINDINGS_LIB_DIR}/libomega_match-linux-arm64.so"
            COMMENT "Copying Linux arm64 .so to Python bindings native/lib directory"
        )
    endif()
endif()

# ---------------------------------------------------------------------------
# Build Python wheel for bindings (optional target)
# ---------------------------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter REQUIRED)
add_custom_target(python_wheel
    COMMAND ${Python3_EXECUTABLE} -m build --wheel
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/python
    COMMENT "Building Python wheel for omega_match Python bindings"
)
add_dependencies(python_wheel omega_match_shared)

add_custom_target(python_binding_tests
    COMMAND ${Python3_EXECUTABLE} -m pip install -e .
    COMMAND ${Python3_EXECUTABLE} -m pytest tests
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/python
    COMMENT "Running Python pytest suite for omega_match"
)
add_dependencies(python_binding_tests python_wheel)

add_test(NAME python_pytest
    COMMAND ${Python3_EXECUTABLE} -m pytest tests
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/python
)
