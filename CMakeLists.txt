cmake_minimum_required(VERSION 3.20)
project(AsterNativeHostProbe LANGUAGES CXX)
# This target is an original host test utility, not the Green Lantern port.
add_executable(aster-host-probe scripts/host_probe.cpp)
target_compile_features(aster-host-probe PRIVATE cxx_std_17)
find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
enable_testing()
add_test(NAME framework COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -v)
set_tests_properties(framework PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
