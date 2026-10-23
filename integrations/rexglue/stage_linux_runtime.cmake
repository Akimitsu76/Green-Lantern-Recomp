# Original local integration. The v0.10.0 SDK helper stages the GPU plugin,
# but its Linux branch does not stage the runtime's shared dependencies.
function(aster_stage_rex_linux_runtime host_target)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        foreach(runtime_target IN ITEMS rex::runtime rex::TracyClient)
            if(NOT TARGET ${runtime_target})
                message(FATAL_ERROR "Missing ReXGlue dependency: ${runtime_target}")
            endif()
            add_custom_command(TARGET ${host_target} POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    "$<TARGET_FILE:${runtime_target}>"
                    "$<TARGET_FILE_DIR:${host_target}>"
                VERBATIM)
        endforeach()
    endif()
endfunction()
