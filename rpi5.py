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

Pulse_En = chip.get_line(14)
Pulse_En.request(consumer="Pulse_En", type=gpiod.LINE_REQ_DIR_OUT)

Pulse_Send = chip.get_line(23)
Pulse_Send.request(consumer="Pulse_Send", type=gpiod.LINE_REQ_DIR_OUT)


Sys_Rst = chip.get_line(26)
Sys_Rst.request(consumer="Sys_Rst", type=gpiod.LINE_REQ_DIR_OUT)

OE = chip.get_line(15)
OE.request(consumer="OE", type=gpiod.LINE_REQ_DIR_OUT)


Trigger_Send = chip.get_line(24)
Trigger_Send.request(consumer="Trigger_Send", type=gpiod.LINE_REQ_DIR_OUT)

# The program works using 3 different objects, A run object which is created every time runs are requested,
# A detector object which handles the data flow to 5 Detector layer objects, each of which actually send the SPI data
# to their respective Pico Blade. A pulse is then created by turning on and off specific sets of GPIO pins. The creating
# of the data is inside the Run object which is parsed to the Detector objects which instructs the Layers to and does timing.

def log_timestamp(file_path="desync.log", event="Unknown Event"):
    """Logs the current timestamp and event description to a file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "a") as f:
        f.write(f"{timestamp} - {event}\n")
class DetectorLayer:
    def __init__(self, cs_id, detector_spi):
        self.data_array = bytearray()
        self.spi = detector_spi
        self.cs = cs_id
        self.previous_array = ()
        self.pico_return = None

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
            voltage_bytes.append((value >> 8) & 0xFF)  # High byte
            voltage_bytes.append(value & 0xFF)  # Low byte


        self.data_array.extend(voltage_bytes)

    def set_pattern(self, pattern, voltage):
        self.convert_pattern_to_bytes(pattern)
        self.convert_voltage_to_bytes(voltage)

    def layer_scan(self):
        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        opcode_scan = bytearray()
        opcode_scan.extend([0xff, 0xfe])
        opcode_scan.extend([0x00 for _ in range(34)])

        print("layer scan return")
        self.pico_return = self.spi.xfer3(opcode_scan)
        print(self.pico_return)

        self.verification(opcode_scan)
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

        self.pico_return = self.spi.xfer3(opcode_data)
        print("PICO RETURN WAS:   ", self.pico_return)
        print("Expected RETURN WAS:   ", self.previous_array)
        self.spi.close()
        self.verification(opcode_data)


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



    def display(self, arr):
        for i, byte_value in enumerate(arr):
            print(f'{byte_value:02X}', end=' ')
            if (i + 1) % 2 == 0:
                print(end='|')
            if (i + 1) % 8 == 0:
                print()

    def clear(self):
        self.data_array.clear()


def send_pulse(pulse):
    Sys_Rst.set_value(0)
    Sys_Rst.set_value(1)

    OE.set_value(0)

    if pulse == 1:
        Pulse_En.set_value(1)
        print("Pulse  Allowed")

        Trigger_Send.set_value(1)
        Pulse_Send.set_value(1)
        time.sleep(.1)

    Trigger_Send.set_value(0)
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

    def send_data(self, pulse):
        for _ in range(len(self.olayer)):
            self.olayer[_].send_data()
        send_pulse(pulse)

    def clear(self):
        for _, blade in enumerate(self.olayer):
            blade.clear()


class Run:

    def __init__(self, trigger, randomize, run_list_raw, pulse):
        self.run_list = run_list_raw
        self.odetector = Detector(4)
        time.sleep(5)
        self.random = randomize
        self.run_type_list = ['mcp', 'rand', 'layer', 'layer0', 'layer1', 'layer2', 'layer3', 'layer4', 'chan', 'zero', 'desync', 'custom']
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.pulse = pulse
        self.counter = 0


    def create_run(self):
        print("Entered Run")
        for i in range(len(self.run_list)):
            #print((len(self.run_list)))
            emulation_type = self.run_list[i]
            if emulation_type in self.run_type_list:
                create_function = getattr(self, f"create_{emulation_type}", None)
                if create_function and callable(create_function):
                    time.sleep(.3)


                    create_start = time.time()
                    create_function()

                    create_end = time.time()
                    #print("Create time: ", create_end - create_start)
                    # self.odetector.display()
                    send_start = time.time()

                    self.odetector.send_data(self.pulse)

                    send_end = time.time()
                    #print("Send time: ", send_end - send_start)
                    clear_start = time.time()

                    self.odetector.clear()



                    clear_end = time.time()
                    #print("Clear time: ", clear_end - clear_start)

                    if self.counter % 10000 == 0:
                        log_timestamp(event=f"Event Number {self.counter}")  # Logs every 10,000 events
                    self.counter = self.counter + 1

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

        voltages = [random.randrange(4000, 4005, 5) for _ in range(16)]

        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltages)

    def create_zero(self):

        bit_map = [[[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]] for _ in range(4)]

        voltages = [0 for _ in range(16)]

        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltages)

    def create_desync(self):

        bit_map = [[[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]] for _ in range(4)]
        desync_amount = random.randrange(0, 15, 1)
        voltages = [0 for _ in range(0, desync_amount)]
        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltages)


    def create_layer(self, layer_on=None):
        if layer_on is None:
            layer_on = random.randint(0, 4)

        bit_map = [[[0 for _ in range(4)] for _ in range(4)] for _ in range(4)]
        bit_map[layer_on] = [[1 for _ in range(4)] for _ in range(4)]
        #print(bit_map)

        volt_val = random.randrange(500, 505, 5)

        voltage = [volt_val for _ in range(0, 16)]

        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltage)

    def create_chan(self):
        chan = 3
        layer = (chan) // 16
        row = ((chan) % 16) // 4
        column = (chan) % 4

        bit_map = [[[0 for _ in range(4)] for _ in range(4)] for _ in range(4)]
        bit_map[layer][row][column] = 1

        volt_val = random.randrange(2000, 2005, 5)

        voltage = [volt_val for _ in range(0, 16)]

        for blade_index, _ in enumerate(range(4)):
            self.odetector.set_blade_pattern(blade_index, bit_map[_], voltage)

    def create_custom(self):

        # 2 Bar like testing
        bit_map = [[[1, 1, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]] for _ in range(4)]

        voltage = [0 for _ in range(0, 16)]
        voltage[0] = 2800
        voltage[1] = 2875
        voltage[3] = 300

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
                "\nType of supported types are: \n'mcp', 'rand', and 'layer' 'chan', 'zero'\n\n'layer' has the ability"
                "to be called "
                "for a specific layer with layer0, layer1 ... with the defult being random layer\n\n"
                "To use type 'mcp 30' this will give 30 mcp run types.\n"
                "'rand 5 layer2 3' will give 5 random file and 3 layer2 runs.\n\n"
                "chan is for a hardcoded channel and zero is to initialize the system"
                "An optional marker -r can be added at the end and will randomize the order of the runs.\n"
                "A marker -t can be added to force the MilliQan detector to trigger.")
        else:
            user_input_parts = user_in.split()
            run_type = []
            randomize = 0
            trigger = 0
            for _ in range(len(user_input_parts)):
                if user_input_parts[_] in ['mcp', 'rand', 'layer', 'layer0', 'layer1', 'layer2', 'layer3', 'chan', 'zero', 'desync', 'custom']:
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
                oRun = Run(trigger, randomize, run_type, 1)
                log_timestamp(event="Staring Run")

                oRun.create_run()

