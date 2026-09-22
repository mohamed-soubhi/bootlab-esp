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
    src/app_wifi.c
)

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../credentials.env")
  file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/../../credentials.env" CRED_LINES)
  foreach(line ${CRED_LINES})
    if(line MATCHES "^WIFI_SSID=\"?([^\"]+)\"?")
      set(ENV_WIFI_SSID "${CMAKE_MATCH_1}")
    elseif(line MATCHES "^WIFI_PSK=\"?([^\"]+)\"?")
      set(ENV_WIFI_PSK "${CMAKE_MATCH_1}")
    endif()
  endforeach()
  if(ENV_WIFI_SSID)
    target_compile_definitions(app PRIVATE
      APP_WIFI_SSID="${ENV_WIFI_SSID}"
      APP_WIFI_PSK="${ENV_WIFI_PSK}"
    )
  endif()
endif()

