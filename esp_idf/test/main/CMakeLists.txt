cmake_minimum_required(VERSION 3.22)

idf_component_register(
  SRCS "main.c"
  INCLUDE_DIRS "."
  REQUIRES labid
)
