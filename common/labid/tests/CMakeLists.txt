# BL-011 — Unity host tests for the LABID library
# Test vectors are loaded from test_vectors.json at build time via
# gen_test_vectors_h.py (single source of truth shared with Python labid.py).
cmake_minimum_required(VERSION 3.16)
project(labid_tests C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra)

set(UNITY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/unity)
set(VECTORS_JSON ${CMAKE_CURRENT_SOURCE_DIR}/../test_vectors.json)
set(GEN ${CMAKE_CURRENT_SOURCE_DIR}/gen_test_vectors_h.py)
set(GEN_HEADER ${CMAKE_CURRENT_BINARY_DIR}/test_vectors.h)

# Generate test_vectors.h from test_vectors.json before building
add_custom_command(
    OUTPUT ${GEN_HEADER}
    COMMAND python3 ${GEN} ${VECTORS_JSON} ${GEN_HEADER}
    DEPENDS ${GEN} ${VECTORS_JSON}
    COMMENT "Generating test_vectors.h from test_vectors.json"
    VERBATIM
)
add_custom_target(gen_vectors DEPENDS ${GEN_HEADER})

add_executable(test_labid
    test_labid.c
    ${UNITY_DIR}/src/unity.c
    ../src/labid.c
)
add_dependencies(test_labid gen_vectors)
target_include_directories(test_labid PRIVATE
    ../include
    ${UNITY_DIR}/src
    ${CMAKE_CURRENT_BINARY_DIR}   # for test_vectors.h
)

enable_testing()
add_test(NAME labid COMMAND test_labid)
