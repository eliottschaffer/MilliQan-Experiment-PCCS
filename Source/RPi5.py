# LV Distribution Board Code
import random
import time
import spidev
import datetime
import json
from collections import Counter
import os
import csv
import gpiod

chip = gpiod.Chip('gpiochip4')

Pulse_En = chip.get_line(5)
Pulse_En.request(consumer="Pulse_En", type=gpiod.LINE_REQ_DIR_OUT)

Pulse_Send = chip.get_line(23)
Pulse_Send.request(consumer="Pulse_Send", type=gpiod.LINE_REQ_DIR_OUT)


Sys_Rst = chip.get_line(26)
Sys_Rst.request(consumer="Sys_Rst", type=gpiod.LINE_REQ_DIR_OUT)

OE = chip.get_line(17)
OE.request(consumer="OE", type=gpiod.LINE_REQ_DIR_OUT)




# The program works using 3 different objects, A run object which is created every time runs are requested,
# A detector object which handles the data flow to 4 Detector layer objects, each of which actually send the SPI data
# to their respective Pico Blade. A pulse is then created by turning on and off specific sets of GPIO pins. The creating
# of the data is inside the Run object which is parsed to the Detector objects which instructs the Layers to and does timing.


class DetectorLayer:
    def __init__(self, cs_id, detector_spi):
        self.data_array = bytearray()
        self.spi = detector_spi
        self.cs = cs_id

    def convert_pattern_to_bytes(self, pattern):

        pattern_bytes = bytearray()
        print(pattern)
        half_byte_list = [0, 0, 0, 0]
        counter = 0
        for row in pattern:
            half_byte = 0
            for i, boolean in enumerate(row):
                if boolean:
                    half_byte += 2 ** (3 - i)
            half_byte_list[counter] = half_byte
            counter += 1

        byte_2 = (half_byte_list[2] << 4) | half_byte_list[3]
        byte_1 = (half_byte_list[0] << 4) | half_byte_list[1]

        pattern_bytes.append(byte_1)
        pattern_bytes.append(byte_2)

        # Extend self.data_array with pattern_bytes
        self.data_array.extend(pattern_bytes)

    def convert_voltage_to_bytes(self, voltage):
        voltage_bytes = bytearray()

        for value in voltage:
            voltage_bytes.append(value & 0xFF)  # Low byte
            voltage_bytes.append((value >> 8) & 0xFF)  # High byte

        self.data_array.extend(voltage_bytes)

    def set_pattern(self, pattern, voltage):
        self.convert_pattern_to_bytes(pattern)
        self.convert_voltage_to_bytes(voltage)

    def layer_scan(self):

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50*1000
        self.spi.mode = 0


        # print(data)
        # for byte in data:
        #     self.spi.xfer3([byte])
        opcode_scan = bytearray()
        opcode_scan.extend([0xff, 0xfe])
        opcode_scan.extend([0x00 for _ in range(34)])
        self.display(opcode_scan)
        self.spi.xfer3(opcode_scan)
        self.spi.close()

    def send_data(self):
        # Enable SPI

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50*1000
        self.spi.mode = 0

        # print(data)
        # for byte in data:
        #     self.spi.xfer3([byte])
        opcode_data = bytearray()
        opcode_data.extend([0xff, 0xff])
        opcode_data.extend(self.data_array)
        self.display(opcode_data)
        self.spi.xfer3(opcode_data)
        self.spi.close()

    def display(self, arr):
        for i, byte_value in enumerate(arr):
            print(f'{byte_value:02X}', end=' ')
            if (i + 1) % 2 == 0:
                print(end='|')
            if (i + 1) % 8 == 0:
                print()

    def clear(self):
        self.data_array.clear()


def send_pulse():
    Sys_Rst.set_value(0)
    Sys_Rst.set_value(1)

    OE.set_value(0)
    Pulse_En.set_value(1)
    print("Pulse  Allowed")

    Pulse_Send.set_value(1)
    time.sleep(0.1)
    Pulse_Send.set_value(0)

    Pulse_En.set_value(0)
    OE.set_value(1)
    print("Pulse No longer allowed")


class Detector:
    def __init__(self, number_of_layers):
        self.spi = spidev.SpiDev()
        self.olayer = [DetectorLayer(_, self.spi) for _ in range(number_of_layers)]
        self.i2c_scan(number_of_layers)

    def i2c_scan(self, number_of_layer):
        for index in range(number_of_layer):
            self.olayer[index].layer_scan()

    def set_blade_pattern(self, layer_index, pattern, voltage):
        if layer_index < len(self.olayer):
            self.olayer[layer_index].set_pattern(pattern, voltage)

    def display(self):
        for index, blade in enumerate(self.olayer):
            print(f"Blade {index}:")
            blade.display()
            print()

    def send_data(self):
        for _ in range(len(self.olayer)):
            self.olayer[_].send_data()
        send_pulse()

    def clear(self):
        for _, blade in enumerate(self.olayer):
            blade.clear()


class Run:

    def __init__(self, trigger, randomize, run_list_raw):
        self.run_list = run_list_raw
        self.milliqan_trigger = bool(trigger)
        self.odetector = Detector(4)
        self.random = randomize
        self.run_type_list = ['mcp', 'rand', 'layer', 'layer0', 'layer1', 'layer2', 'layer3', 'layer4']
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


    def create_run(self):
        print("Entered Run")
        for i in range(len(self.run_list)):
            print((len(self.run_list)))
            emulation_type = self.run_list[i]
            if emulation_type in self.run_type_list:
                create_function = getattr(self, f"create_{emulation_type}", None)
                if create_function and callable(create_function):
                    create_start = time.time()
                    create_function()
                    create_end = time.time()
                    print("Create time: ", create_end - create_start)
                    # self.odetector.display()
                    send_start = time.time()
                    self.odetector.send_data()
                    send_end = time.time()
                    print("Send time: ", send_end - send_start)
                    clear_start = time.time()
                    self.odetector.clear()
                    clear_end = time.time()
                    print("Clear time: ", clear_end - clear_start)
                    time.sleep(0.1)


    def create_mcp(self):
        location = random.randrange(0, 16, 1)
        row = (location - 1) // 4
        column = (location - 1) % 4

        bit_map = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        bit_map[row][column] = 1
        volt_val = random.randrange(1000, 3000, 5)

        voltage = [volt_val for _ in range(0, 16)]

        drift = random.choice([0, 1])

        if drift == 1:
            drift_map = [[0] * 4 for _ in range(4)]

            row_change = random.choice([-1, 0, 1])
            column_change = random.choice([-1, 0, 1])

            if 0 <= row + row_change < 4 and 0 <= column + column_change < 4:
                drift_map[row + row_change][column + column_change] = 1

            for blade_index in range(4):
                self.odetector.set_blade_pattern(blade_index, (drift_map if blade_index == 3 else bit_map), voltage)
        else:
            for blade_index in range(4):
                self.odetector.set_blade_pattern(blade_index, bit_map, voltage)

    def create_rand(self):

        bit_map = [[[random.randint(0, 1) for _ in range(4)] for _ in range(4)] for _ in range(4)]

        voltages = [random.randrange(1000, 3000, 5) for _ in range(16)]

        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltages)


    # def load_run(self):
    def create_layer(self, layer_on=None):
        if layer_on is None:
            layer_on = random.randint(0, 4)

        bit_map = [[[0 for _ in range(4)] for _ in range(4)] for _ in range(4)]
        bit_map[layer_on] = [[1 for _ in range(4)] for _ in range(4)]
        print(bit_map)

        volt_val = random.randrange(1000, 3000, 5)

        voltage = [volt_val for _ in range(0, 16)]

        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltage)


    def create_layer0(self):
        self.create_layer(0)

    def create_layer1(self):
        self.create_layer(1)

    def create_layer2(self):
        self.create_layer(2)

    def create_layer3(self):
        self.create_layer(3)

    def create_layer4(self):
        self.create_layer(4)





if __name__ == '__main__':
    print("Starting Emulator Program Program. Type -h for help, else enter run type with quantity of run.\n")
    while True:
        user_in = input("\nInput: ")
        if user_in == "-h":
            print(
                "\nType of supported types are: \n'mcp', 'rand', and 'layer'\n\n'layer' has the ability to be called "
                "for a specific layer with layer0, layer1 ... with the defult being random layer\n\n"
                "To use type 'mcp 30' this will give 30 mcp run types.\n"
                "'rand 5 layer2 3' will give 5 random file and 3 layer2 runs.\n\n"
                "An optional marker -r can be added at the end and will randomize the order of the runs.\n"
                "A marker -t can be added to force the MilliQan detector to trigger.")
        else:
            user_input_parts = user_in.split()
            run_type = []
            randomize = 0
            trigger = 0
            for _ in range(len(user_input_parts)):
                if user_input_parts[_] in ['mcp', 'rand', 'layer', 'layer0', 'layer1', 'layer2', 'layer3']:
                    try:
                        number = int(user_input_parts[_ + 1])
                    except IndexError:
                        print("Please Specify Number After the Run Type")
                        break
                    except ValueError:
                        print("Please specify number of runs sequentially: type1 #1 type2 #2")
                        break
                    except Exception:
                        print("Unknown Error")

                    for j in range(number):
                        run_type.append(user_input_parts[_])

                if user_input_parts[_] == '-r':
                    randomize = 1

                if user_input_parts[_] == '-t':
                    trigger = 1

            if not run_type:
                # Handle other cases or provide an error message
                print("Invalid input. Please use '-h' for help.")
            else:
                print(randomize, trigger)
                print(run_type)
                oRun = Run(trigger, randomize, run_type)

                oRun.create_run()

