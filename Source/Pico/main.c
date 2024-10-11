// // Copyright (c) 2021 Michael Stoops. All rights reserved.
// // Portions copyright (c) 2021 Raspberry Pi (Trading) Ltd.
// // 
// // Redistribution and use in source and binary forms, with or without modification, are permitted provided that the 
// // following conditions are met:
// //
// // 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
// //    disclaimer.
// // 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
// //    following disclaimer in the documentation and/or other materials provided with the distribution.
// // 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
// //    products derived from this software without specific prior written permission.
// // 
// // THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, 
// // INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE 
// // DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, 
// // SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
// // SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, 
// // WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE 
// // USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
// //
// // SPDX-License-Identifier: BSD-3-Clause
// //
// // Example of an SPI bus slave using the PL022 SPI interface

// #include <stdio.h>
// #include <string.h>
// #include "pico/stdlib.h"
// #include "pico/binary_info.h"
// #include "hardware/spi.h"
// #include "hardware/i2c.h"

// #define I2C_PORT i2c0
// #define BUF_LEN  0x24
// #define CENT_FAN 0x70
// #define AUX_FAN 0x71


// int8_t pins[] = {20, 21, 26, 27, 7, 6, 5, 4, 8, 9, 10, 12, 14, 15, 13, 11};



// int8_t address[16]; 

// bool reserved_addr(uint8_t addr) {
//     return (addr & 0x78) == 0 || (addr & 0x78) == 0x78;
// }

// void chooseChannel(uint8_t chan){
//     if (chan > 15) {
//         return;
//     }
//     // Reset the TCA9548A multiplexers
//     uint8_t reset_val = 0x00;
//     i2c_write_blocking(I2C_PORT, CENT_FAN, &reset_val, 1, false);
//     i2c_write_blocking(I2C_PORT, AUX_FAN, &reset_val, 1, false);

//     uint8_t multiplexer_address = (chan < 8) ? CENT_FAN : AUX_FAN;
//     uint8_t channel_select = 1 << (chan % 8);

//     // Debug print to show the channel selection
//     printf("Setting multiplexer address 0x%X to channel %d with channel select 0x%X\n", multiplexer_address, chan % 8, channel_select);

//     // Send control byte to multiplexer to select the channel
//     int ret = i2c_write_blocking(I2C_PORT, multiplexer_address, &channel_select, 1, false);
//     if (ret < 0) {
//         printf("Error selecting channel %d on multiplexer 0x%X\n", chan % 8, multiplexer_address);
//     } else {
//         printf("Channel %d selected on multiplexer 0x%X\n", chan % 8, multiplexer_address);
//     }
// }

// void i2cScan() {
//     printf("\nI2C Bus Scan\n");
//     printf("   0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F\n");

//     for (int addr = 0; addr < (1 << 7); ++addr) {
//         if (addr % 16 == 0) {
//             printf("%02x ", addr);
//         }

//         // Perform a 1-byte dummy read from the probe address. If a slave
//         // acknowledges this address, the function returns the number of bytes
//         // transferred. If the address byte is ignored, the function returns
//         // -1.

//         // Skip over any reserved addresses.
//         int ret;
//         uint8_t rxdata;
//         if (reserved_addr(addr)) {
//             ret = PICO_ERROR_GENERIC;
//         } else {
//             ret = i2c_read_blocking(I2C_PORT, addr, &rxdata, 1, false);
//         }

//         printf(ret < 0 ? "." : "@");
//         if (ret > -1) {
//             printf("Address 0x%02x found\n", addr);  // Adjusted output to show address and channel
//         }
//         printf(addr % 16 == 15 ? "\n" : "  ");
//     }
// }
    

// void printbuf(uint8_t buf[], size_t len){
//     int i;
//     for (i = 0; i < len; ++i) {
//         if (i % 16 == 15)
//             printf("%02x\n", buf[i]);
//         else
//             printf("%02x ", buf[i]);
//     }

//     // append trailing newline if there isn't one
//     if (i % 16) {
//         putchar('\n');
//     }
// }
    
// void i2c_start(void){
//         // Initialize I2C interface
//     i2c_init(I2C_PORT, 400 * 1000);  // Initialize I2C1 at 400 kHz
//     gpio_set_function(0, GPIO_FUNC_I2C); // Set SDA pin function
//     gpio_set_function(1, GPIO_FUNC_I2C); // Set SCL pin function
//     gpio_pull_up(0);
//     gpio_pull_up(1);
//     return;
// }

// void pins_init(void){
//     for (int j = 0; j < 16; j++){
//         gpio_init(pins[j]);
//         gpio_set_dir(pins[j], GPIO_OUT);
//     }
// }

// void set_pin(int pin, bool value){
//     gpio_put(pin, value);
// }

// void pinSetting(uint8_t buf[]){
//     // Extracting the first two bytes and combining them into a 16-bit integer
//     int16_t pinsetting = (buf[0] << 8) | buf[1];

//     // Creating a boolean array to store the bits of pinsetting
//     bool pin_logic[16];

//     // Extracting each bit of pinsetting and storing it in the pin_logic array
//     for (int i = 0; i < 16; i++) {
//         pin_logic[15 - i] = (pinsetting >> i) & 0x01;
//     }

//     for (int j = 0; j < 16; j++){
//         set_pin(pins[j], pin_logic[j]);
//     }
//     // To make sure it hasnt crashed
//     printf("Set pins correctly\n");
// }
    


// void voltageSetting(uint8_t buf[]) {
//     int16_t voltageSetting[16];
    
//     // Extract voltage values from the buffer
//     for (int i = 0; i < 16; i++) {
//         voltageSetting[i] = (buf[i * 2] << 8) | buf[i * 2 + 1];
//     }

//     for (int i = 0; i < 16; i++) {
//         // Determine the multiplexer address based on the index
      
//         // Ensure the voltage setting is within the range 0-4095 (12 bits)
//         int16_t data = voltageSetting[i] & 0x0FFF; // DAC accepts 12-bit data

//         chooseChannel(i);

//         i2cScan();

//         // Prepare data bytes for the DAC (assuming 12-bit data needs to be split into two bytes)
//         uint8_t dac_data[2] = { (uint8_t)(data >> 8), (uint8_t)(data & 0xFF) };

//         // Send data to DAC
//         i2c_write_blocking(I2C_PORT, 0x4D, dac_data, 2, false); // Assuming 0x4D is the DAC I2C address
//     }

//     // To make sure it hasn't crashed
//     printf("Set Voltage correctly\n");
// }

// void processInput(uint8_t* buf) {

//     switch (buf[0]) {
//         case 0xFF:
//             switch (buf[1]) {
//                 case 0xFF:
//                     pinSetting(&buf[2]);
//                     voltageSetting(&buf[2]);
//                     return;
//                 case 0xFE:
//                     i2cScan();
//                     return;
//                 default:
//                     break;
//             }
//             break;
//         default:
//             printf("DeSync");
//             break;
//     }
// }


// int main() {
//     // Enable UART so we can print
//     stdio_init_all();
// #if !defined(spi_default) || !defined(PICO_DEFAULT_SPI_SCK_PIN) || !defined(PICO_DEFAULT_SPI_TX_PIN) || !defined(PICO_DEFAULT_SPI_RX_PIN) || !defined(PICO_DEFAULT_SPI_CSN_PIN)
// #warning spi/spi_slave example requires a board with SPI pins
//     puts("Default SPI pins were not defined");
// #else

//     printf("SPI slave example\n");

//     // Enable SPI 0 at 1 MHz and connect to GPIOs
//     spi_init(spi_default, 50 *1000);
//     spi_set_slave(spi_default, true);
//     gpio_set_function(PICO_DEFAULT_SPI_RX_PIN, GPIO_FUNC_SPI);
//     gpio_set_function(PICO_DEFAULT_SPI_SCK_PIN, GPIO_FUNC_SPI);
//     gpio_set_function(PICO_DEFAULT_SPI_TX_PIN, GPIO_FUNC_SPI);
//     gpio_set_function(PICO_DEFAULT_SPI_CSN_PIN, GPIO_FUNC_SPI);
//     // Make the SPI pins available to picotool
//     bi_decl(bi_4pins_with_func(PICO_DEFAULT_SPI_RX_PIN, PICO_DEFAULT_SPI_TX_PIN, PICO_DEFAULT_SPI_SCK_PIN, PICO_DEFAULT_SPI_CSN_PIN, GPIO_FUNC_SPI));


//     spi_set_format(spi_default, 8, SPI_CPOL_1, SPI_CPHA_1, SPI_MSB_FIRST); 
//     i2c_start();
//     pins_init();

//     i2cScan();
//     sleep_ms(3000);
//     printf("Before scan");
//     i2cScan();
//     printf("After scan");
//     uint8_t out_buf[BUF_LEN], in_buf[BUF_LEN];

//     // Initialize output buffer
//     for (size_t i = 0; i < BUF_LEN; ++i) {
//         // bit-inverted from i. The values should be: {0xff, 0xfe, 0xfd...}
//         out_buf[i] = ~i;
//     }

//     printf("SPI slave says: When reading from MOSI, the following buffer will be written to MISO:\n");
//     printbuf(out_buf, BUF_LEN);
    
//     for (size_t i = 0; ; ++i) {
//         // Write the output buffer to MISO, and at the same time read from MOSI.
//         spi_write_read_blocking(spi_default, out_buf, in_buf, BUF_LEN);

//         // Write to stdio whatever came in on the MOSI line.
//         printf("SPI slave says: read page %d from the MOSI line:\n", i);
//         printbuf(in_buf, BUF_LEN);

//         processInput(in_buf);

//     }



// #endif
// }

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/binary_info.h"
#include "hardware/spi.h"
#include "hardware/i2c.h"

#define I2C_PORT i2c0
#define BUF_LEN  0x24
#define CENT_FAN 0x70
#define AUX_FAN 0x71
#define TEST 0x00

int8_t pins[] = {20, 21, 26, 27, 7, 6, 5, 4, 8, 9, 10, 12, 14, 15, 13, 11};
int8_t address[16]; 

int8_t desync[] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};

bool reserved_addr(uint8_t addr) {
    return (addr & 0x78) == 0 || (addr & 0x78) == 0x78;
}

void chooseChannel(uint8_t chan){
    if (chan > 15) {
        return;
    }
    // Reset the TCA9548A multiplexers
    uint8_t reset_val = 0x00;
    i2c_write_blocking(I2C_PORT, CENT_FAN, &reset_val, 1, false);
    i2c_write_blocking(I2C_PORT, AUX_FAN, &reset_val, 1, false);

    uint8_t multiplexer_address = (chan < 8) ? CENT_FAN : AUX_FAN;
    uint8_t channel_select = 1 << (chan % 8);

    // Debug print to show the channel selection
    printf("Setting multiplexer address 0x%X to channel %d with channel select 0x%X\n", multiplexer_address, chan % 8, channel_select);

    // Send control byte to multiplexer to select the channel
    int ret = i2c_write_blocking(I2C_PORT, multiplexer_address, &channel_select, 1, false);
    if (ret < 0) {
        printf("Error selecting channel %d on multiplexer 0x%X\n", chan % 8, multiplexer_address);
    } else {
        // printf("Channel %d selected on multiplexer 0x%X\n", chan % 8, multiplexer_address);
    }
}

void versionScan() {
    for(uint8_t i = 0; i < 16; i++) {
        chooseChannel(i);
        
        // Add a small delay to ensure the multiplexer has switched channels
        sleep_ms(5);

        uint8_t test_data = 0x00;

        int ret = i2c_write_blocking(I2C_PORT, 0x2F, &test_data, 1, false); // Testing Possible Results
        if (ret >= 0) {
            printf("V4 or below Found in Channel %u\n", i);
            address[i] = 0x2F;
        } else {
            printf(" V4 or below not found in Channel %u\n", i);
            address[i] = 0x2D;
        }
    }
}


void printbuf(uint8_t buf[], size_t len) {
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
    
void i2c_start(void) {
    // Initialize I2C interface
    i2c_init(I2C_PORT, 400 * 1000);  // Initialize I2C at 400 kHz
    gpio_set_function(0, GPIO_FUNC_I2C); // Set SDA pin function
    gpio_set_function(1, GPIO_FUNC_I2C); // Set SCL pin function
    gpio_pull_up(0);
    gpio_pull_up(1);
}

void pins_init(void) {
    for (int j = 0; j < 16; j++) {
        gpio_init(pins[j]);
        gpio_set_dir(pins[j], GPIO_OUT);
    }
}

void set_pin(int pin, bool value) {
    gpio_put(pin, value);
}

void pinSetting(uint8_t buf[]) {
    // Extracting the first two bytes and combining them into a 16-bit integer
    int16_t pinsetting = (buf[0] << 8) | buf[1];

    // Creating a boolean array to store the bits of pinsetting
    bool pin_logic[16];

    // Extracting each bit of pinsetting and storing it in the pin_logic array
    for (int i = 0; i < 16; i++) {
        pin_logic[15 - i] = (pinsetting >> i) & 0x01;
    }

    for (int j = 0; j < 16; j++) {
        set_pin(pins[j], pin_logic[j]);
    }
    // To make sure it hasn't crashed
    printf("Set pins correctly\n");
}

void voltageSetting(uint8_t buf[]) {
    int16_t voltageSetting[16];
    
    // Extract voltage values from the buffer
    for (int i = 0; i < 16; i++) {
        voltageSetting[i] = (buf[i * 2] << 8) | buf[i * 2 + 1];
    }

    for (int i = 0; i < 16; i++) {
        // Ensure the voltage setting is within the range 0-4095 (12 bits)
        uint16_t data = voltageSetting[i] & 0x0FFF; // DAC accepts 12-bit data
        if (data>0xfa0) {
             data = 0xfa0;
        }
        uint8_t trunc_data[1] = {abs((uint8_t)(data >> 5) - 128)}; // Pot on older version takes 7-bit data and is inverted wiper (0 is highest, 128 is lowest voltage)
        
        chooseChannel(i);

        // Prepare data bytes for the DAC (12-bit data needs to be split into two bytes)
        uint8_t dac_data[2] = { (uint8_t)(data >> 8), (uint8_t)(data & 0xFF) };

        // Send data to DAC/Pot
        switch (address[i]) {
            case 0x2D: {
                int ret = i2c_write_blocking(I2C_PORT, 0x4D, dac_data, 2, false); // Assuming 0x4D is the DAC I2C address
                if (ret < 0) {
                    ret = i2c_write_blocking(I2C_PORT, 0x4C, dac_data, 2, false);

                    if (ret < 0) {
                        printf("No base connected in channel %d\n", i);
                    } else {
                        printf("DAC at address 0x4C set to %u, %u\n", dac_data[0], dac_data[1]);
                    }
                } else {
                    printf("DAC at address 0x4D set to %u %u\n", dac_data[0], dac_data[1]);
                }
                break;
            }
        
            case 0x2F:
                i2c_write_blocking(I2C_PORT, 0x2F, trunc_data, 1, false);
                printf("Potentiometer at address 0x2F set to %d\n", trunc_data[0]);
                break;
        
            default:
                printf("No recognized address for channel %d\n", i);
                break;
        }
    }
    // To make sure it hasn't crashed
    printf("Set Voltage correctly\n");
}

void processInput(uint8_t* buf) {
    switch (buf[0]) {
        case 0xFF:
            switch (buf[1]) {
                case 0xFF:
                    pinSetting(&buf[2]);
                    voltageSetting(&buf[4]);
                    return;
                case 0xFE:
                    versionScan();
                    return;
                default:
                    break;
            }
            break;
        default:
            printf("DeSync");
            pinSetting(&desync[2]);
            voltageSetting(&desync[4]);
            break;
    }
}

int main() {
    // Enable UART so we can print
    stdio_init_all();

    printf("SPI slave example\n");

    // Enable SPI 0 at 1 MHz and connect to GPIOs
    spi_init(spi_default, 50 * 1000);
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

        processInput(in_buf);
    }
}