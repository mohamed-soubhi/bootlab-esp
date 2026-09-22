# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

# Register common/labid module
list(APPEND EXTRA_ZEPHYR_MODULES "${CMAKE_CURRENT_SOURCE_DIR}/../../common/labid")

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(bootlab_zephyr_app)

target_sources(app PRIVATE
    src/main.c
    src/app_blink_timing.c
    src/labid_port_zephyr.c
    src/app_self_test.c
    src/app_ble_smp.c
)
