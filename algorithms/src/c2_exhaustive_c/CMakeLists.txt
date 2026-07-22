cmake_minimum_required(VERSION 3.20)
project(c2_exhaustive_c C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_FLAGS_RELEASE "-O3")

find_package(Threads REQUIRED)

add_executable(c2_exhaustive_c main.c)
target_link_libraries(c2_exhaustive_c PRIVATE Threads::Threads m)