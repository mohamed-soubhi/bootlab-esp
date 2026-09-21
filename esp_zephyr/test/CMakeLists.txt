# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

# Register common/labid as an extra Zephyr module
list(APPEND EXTRA_ZEPHYR_MODULES "${CMAKE_CURRENT_SOURCE_DIR}/../../common/labid")

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(labid_zephyr_test)

target_sources(app PRIVATE src/main.c)
