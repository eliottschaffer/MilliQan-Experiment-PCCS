# PCCS Board Code

#from rpi5 import Run

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


def log_timestamp(file_path="desync.log", event="Unknown Event"):
    """Logs the current timestamp and event description to a file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "a") as f:
        f.write(f"{timestamp} - {event}\n")

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


def send_fastpulse():
    Sys_Rst.set_value(0)
    Sys_Rst.set_value(1)

    OE.set_value(0)
    Pulse_En.set_value(1)
    print("Pulse  Allowed")

    Pulse_Send.set_value(1)
    time.sleep(1 / 300)  # 300Hz for DRS
    Pulse_Send.set_value(0)

    Pulse_En.set_value(0)
    OE.set_value(1)
    print("Pulse No longer allowed")


class DetectorLayer:
    def __init__(self, cs_id, detector_spi):
        self.data_array = bytearray()
        self.data_array2 = bytearray()  # New for slab, need 2 frames of data since we have 2*16 pot vals to account for

        # The "previous array" will be used to ensure data security and fix desync,
        # The picos will return the first so many values received, these will be compared to the ones here
        self.previous_array = ()
        self.pico_return = None

        self.spi = detector_spi
        self.cs = cs_id

    def setByteData(self, bool_data):

        # print(bool_data)

        pattern_bytes = bytearray()

        # print(pattern_bytes)

        if len(bool_data) == 32:
            slab_bool = []
            print("Slab run bool data raw", bool_data)
            for i in range(0, len(bool_data), 2):
                # Perform OR operation on each pair and append to the result
                slab_bool.append((1 if bool_data[i] | bool_data[i + 1] else 0))
            print("Slab run bool data appended: ", slab_bool)
            bool_data = slab_bool

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
        self.data_array2.extend(pattern_bytes)
        print(self.data_array)
        print(self.data_array2)

    def setVoltage(self, voltage):
        voltage_bytes = bytearray()

        for value in voltage:
            value = int(value)  # Convert value to integer
            voltage_bytes.append((value >> 8) & 0xFF)  # High byte
            voltage_bytes.append(value & 0xFF)  # Low byte

        print(f"Voltage bytes length: {len(voltage_bytes)}")
        print(f"Voltage bytes content: {voltage_bytes}")

        if len(voltage) == 32:
            self.data_array.extend(voltage_bytes[:32])  # First 32 bytes
            self.data_array2.extend(voltage_bytes[32:64])  # Next 32 bytes
        else:
            self.data_array.extend(voltage_bytes)

        print(self.data_array)
        print(self.data_array2)

    def set_data(self, chan_val):
        print("Chan Val in Set Data", chan_val)
        bool_data = [(val != '0' and val != '') for val in chan_val]  # lets pulse go to non zero channels
        print("Bool Data in Set Data", bool_data)
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
        self.pico_return = self.spi.xfer3(opcode_data)
        self.spi.close()

        self.verification(opcode_data)

        self.clear()

    def verification(self, new_previous):
        #print(self.pico_return)
        #print(self.previous_array)

        if(sum(self.pico_return) == 0):
            print("No Pico in this")
            self.previous_array = tuple(new_previous)
            return
        elif(self.pico_return[0:3] == [255,254,253,252] or self.previous_array == ()):
            print("initial loops")
            self.previous_array = tuple(new_previous)
            return
        elif(self.pico_return[0:3] == self.previous_array[0:3]):
            print("Verified Correct")
            self.previous_array = tuple(new_previous)
            return
        else:
            log_timestamp(event="Desync detected")
            print("Entering Desync Fixing")
            self.desync_protocol()


    def desync_protocol(self):
        ## When desynced the pico is recieving the opcode and data in the wrong order.

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50*1000
        self.spi.mode = 0

        desync_test = bytearray()
        desync_fix = bytearray()

        desync_test.extend([i for i in range(36)]) # An array 0-35 in bytes
        print(desync_test)
        time.sleep(0.5)
        print("Zeroth Test send", self.spi.xfer3(desync_test))
        time.sleep(0.5)
        test_return1 = self.spi.xfer3(desync_test)
        print(test_return1)
        print("CALCULATED DESYNC = ", test_return1[-1])

        time.sleep(0.5)
        #int(test_return1[-1])
        desync_fix.extend([i for i in range(test_return1[-1] + 1)])
        print(desync_fix)
        time.sleep(0.5)
        test_return2 = self.spi.xfer3(desync_fix)

        print(test_return2)
        time.sleep(0.5)
        revert_array = bytearray()
        revert_array.extend([255,255])
        revert_array.extend([0 for i in range(34)])
        test_return3 = self.spi.xfer3(revert_array)
        self.previous_array = tuple(revert_array)
        print(test_return3[-1])

        self.spi.close()

        print("Desync Hopefully fixed")
        log_timestamp(event="Hopefully fixed")
        print("prev_return = ", self.previous_array)




    def send_slab_data(self):

        # New code to send 2 frames to the Pico,
        # This is needed as 1 layer on the slab is 16*2 PMTs, need 2x the DAC data.

        # Enable SPI

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        # print(data)
        # for byte in data:
        #     self.spi.xfer3([byte])
        opcode_data1 = bytearray()
        opcode_data1.extend([0xff, 0xfc])
        opcode_data1.extend(self.data_array)
        self.pico_return = self.spi.xfer3(opcode_data1)
        self.verification(opcode_data1)

        time.sleep(0.5)

        opcode_data2 = bytearray()
        opcode_data2.extend([0xff, 0xfd])
        opcode_data2.extend(self.data_array2)
        self.pico_return = self.spi.xfer3(opcode_data2)
        self.verification(opcode_data2)

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
        self.pico_return = self.spi.xfer3(opcode_scan)
        self.verification(opcode_scan)
        self.spi.close()
        self.clear()

    def clear(self):
        self.data_array.clear()
        self.data_array2.clear()

class Detector:
    def __init__(self, number_of_layers):
        self.number_of_layers = number_of_layers
        self.spi = spidev.SpiDev()
        self.olayer = [DetectorLayer(_, self.spi) for _ in range(number_of_layers)]
        # self.i2c_scan()
        self.trigger = False

    def i2c_scan(self):
        for index in range(self.number_of_layers):
            self.olayer[index].layer_scan()

    def set_blade_data(self, chan_val):
        # Send increments of 16 channel values to each layer
        for i in range(self.number_of_layers):
            self.olayer[i].set_data(chan_val[i * 16:(i + 1) * 16])

    def set_slab_blade_data(self, chan_val):
        for i in range(self.number_of_layers):
            print("Chan ", i, "is getting data ", chan_val[i * 32:(i + 1) * 32])
            self.olayer[i].set_data(chan_val[i * 32:(i + 1) * 32])


    def send_data(self):
        # Tells the layer objects to send their data to the Picos
        for _ in range(len(self.olayer)):
            self.olayer[_].send_data()
        send_pulse()

    def send_slab_data(self):
        # Tells the layer objects to send their data to the Picos
        for _ in range(len(self.olayer)):
            self.olayer[_].send_slab_data()
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
        self.data = []
        self.odetector = Detector(4)

        with open(csv_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            # Skip the header row if needed
            next(reader)  # Uncomment this line if your CSV file has a header row
            # Iterate over each row in the CSV file
            for row in reader:
                # Append each row to the data list
                self.data.append(row)

    def start_csv_run(self):
        prev_data = 0
        prev_prev_data = 0
        for j in range(10):
            for k in range(25):
                for i in range(len(self.data)):
                    datai = self.data[i]
                    detecor_type = datai[0]
                    print(datai, detecor_type)

                    if prev_prev_data == datai:
                        send_fastpulse()
                        print("Fast Flash")
                    else:  # change "if True" to else to get fast flashes back
                        match detecor_type:
                            case 'bar':
                                self.bar_run(datai)
                            case 'slab':
                                self.slab_run(datai)
                        prev_prev_data = prev_data
                        prev_data = datai


    def bar_run(self, datai):
        print("Entered Bar Run")
        trigger = datai[3]
        pulse_length = datai[4]
        chan_val = datai[5:85]

        processed_chan_val = [
            '0' if val.strip() == '' or not val.strip().isdigit()
            else ('4000' if int(val) > 4000 else val.strip())
            for val in chan_val
        ]
        self.odetector.set_length(pulse_length)
        self.odetector.set_blade_data(processed_chan_val)
        self.odetector.set_trigger(trigger)
        self.odetector.send_data()
        time.sleep(0.4)

    def slab_run(self, datai):
        print("Entered Slab Run")
        trigger = datai[3]
        pulse_length = datai[4]
        chan_val = datai[5:165]

        processed_chan_val = [
            '0' if val.strip() == '' or not val.strip().isdigit()
            else ('4000' if int(val) > 4000 else val.strip())
            for val in chan_val
        ]
        print("Processed chan val", processed_chan_val)

        self.odetector.set_length(pulse_length)
        self.odetector.set_slab_blade_data(processed_chan_val)
        self.odetector.set_trigger(trigger)
        self.odetector.send_slab_data()
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

