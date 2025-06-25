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

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/binary_info.h"
#include "hardware/spi.h"
#include "hardware/i2c.h"
#include "hardware/watchdog.h"
#include "hardware/structs/watchdog.h"

#define I2C_PORT i2c0
#define BUF_LEN  0x24
#define CENT_FAN 0x70
#define AUX_FAN 0x71
#define TEST 0x00

int8_t pins[] = {20, 21, 26, 27, 7, 6, 5, 4, 8, 9, 10, 12, 14, 15, 13, 11};
int8_t address[16][2]; 
int8_t device_count[16] = {0};

int8_t desync[] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};

int8_t desync_flag = 0;

bool bad_chan[16][2]; 


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

        uint8_t potential_addresses[] = {0x2F, 0x4D, 0x4C};

        // Reset device count for this channel
        device_count[i] = 0;

        uint8_t test_data = 0x00;

        // Check each potential address
        for (uint8_t j = 0; j < sizeof(potential_addresses); j++) {
            int ret = i2c_write_blocking(I2C_PORT, potential_addresses[j], &test_data, 1, false);
            if (ret >= 0) {
                printf("Device with address 0x%X found in Channel %u\n", potential_addresses[j], i);

                // Store the address if there's space in the array
                if (device_count[i] < 2) {
                    address[i][device_count[i]] = potential_addresses[j];
                    device_count[i]++;
                } else {
                    printf("Warning: Too many devices on Channel %u, some may not be recorded.\n", i);
                }
            }
        }

        // If no devices found, leave address list empty for this channel
        if (device_count[i] == 0) {
            printf("No devices found in Channel %u\n", i);
        }
    
    }

    printf("\nSummary of detected devices:\n");
    for (uint8_t i = 0; i < 16; i++) {
        printf("Channel %u: ", i);
        if (device_count[i] == 0) {
            printf("No devices\n");
        } else {
            for (uint8_t j = 0; j < 2; j++) {
                printf("0x%X ", address[i][j]);
            }
            printf("\n");
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
        uint8_t trunc_data[1] = {abs((uint8_t)(data >> 5) - 128)}; 
        // Pot on older version takes 7-bit data and is inverted wiper (0 is highest, 128 is lowest voltage)
        
        chooseChannel(i);

        // Prepare data bytes for the DAC (12-bit data needs to be split into two bytes)
        uint8_t dac_data[2] = { (uint8_t)(data >> 8), (uint8_t)(data & 0xFF) };
        
        int ret; //where we will verify if I2C write is successful

        // Send data to DAC/Pot
        switch (address[i][0]) {
            case 0x4D:
                ret = i2c_write_blocking(I2C_PORT, 0x4D, dac_data, 2, false); // Assuming 0x4D is the DAC I2C address
                
                if (ret > 0){
                    printf("DAC at address 0x4d set to %u, %u\n", dac_data[0], dac_data[1]);
                } else{
                    printf("Failed to write voltage");
                }

                break;

            case 0x4C:
                ret = i2c_write_blocking(I2C_PORT, 0x4C, dac_data, 2, false);
                
                if (ret > 0){
                    printf("DAC at address 0x4C set to %u, %u\n", dac_data[0], dac_data[1]);
                }else{
                    printf("Failed to write voltage");
                }

                break;
        
            case 0x2F:
                ret = i2c_write_blocking(I2C_PORT, 0x2F, trunc_data, 1, false);
                
                if (ret > 0){
                    printf("Potentiometer at address 0x2F set to %d\n", trunc_data[0]);
                }else{
                    printf("Failed to write voltage");
                }
                
                break;
        
            default:
                printf("No recognized address for channel %d\n", i);
                break;
        }
    }
    // To make sure it hasn't crashed
    printf("Set Voltage correctly\n");
}

void slab_voltageSetting(uint8_t buf[], int slab_frame_ID) {

    int16_t voltageSetting[16];
        
    // Extract voltage values from the buffer
    for (int i = 0; i < 16; i++) {
        voltageSetting[i] = (buf[i * 2] << 8) | buf[i * 2 + 1];
    }
    
    for (int i = 0; i < 8; i++) { // Loop over the 8 channels
        chooseChannel(i + slab_frame_ID * 8);
        
        for(int j = 0; j<2; j++){ //Loop over the potential two bases per channel

            uint16_t data = voltageSetting[2*i + j] & 0x0FFF; // DAC accepts 12-bit data
            if (data>0xfa0) {
                data = 0xfa0;
            }
            uint8_t trunc_data[1] = {abs((uint8_t)(data >> 5) - 128)}; // Pot on older version takes 7-bit data and is inverted wiper (0 is highest, 128 is lowest voltage)
            
            

            // Prepare data bytes for the DAC (12-bit data needs to be split into two bytes)
            uint8_t dac_data[2] = { (uint8_t)(data >> 8), (uint8_t)(data & 0xFF) };

            int ret; //where we will verify if I2C write is successful

            switch (address[i*2 + 8*slab_frame_ID][j]) {
                case 0x4D:
                    ret = i2c_write_blocking(I2C_PORT, 0x4D, dac_data, 2, false); // Assuming 0x4D is the DAC I2C address
                    
                    if (ret > 0){
                        printf("DAC at address 0x4d set to %u, %u\n", dac_data[0], dac_data[1]);
                    } else{
                        printf("Failed to write voltage");
                    }

                    break;

                case 0x4C:
                    ret = i2c_write_blocking(I2C_PORT, 0x4C, dac_data, 2, false);
                    
                    if (ret > 0){
                        printf("DAC at address 0x4C set to %u, %u\n", dac_data[0], dac_data[1]);
                    }else{
                        printf("Failed to write voltage");
                    }

                    break;
            
                case 0x2F:
                    ret = i2c_write_blocking(I2C_PORT, 0x2F, trunc_data, 1, false);
                    
                    if (ret > 0){
                        printf("Potentiometer at address 0x2F set to %d\n", trunc_data[0]);
                    }else{
                        printf("Failed to write voltage");
                    }
                    
                    break;
            
                default:
                    printf("No recognized address for channel %d\n", i);
                    break;
            }
        }
    }

}


void lightbar_config(uint8_t slab_frame_ID){
    uint8_t Setting[2] = { 0x03, 0x00 }; // [Config Address, Data]

    uint8_t dac_data[2] = { 0x00, 0x00 };
    uint8_t mux_data[2] = { 0x01, 0xff}; // [All LED off in last cell]

    for (int i = 0; i < 8; i++) { // Loop over the 8 channels

        for(int j = 0; j<2; j++){ //Loop over the two bases per channel
            
            printf("Choosing Channel: %d\n", i + slab_frame_ID * 8);
            printf("Expected Address: %d\n", address[i + slab_frame_ID * 8][j]);

            chooseChannel(i + slab_frame_ID * 8);
            int ret; //where we will verify if I2C write is successful

            switch (address[i + slab_frame_ID * 8][j]) {
                case 0x4C:
                    ret = i2c_write_blocking(I2C_PORT, 0x20, Setting, 2, false);
                    sleep_ms(5);
                    i2c_write_blocking(I2C_PORT, 0x20, mux_data, 2, false);
                    sleep_ms(5);
                    i2c_write_blocking(I2C_PORT, 0x4C, dac_data, 2, false);
                    if (ret > 0){
                        printf("MUX %02x Configured\n", 0x20);
                    } else {
                        printf("Failed to configure MUX %02x\n", 0x20);
                    }
                    break;
                case 0x4D:
                    ret = i2c_write_blocking(I2C_PORT, 0x21, Setting, 2, false);
                    sleep_ms(5);
                    i2c_write_blocking(I2C_PORT, 0x21, mux_data, 2, false);
                    sleep_ms(5);
                    i2c_write_blocking(I2C_PORT, 0x4D, dac_data, 2, false);
                    if (ret > 0){
                        printf("MUX %02x Configured\n", 0x21);
                    } else {
                        printf("Failed to configure MUX %02x\n", 0x21);
                    }
                    break;
            
                default:
                    printf("No recognized address for channel %d\n", i);
                    break;
            }
        }
    }

}



void lightbar(uint8_t buf[], int slab_frame_ID){

    // To use the same format as previously, we have the lighbar config (0xff) binarily anded to it's Voltages 0xFF00
    // We get our value for the voltage in the first byte and LED info in second as opposed to voltage in two bytes.
    // This means we need to scale the 0-4095 to 0-255 with a factor of 16

    // Assuming Two sig values are LED, Two LSB are DAQ

    int16_t voltageSetting[16];
    uint8_t ledSetting[16];

    for (int i = 0; i < 16; i++) {
        ledSetting[i] = buf[i*2+1];
        voltageSetting[i] = buf[i*2] * 16;
    }

    for (int i = 0; i < 8; i++) { // Loop over the 8 channels
        
        chooseChannel(i + slab_frame_ID * 8);
        printf("Choosing Channel: %d\n", i + slab_frame_ID * 8);
        
        for(int j = 0; j<2; j++){ //Loop over the two bases per channel

            //Prep DAQ Data and then MUX data for correct format/registers

            uint16_t data = voltageSetting[2*i + j] & 0x0FFF; // DAC accepts 12-bit data
            if (data>0xff1) {
                data = 0xfa0;
                printf("DAC voltage was too high");
            }


            printf("Mux Byte is %02x\n", ledSetting[2*i+j]);


            uint8_t dac_data[2] = { (uint8_t)(data >> 8), (uint8_t)(data & 0xFF) };
            uint8_t mux_data[2] = { 0x01, ledSetting[2*i+j]};


 
            int ret_1; //where we will verify if DAC write is successful
            int ret_2; //where we will verify if MUX write is successful

            printf("Expected Address: %d\n", address[i + slab_frame_ID * 8][j]);

            switch (address[i + slab_frame_ID * 8][j]) {
                case 0x4C:
                    ret_1 = i2c_write_blocking(I2C_PORT, 0x20, mux_data, 2, false);
                    sleep_ms(5);
                    ret_2 = i2c_write_blocking(I2C_PORT, 0x4C, dac_data, 2, false);

                    if (ret_1 > 0){
                        printf("MUX %02x Setting Set \n", 0x20);
                    } else {
                        printf("Failed to Put Setting MUX %02x\n", 0x20);
                    }

                    if (ret_2 > 0){
                        printf("DAQ %02x Voltage Written to %02x  %02x\n", 0x4C, dac_data[0], dac_data[1]);
                    } else {
                        printf("Failed to wrote voltage to DAC %02x\n", 0x4C);
                    }
                    break;
                    
                case 0x4D:
                    ret_1 = i2c_write_blocking(I2C_PORT, 0x21, mux_data, 2, false);
                    sleep_ms(5);
                    ret_2 = i2c_write_blocking(I2C_PORT, 0x4D, dac_data, 2, false);
                    
                    if (ret_1 > 0){
                        printf("MUX %02x Setting Set\n", 0x21);
                    } else {
                        printf("Failed to Put Setting MUX %02x\n", 0x21);
                    }

                    if (ret_2 > 0){
                        printf("DAQ %02x Voltage Written to %02x  %02x\n", 0x4D, dac_data[0], dac_data[1]);
                    } else {
                        printf("Failed to wrote voltage to DAC %02x\n", 0x4D);
                    }
                    break;
            
                default:
                    printf("No recognized address for channel %d\n", i);
                    break;
            }
        }
    }

    // for (int i = 0; i < 16; i++) {
    //     printf("MUX Setting %02x\n", ledSetting[i]);
    //     printf("Lightbar voltage %02x\n", voltageSetting[i]);
    // }
    
}





void processInput(uint8_t* buf, uint8_t* outbuf) {

    // Update the Output buffer for
    for (int i = 0; i < 4; i++) {
        outbuf[i] = buf[i];
    }

    for (int i = 5; i < 32; i++) {
        outbuf[i] = 0;
    }

    for (int i = 32; i <= 36; i++) {
        outbuf[i] = buf[i];
    }


    switch (buf[0]) {
        case 0xFF:
            switch (buf[1]) {
                case 0xFF:
                    pinSetting(&buf[2]);
                    voltageSetting(&buf[4]);
                    return;
                case 0xFE:
                    versionScan();
                    lightbar_config(0);
                    lightbar_config(1);
                    return;
                case 0XFC:
                    pinSetting(&buf[2]);
                    slab_voltageSetting(&buf[4], 0);
                    return;
                case 0XFD:
                    slab_voltageSetting(&buf[4], 1);
                    return;

                case 0XFB:
                    //check_bases();
                    lightbar(&buf[4], 1);
                    return;
                case 0xFA:
                    //Lightbar
                    lightbar(&buf[4], 0);
                    return;
                    
                default:
                    break;
            }

            break;
        default:
            printf("DeSync");
            pinSetting(&desync[2]);
            voltageSetting(&desync[4]);
            desync_flag = 4;
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
    for (size_t i = 0; i < BUF_LEN; i++) {
        // bit-inverted from i. The values should be: {0xff, 0xfe, 0xfd...}
        out_buf[i] = ~i;
    }

    printf("SPI slave says: When reading from MOSI, the following buffer will be written to MISO:\n");
    printbuf(out_buf, BUF_LEN);
    
    for (size_t i = 0; ; ++i){
        // Write the output buffer to MISO, and at the same time read from MOSI.
        spi_write_read_blocking(spi_default, out_buf, in_buf, BUF_LEN);

        // Write to stdio whatever came in on the MOSI line.
        printf("Pico read page %d from the MOSI line:\n", i);
        printbuf(in_buf, BUF_LEN);

        if (desync_flag == 0){
            processInput(in_buf, out_buf);
        }else{
            for (int i = 0; i < 4; i++) {
                out_buf[i] = in_buf[i];
            }
            for (int i = 32; i <= 36; i++) {
                out_buf[i] = in_buf[i];
            }
            desync_flag = desync_flag -1;
        }

    }
}
