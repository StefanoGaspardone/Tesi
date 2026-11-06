cmake_minimum_required(VERSION 3.20)

project(c2_exhaustive_c LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

find_package(Threads REQUIRED)

add_executable(c2_exhaustive_c
    main.c
)

target_link_libraries(c2_exhaustive_c PRIVATE
    Threads::Threads
)

if(UNIX)
    target_link_libraries(c2_exhaustive_c PRIVATE m)
endif()

target_compile_options(c2_exhaustive_c PRIVATE
    $<$<AND:$<CONFIG:Release>,$<NOT:$<C_COMPILER_ID:MSVC>>>:-O3>
    $<$<AND:$<CONFIG:Release>,$<C_COMPILER_ID:MSVC>>:/O2>
)

if(MSVC)
    set_property(TARGET c2_exhaustive_c PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
    )
elseif(MINGW)
    target_link_options(c2_exhaustive_c PRIVATE
        -static
        -static-libgcc
    )
endif()