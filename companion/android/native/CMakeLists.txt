# libobai.so for the OpenBridge Companion: llama.cpp + whisper.cpp sharing one ggml, plus the JNI layer.
# Built by `python -m dev.build_companion_ai` (Android NDK, arm64-v8a). The sources of llama.cpp and whisper.cpp
# (MIT) are not vendored: pass their folders with -DOB_LLAMA_DIR and -DOB_WHISPER_DIR.
cmake_minimum_required(VERSION 3.22)
project(obai C CXX)

set(OB_LLAMA_DIR "" CACHE PATH "llama.cpp source folder")
set(OB_WHISPER_DIR "" CACHE PATH "whisper.cpp source folder")
if (NOT EXISTS "${OB_LLAMA_DIR}/include/llama.h" OR NOT EXISTS "${OB_WHISPER_DIR}/include/whisper.h")
    message(FATAL_ERROR "Set OB_LLAMA_DIR and OB_WHISPER_DIR to the llama.cpp and whisper.cpp source folders")
endif()

set(CMAKE_CXX_STANDARD 17)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
foreach(opt LLAMA_BUILD_TESTS LLAMA_BUILD_EXAMPLES LLAMA_BUILD_TOOLS LLAMA_BUILD_SERVER LLAMA_BUILD_COMMON LLAMA_CURL
            LLAMA_OPENSSL WHISPER_BUILD_TESTS WHISPER_BUILD_EXAMPLES WHISPER_BUILD_SERVER WHISPER_SDL2 WHISPER_CURL
            GGML_OPENMP GGML_NATIVE GGML_BUILD_TESTS GGML_BUILD_EXAMPLES)
    set(${opt} OFF CACHE BOOL "" FORCE)
endforeach()

# llama.cpp first: whisper.cpp then reuses its ggml target (both only add ggml when no target exists yet).
add_subdirectory(${OB_LLAMA_DIR} llama EXCLUDE_FROM_ALL)
add_subdirectory(${OB_WHISPER_DIR} whisper EXCLUDE_FROM_ALL)

add_library(obai SHARED obai.cpp)
target_link_libraries(obai PRIVATE llama whisper log android)
target_link_options(obai PRIVATE -Wl,--gc-sections -Wl,-z,max-page-size=16384)
set_target_properties(obai PROPERTIES CXX_VISIBILITY_PRESET hidden)
