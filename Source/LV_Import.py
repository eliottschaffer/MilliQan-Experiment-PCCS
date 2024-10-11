# PCCS Board Code

import time
import spidev
import datetime
import csv
import sys
import gpiod
import smbus
import logging

chip = gpiod.Chip('gpiochip4')

Pulse_En = chip.get_line(14)
Pulse_En.request(consumer="Pulse_En", type=gpiod.LINE_REQ_DIR_OUT)

Pulse_Send = chip.get_line(23)
Pulse_Send.request(consumer="Pulse_Send", type=gpiod.LINE_REQ_DIR_OUT)

Sys_Rst = chip.get_line(26)
Sys_Rst.request(consumer="Sys_Rst", type=gpiod.LINE_REQ_DIR_OUT)

OE = chip.get_line(15)
OE.request(consumer="OE", type=gpiod.LINE_REQ_DIR_OUT)

bus = smbus.SMBus(1)
pot_addr = 0x2c


# The program works using 3 different objects, A run object which is created every time runs are requested,
# A detector object which handles the data flow to 5 Detector layer objects, each of which actually send the SPI data
# to their respective Pico Blade. A pulse is then created by turning on and off specific sets of GPIO pins. The data is
# imported from the CSV file that the program is run with.


def send_pulse():
    Sys_Rst.set_value(0)
    Sys_Rst.set_value(1)

    OE.set_value(0)
    Pulse_En.set_value(1)
    print("Pulse  Allowed")

    Pulse_Send.set_value(1)
    time.sleep(.1)
    Pulse_Send.set_value(0)

    Pulse_En.set_value(0)
    OE.set_value(1)
    print("Pulse No longer allowed")


class DetectorLayer:
    def __init__(self, cs_id, detector_spi):
        self.data_array = bytearray()
        self.spi = detector_spi
        self.cs = cs_id

    def setByteData(self, bool_data):

        print(bool_data)

        pattern_bytes = bytearray()

        print(pattern_bytes)
        # Construct the first byte
        byte1 = 0
        for i in range(8):
            if bool_data[i]:
                byte1 |= (1 << (7 - i))  # Set the bit at position (7 - i) if the boolean value is True

        # Construct the second byte
        byte2 = 0
        for i in range(8, 16):
            if bool_data[i]:
                byte2 |= (1 << (15 - i))  # Set the bit at position (15 - i) if the boolean value is True

        print(byte1)
        print(byte2)
        pattern_bytes.append(byte1)
        pattern_bytes.append(byte2)

        self.data_array.extend(pattern_bytes)
        print(self.data_array)

    def setVoltage(self, voltage):
        voltage_bytes = bytearray()

        for value in voltage:
            value = int(value)  # Convert value to integer
            voltage_bytes.append((value >> 8) & 0xFF)  # High byte
            voltage_bytes.append(value & 0xFF)  # Low byte

        self.data_array.extend(voltage_bytes)

    def set_data(self, chan_val):

        bool_data = [(val != '0' and val != '') for val in chan_val]  # lets pulse go to non zero channels
        voltage_data = chan_val
        self.setByteData(bool_data)
        self.setVoltage(voltage_data)

    def send_data(self):
        # Enable SPI

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        # print(data)
        # for byte in data:
        #     self.spi.xfer3([byte])
        opcode_data = bytearray()
        opcode_data.extend([0xff, 0xff])
        opcode_data.extend(self.data_array)
        self.spi.xfer3(opcode_data)
        self.spi.close()
        self.clear()

    def layer_scan(self):

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        # print(data)
        # for byte in data:
        #     self.spi.xfer3([byte])
        opcode_scan = bytearray()
        opcode_scan.extend([0xff, 0xfe])
        opcode_scan.extend([0x00 for _ in range(34)])
        # self.display(opcode_scan)
        self.spi.xfer3(opcode_scan)
        self.spi.close()
        self.clear()

    def clear(self):
        self.data_array.clear()


class Detector:
    def __init__(self, number_of_layers):
        self.number_of_layers = number_of_layers
        self.spi = spidev.SpiDev()
        self.olayer = [DetectorLayer(_, self.spi) for _ in range(number_of_layers)]
        # self.i2c_scan()
        self.trigger = False
        self.detector_type = "bar"

    def i2c_scan(self):
        for index in range(self.number_of_layers):
            self.olayer[index].layer_scan()

    def set_blade_data(self, chan_val):
        # Send increments of 16 channel values to each layer
        for i in range(self.number_of_layers):
            self.olayer[i].set_data(chan_val[i * 16:(i + 1) * 16])

    def send_data(self):
        # Tells the layer objects to send their data to the Picos
        for _ in range(len(self.olayer)):
            self.olayer[_].send_data()
        send_pulse()

    def set_trigger(self, trigger_bool):
        # Change the triggering logic for MilliQan detector
        self.trigger = trigger_bool

    def set_length(self, length):
        # Validate that length is a digit and within the range 100-1100
        if not length.isdigit() or int(length) < 100 or int(length) > 1100:
            length = 500

        # Convert the 100-1100 ns range to 7-207 corresponding i2c hex range, 0x07 - 0xcf
        i2c_bit = round((int(length) - 100) / 5) + 7

        # Send the I2C command
        bus.write_i2c_block_data(pot_addr, 0x00, [i2c_bit])


class Import_csv:
    def __init__(self, csv_file):
        self.odetector = Detector(4)
        self.data = []

        with open(csv_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            # Skip the header row if needed
            next(reader)  # Uncomment this line if your CSV file has a header row
            # Iterate over each row in the CSV file
            for row in reader:
                # Append each row to the data list
                self.data.append(row)

    def start_csv_run(self):
        for i in range(len(self.data)):
            datai = self.data[i]
            print(datai)
            detector = datai[0]
            trigger = datai[3]
            pulse_length = datai[4]
            chan_val = datai[5:85]
            processed_chan_val = ['0' if val.strip() == '' or not val.strip().isdigit() else ('4000' if int(val) > 4000 else val.strip()) for val in chan_val]

            self.odetector.set_length(pulse_length)
            self.odetector.set_blade_data(processed_chan_val)
            self.odetector.set_trigger(trigger)
            self.odetector.send_data()
            time.sleep(0.4)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python LV_Import.py <file_path>\n")
        print(
            "For the usage and system information please refer to Github Repo: MilliQan-Experiment-LV-Dist-Calibration (will need to search within github)")
        sys.exit(1)
    else:
        Import = Import_csv(sys.argv[1])
        Import.start_csv_run()
        print("Import Run finished successfully")
