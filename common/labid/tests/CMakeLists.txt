# BL-011 — Unity host tests for the LABID library
cmake_minimum_required(VERSION 3.16)
project(labid_tests C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Strict warnings
add_compile_options(-Wall -Wextra)

set(UNITY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/unity)

add_executable(test_labid
    test_labid.c
    ${UNITY_DIR}/src/unity.c
    ../src/labid.c
)
target_include_directories(test_labid PRIVATE
    ../include
    ${UNITY_DIR}/src
)

enable_testing()
add_test(NAME labid COMMAND test_labid)
