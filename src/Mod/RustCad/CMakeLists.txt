# SPDX-License-Identifier: LGPL-2.1-or-later

set(RustCad_Crate "${CMAKE_SOURCE_DIR}/rust/geometry-kernel")
find_program(RUSTCAD_RUSTUP_EXECUTABLE rustup HINTS "$ENV{HOME}/.cargo/bin")
if(NOT RUSTCAD_RUSTUP_EXECUTABLE OR NOT EXISTS "${RUSTCAD_RUSTUP_EXECUTABLE}")
    message(FATAL_ERROR "BUILD_RUSTCAD requires Rustup and the installed rust/geometry-kernel/rust-toolchain.toml toolchain")
endif()
file(STRINGS "${RustCad_Crate}/rust-toolchain.toml" RustCad_Toolchain REGEX "^channel = ")
string(REGEX REPLACE "^channel = \"([^\"]+)\"$" "\\1" RustCad_Toolchain "${RustCad_Toolchain}")
set(RustCad_Cargo "${RUSTCAD_RUSTUP_EXECUTABLE}" run "${RustCad_Toolchain}" cargo)
# `rustup run` without --install refuses missing toolchains instead of changing the host.
execute_process(
    COMMAND ${RustCad_Cargo} --version
    RESULT_VARIABLE RustCad_CargoStatus
    OUTPUT_VARIABLE RustCad_CargoVersion
    ERROR_VARIABLE RustCad_CargoError
)
if(NOT RustCad_CargoStatus EQUAL 0)
    message(FATAL_ERROR "BUILD_RUSTCAD requires installed Rust ${RustCad_Toolchain}: ${RustCad_CargoError}")
endif()
string(STRIP "${RustCad_CargoVersion}" RustCad_CargoVersion)
message(STATUS "RustCad: ${RustCad_CargoVersion}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${RustCad_Crate}/rust-toolchain.toml")

set(RustCad_Mod "${CMAKE_BINARY_DIR}/Mod/RustCad")
set(RustCad_CargoDir "${CMAKE_CURRENT_BINARY_DIR}/cargo")
set(RustCad_Engine "${RustCad_Mod}/rustcad-engine${CMAKE_EXECUTABLE_SUFFIX}")
file(GLOB_RECURSE RustCad_EngineSources CONFIGURE_DEPENDS "${RustCad_Crate}/src/*.rs")
add_custom_command(
    OUTPUT "${RustCad_Engine}"
    COMMAND ${RustCad_Cargo} build --locked --release --jobs 1
        --manifest-path "${RustCad_Crate}/Cargo.toml" --bin rustcad-engine
        --target-dir "${RustCad_CargoDir}"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${RustCad_Mod}"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "${RustCad_CargoDir}/release/rustcad-engine${CMAKE_EXECUTABLE_SUFFIX}" "${RustCad_Engine}"
    DEPENDS
        "${RustCad_Crate}/Cargo.toml"
        "${RustCad_Crate}/Cargo.lock"
        "${RustCad_Crate}/rust-toolchain.toml"
        ${RustCad_EngineSources}
    WORKING_DIRECTORY "${RustCad_Crate}"
    VERBATIM
    COMMENT "Building the locked RustCad geometry engine"
)
add_custom_target(RustCadEngine ALL DEPENDS "${RustCad_Engine}")

set(RustCad_Scripts Init.py)
set(RustCad_Package rustcad/__init__.py rustcad/engine.py rustcad/feature.py)
if(BUILD_GUI)
    list(APPEND RustCad_Scripts InitGui.py TestRustCadGui.py)
    list(APPEND RustCad_Package rustcad/view.py rustcad/commands.py)
endif()
add_custom_target(RustCadScripts ALL SOURCES ${RustCad_Scripts} ${RustCad_Package})
fc_copy_sources(RustCadScripts "${RustCad_Mod}" ${RustCad_Scripts} ${RustCad_Package})
install(FILES ${RustCad_Scripts} DESTINATION Mod/RustCad)
install(FILES ${RustCad_Package} DESTINATION Mod/RustCad/rustcad)
install(PROGRAMS "${RustCad_Engine}" DESTINATION Mod/RustCad)
