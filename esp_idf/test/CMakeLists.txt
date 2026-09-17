cmake_minimum_required(VERSION 3.22)

# BL-014: validate the LABID IDF component builds for the linux (host) target.
# Uses the ESP-IDF host test harness (see e.g. components/<comp>/host_test).
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Only build the app + our LABID component; host tests do NOT bring in the
# full hardware component tree (that pulls managed/hal components unsupported
# on the linux target).
set(COMPONENTS main labid)

# Pull in our LABID component (common/labid is the component root).
list(APPEND EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_SOURCE_DIR}/../../common/labid")

project(labid_host_test)
