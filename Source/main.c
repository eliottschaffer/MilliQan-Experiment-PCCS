// Copyright (c) 2021 Michael Stoops. All rights reserved.
// Portions copyright (c) 2021 Raspberry Pi (Trading) Ltd.
// 
// Redistribution and use in source and binary forms, with or without modification, are permitted provided that the 
// following conditions are met:
//
// 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
//    disclaimer.
// 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
//    following disclaimer in the documentation and/or other materials provided with the distribution.
// 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
//    products derived from this software without specific prior written permission.
// 
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, 
// INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE 
// DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, 
// SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
// SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, 
// WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE 
// USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
//
// SPDX-License-Identifier: BSD-3-Clause
//
// Example of an SPI bus slave using the PL022 SPI interface

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/binary_info.h"
#include "hardware/spi.h"
#include "hardware/i2c.h"

#define I2C_PORT i2c0
#define BUF_LEN  0x22
#define CENT_FAN 0x70
#define AUX_FAN 0x71


int8_t pins[] = {20, 21, 26, 27, 7, 6, 5, 4, 8, 9, 10, 12, 14, 15, 13, 11};

void printbuf(uint8_t buf[], size_t len){
    int i;
    for (i = 0; i < len; ++i) {
        if (i % 16 == 15)
            printf("%02x\n", buf[i]);
        else
            printf("%02x ", buf[i]);
    }

    // append trailing newline if there isn't one
    if (i % 16) {
        putchar('\n');
    }
}
    
void i2c_start(void){
        // Initialize I2C interface
    i2c_init(I2C_PORT, 400 * 1000);  // Initialize I2C1 at 400 kHz
    gpio_set_function(0, GPIO_FUNC_I2C); // Set SDA pin function
    gpio_set_function(1, GPIO_FUNC_I2C); // Set SCL pin function
    gpio_pull_up(0);
    gpio_pull_up(1);
    return;
}

void pins_init(void){
    for (int j = 0; j < 16; j++){
        gpio_init(pins[j]);
        gpio_set_dir(pins[j], GPIO_OUT);
    }
}

void set_pin(int pin, bool value){
    gpio_put(pin, value);
}

void pinSetting(uint8_t buf[]){
    // Extracting the first two bytes and combining them into a 16-bit integer
    int16_t pinsetting = (buf[0] << 8) | buf[1];

    // Creating a boolean array to store the bits of pinsetting
    bool pin_logic[16];

    // Extracting each bit of pinsetting and storing it in the pin_logic array
    for (int i = 0; i < 16; i++) {
        pin_logic[15 - i] = (pinsetting >> i) & 0x01;
    }

    for (int j = 0; j < 16; j++){
        set_pin(pins[j], pin_logic[j]);
    }

    printf("Set pins correctly\n");
}
    

void voltageSetting(uint8_t buf[]) {
    int16_t voltageSetting[16];
    
    // Extract voltage values from the buffer
    for (int i = 0; i < 16; i++) {
        voltageSetting[i] = (buf[i * 2] << 8) | buf[i * 2 + 1];
    }

    for (int i = 0; i < 16; i++) {
        // Determine the multiplexer address based on the index
        uint8_t multiplexer_address = (i < 8) ? CENT_FAN : AUX_FAN;

        // Determine the channel number based on the index
        uint8_t channel = (i < 8) ? i : (i - 8);

        // Ensure the voltage setting is within the range 0-4095
        int16_t data = voltageSetting[i] & 0x0FFF; // Assuming DAC accepts 12-bit data
        
        // Send control byte to multiplexer
        i2c_write_blocking(I2C_PORT, multiplexer_address, channel & 0x01, sizeof(channel), false);
        
        // Send data to DAC
        i2c_write_blocking(I2C_PORT, 77, &data, sizeof(data), false);
    }
    printf("Set Voltage correctly\n");
}


int main() {
    // Enable UART so we can print
    stdio_init_all();
#if !defined(spi_default) || !defined(PICO_DEFAULT_SPI_SCK_PIN) || !defined(PICO_DEFAULT_SPI_TX_PIN) || !defined(PICO_DEFAULT_SPI_RX_PIN) || !defined(PICO_DEFAULT_SPI_CSN_PIN)
#warning spi/spi_slave example requires a board with SPI pins
    puts("Default SPI pins were not defined");
#else

    printf("SPI slave example\n");

    // Enable SPI 0 at 1 MHz and connect to GPIOs
    spi_init(spi_default, 500 * 1000);
    spi_set_slave(spi_default, true);
    gpio_set_function(PICO_DEFAULT_SPI_RX_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_SCK_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_TX_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_CSN_PIN, GPIO_FUNC_SPI);
    // Make the SPI pins available to picotool
    bi_decl(bi_4pins_with_func(PICO_DEFAULT_SPI_RX_PIN, PICO_DEFAULT_SPI_TX_PIN, PICO_DEFAULT_SPI_SCK_PIN, PICO_DEFAULT_SPI_CSN_PIN, GPIO_FUNC_SPI));


    spi_set_format(spi_default, 8, SPI_CPOL_1, SPI_CPHA_1, SPI_MSB_FIRST); 
    i2c_start();
    pins_init();

    uint8_t out_buf[BUF_LEN], in_buf[BUF_LEN];

    // Initialize output buffer
    for (size_t i = 0; i < BUF_LEN; ++i) {
        // bit-inverted from i. The values should be: {0xff, 0xfe, 0xfd...}
        out_buf[i] = ~i;
    }

    printf("SPI slave says: When reading from MOSI, the following buffer will be written to MISO:\n");
    printbuf(out_buf, BUF_LEN);
    
    for (size_t i = 0; ; ++i) {
        // Write the output buffer to MISO, and at the same time read from MOSI.
        spi_write_read_blocking(spi_default, out_buf, in_buf, BUF_LEN);

        // Write to stdio whatever came in on the MOSI line.
        printf("SPI slave says: read page %d from the MOSI line:\n", i);
        printbuf(in_buf, BUF_LEN);
        pinSetting(in_buf);
        voltageSetting(in_buf);

    }



#endif
}