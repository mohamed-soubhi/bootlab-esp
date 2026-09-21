# SPDX-License-Identifier: Apache-2.0

# LABID common library — dual build integration.
#
# This single CMakeLists.txt serves BOTH build systems from the same
# on-disk directory (common/labid is both the Zephyr module root and the
# IDF component root):
#
#   - ESP-IDF component build (idf_component.yml): the IDF build system
#     sets ESP_PLATFORM=1 (per Espressif build-system docs), so we call
#     idf_component_register().
#   - Zephyr module build (zephyr/module.yml -> cmake: .): ESP_PLATFORM is
#     not set; we compile the sources into a Zephyr library when
#     CONFIG_LABID is enabled. Kconfig is at the module root (Kconfig).
#
# The two paths are mutually exclusive by construction.

if(ESP_PLATFORM)
  # --- ESP-IDF component ---
  idf_component_register(
    SRCS "src/labid.c" "src/labid_dispatch.c"
    INCLUDE_DIRS "include"
  )
else()
  # --- Zephyr module ---
  if(CONFIG_LABID)
    zephyr_library()
    zephyr_library_sources(${CMAKE_CURRENT_SOURCE_DIR}/src/labid.c
                           ${CMAKE_CURRENT_SOURCE_DIR}/src/labid_dispatch.c)
    zephyr_library_include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)
    zephyr_include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)
  endif()
endif()
