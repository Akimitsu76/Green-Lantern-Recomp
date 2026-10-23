cmake_minimum_required(VERSION 3.25)
project(AsterReXGpuCacheReview LANGUAGES C CXX)

# Deliberately separate from the game and SDK build/install trees. No install
# rule and no staging into the live game's directory exist in this project.
get_filename_component(ASTER_WORKSPACE "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(ASTER_REX_SOURCE "${ASTER_WORKSPACE}/.aster/tools/rexglue-sdk" CACHE PATH "Patched SDK source")
set(ASTER_REX_PREFIX "${ASTER_WORKSPACE}/.aster/tools/rexglue-0.10.0/linux-amd64" CACHE PATH "Matching prebuilt SDK")
set(ASTER_GLSLANG_SOURCE "${ASTER_REX_SOURCE}/thirdparty/glslang" CACHE PATH "Pinned glslang headers")

set(ASTER_HUMAN_STATUS "${ASTER_WORKSPACE}/.aster/reports/rex-history/027-human-play-session/status.json")
include("${CMAKE_CURRENT_LIST_DIR}/check_session.cmake")

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(AMD64|x86_64)$")
    message(FATAL_ERROR "This isolated experiment supports Linux x86_64 only")
endif()
if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang" OR CMAKE_CXX_COMPILER_VERSION VERSION_LESS 18)
    message(FATAL_ERROR "Use Clang 18 or newer, matching the SDK's C++ ABI")
endif()
if(CMAKE_CONFIGURATION_TYPES OR NOT CMAKE_BUILD_TYPE MATCHES "^(Release|RelWithDebInfo)$")
    message(FATAL_ERROR "Use a single-config build matching the host: Release or RelWithDebInfo")
endif()
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(ASTER_PINNED_ARCHIVE_SOURCES "Source archives verified by Aster SHA-256" OFF)
if(NOT ASTER_PINNED_ARCHIVE_SOURCES)
find_package(Git REQUIRED)
execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${ASTER_REX_SOURCE}" rev-parse HEAD
    OUTPUT_VARIABLE _sdk_commit OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE _git_result)
if(NOT _git_result EQUAL 0 OR NOT _sdk_commit STREQUAL "f5337cdc947ff6d4c4196737e2c807a48f2a1fc2")
    message(FATAL_ERROR "Source must be the exact reviewed ReXGlue v0.10.0 commit")
endif()
if(NOT EXISTS "${ASTER_GLSLANG_SOURCE}/SPIRV/SpvBuilder.h")
    message(FATAL_ERROR "Prebuilt SDK omits glslang headers. Populate ONLY the pinned glslang submodule f4f1d8a352ca1908943aea2ad8c54b39b4879080, then retry. Do not substitute system headers.")
endif()
execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${ASTER_GLSLANG_SOURCE}" rev-parse HEAD
    OUTPUT_VARIABLE _glslang_commit OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE _git_result)
if(NOT _git_result EQUAL 0 OR NOT _glslang_commit STREQUAL "f4f1d8a352ca1908943aea2ad8c54b39b4879080")
    message(FATAL_ERROR "glslang headers do not match the SDK-pinned source commit")
endif()

endif()

# This loads imported targets only; it does not add or compile the SDK tree.
list(PREPEND CMAKE_PREFIX_PATH "${ASTER_REX_PREFIX}")
find_package(Threads REQUIRED)
find_package(rexglue 0.10.0 EXACT CONFIG REQUIRED
    PATHS "${ASTER_REX_PREFIX}/lib/cmake/rexglue" NO_DEFAULT_PATH)

# Source list follows SDK src/graphics/CMakeLists.txt at the exact commit above.
set(_gpu_sources
    plugin_main.cpp flags.cpp register_file.cpp registers.cpp
    pipeline/shader/shader.cpp format/ucode.cpp sampler_info.cpp
    graphics_system.cpp command_processor.cpp util/draw_extent_estimator.cpp
    util/draw.cpp packet_disassembler.cpp primitive_processor.cpp
    pipeline/render_target/cache.cpp shared_memory.cpp pipeline/texture/cache.cpp
    pipeline/shader/interpreter.cpp pipeline/shader/translator.cpp
    pipeline/shader/translator_disasm.cpp
    pipeline/shader/spirv_builder.cpp pipeline/shader/spirv.cpp
    pipeline/shader/spirv_translator.cpp pipeline/shader/spirv_translator_alu.cpp
    pipeline/shader/spirv_translator_fetch.cpp pipeline/shader/spirv_translator_memexport.cpp
    pipeline/shader/spirv_translator_rb.cpp
    vulkan/graphics_system.cpp vulkan/deferred_command_buffer.cpp
    vulkan/command_processor.cpp vulkan/pipeline_cache.cpp vulkan/primitive_processor.cpp
    vulkan/render_target_cache.cpp vulkan/shader.cpp vulkan/shared_memory.cpp
    vulkan/texture_cache.cpp)
list(TRANSFORM _gpu_sources PREPEND "${ASTER_REX_SOURCE}/src/graphics/")
foreach(_source IN LISTS _gpu_sources)
    if(NOT EXISTS "${_source}")
        message(FATAL_ERROR "Missing SDK GPU source: ${_source}")
    endif()
endforeach()

add_library(aster_rexgpu_xenos SHARED ${_gpu_sources})
set_target_properties(aster_rexgpu_xenos PROPERTIES
    OUTPUT_NAME rexgpu-xenos
    RELWITHDEBINFO_POSTFIX rd
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/isolated-runtime"
    CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON
    BUILD_RPATH "${ASTER_REX_PREFIX}/lib")
target_include_directories(aster_rexgpu_xenos BEFORE PRIVATE
    "${ASTER_REX_SOURCE}/include" "${ASTER_GLSLANG_SOURCE}"
    "${ASTER_REX_PREFIX}/include/renderdoc")
target_compile_definitions(aster_rexgpu_xenos PRIVATE
    REX_HAS_VULKAN=1 REX_HAS_D3D12=0 REX_PLATFORM_LINUX=1 REXGLUE_BUILD_CONFIG="${CMAKE_BUILD_TYPE}")
target_compile_options(aster_rexgpu_xenos PRIVATE
    -march=x86-64-v2 -mcmodel=large -fno-strict-aliasing -ffp-model=strict
    -fno-char8_t -Wall -Wextra -Wno-unused-variable)
# Match upstream's PCH rather than relying on accidental umbrella includes.
target_precompile_headers(aster_rexgpu_xenos PRIVATE
    <mutex> <unordered_map> <rex/math.h> <rex/memory.h> <rex/thread/mutex.h>
    <rex/system/xmemory.h> <rex/graphics/xenos.h> <rex/graphics/registers.h>
    <rex/graphics/format/ucode.h> <rex/graphics/pipeline/shader/shader.h>)
# Never link rexcore/rexui OBJECT libraries: runtime already owns their globals.
target_link_libraries(aster_rexgpu_xenos PRIVATE
    rex::runtime rex::xxhash Vulkan::Headers GPUOpen::VulkanMemoryAllocator
    rex::SPIRV rex::glslang rex::MachineIndependent rex::GenericCodeGen
    rex::OSDependent rex::OGLCompiler Threads::Threads)
target_link_options(aster_rexgpu_xenos PRIVATE -Wl,--no-undefined)

add_custom_target(aster_session_closed
    COMMAND "${CMAKE_COMMAND}" "-DASTER_HUMAN_STATUS=${ASTER_HUMAN_STATUS}"
        -P "${CMAKE_CURRENT_LIST_DIR}/check_session.cmake"
    COMMENT "Checking that human session 027 has ended")
add_dependencies(aster_rexgpu_xenos aster_session_closed)
