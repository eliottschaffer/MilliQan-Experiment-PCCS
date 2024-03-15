cmake_minimum_required(VERSION 3.13)

set(PROGRAM_NAME LV_Dist_Spi)
set(PICO_BOARD pico_w)

include(pico_sdk_import.cmake)

project(LV_Dist_Spi)

pico_sdk_init()


set(SOURCES
    main.c
)

add_executable(${PROJECT_NAME} ${SOURCES})

target_include_directories(${PROGRAM_NAME} PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(${PROGRAM_NAME}
    pico_stdlib
    pico_util
    hardware_spi
    hardware_i2c
)


pico_enable_stdio_usb(${PROGRAM_NAME} TRUE)
pico_enable_stdio_uart(${PROGRAM_NAME} FALSE)

pico_add_extra_outputs(${PROGRAM_NAME})