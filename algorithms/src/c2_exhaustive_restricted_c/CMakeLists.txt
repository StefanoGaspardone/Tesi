cmake_minimum_required(VERSION 3.20)
project(c2_exhaustive_restricted_c C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_FLAGS_RELEASE "-O3")

find_package(Threads REQUIRED)

add_executable(c2_exhaustive_restricted_c main.c)
target_link_libraries(c2_exhaustive_restricted_c PRIVATE Threads::Threads m)

if(WIN32)
    target_link_options(c2_exhaustive_restricted_c PRIVATE -static-libgcc)

    add_custom_command(TARGET c2_exhaustive_restricted_c POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "C:/Program Files/JetBrains/CLion 2025.3.4/bin/mingw/bin/libwinpthread-1.dll"
            "$<TARGET_FILE_DIR:c2_exhaustive_restricted_c>"
    )
endif()