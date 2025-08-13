# PCCS Sender - This Program is designed for the MilliQan Slab detector Utilization of the PCCS. In the slab schema,
# there are 4 PCCS crates, one for each layer, which need to all work together. Specifically this program is the
# "Main" Code which is run by the Main PCCS and this is where the CSV file is imported.

# The Multi-PCCS System relies on the use of MQTT. Specifically, the Raspberry Pi that is running this code, is
# hardcoded as the MQTT Broker.

# MQTT is a Publish/Subscribe Messaging Protocol that allows for multiple streams of information to be seperated in
# different channels called TOPICs. Here the TOPICs are HANDSHAKE, DATA (and other similar), ERROR, STATUS.
# This code can then subscribe and publish on these topics to get information to the other RPis.

# For example, the Sender publishes the data on the DATA TOPIC which is read off by the Sub PCCS and is subscribed
# and waits for a ready response before sending a flash.


# For the handling of the data from the CSV to the Picos an OOP approach is used.
# The program works using 3 different objects, A run object which is created every time runs are requested,
# A detector object which handles the data flow to Detector layer objects, each of which actually send the SPI data
# to their respective Pico Blade. A pulse is then created by turning on and off specific sets of GPIO pins. The data is
# imported from the CSV file that the program is run with.


# from rpi5 import Run
import paho.mqtt.client as mqtt
import struct
import json
import threading
import time
import spidev
import datetime
import csv
import sys
import gpiod
import smbus
import logging

broker_ip = "192.168.110.110"  # Replace with Pi's IP (Or where ever the MQTT Broker is initialized), see GitHub readme

# MQTT Topics
TOPIC_HANDSHAKE = "pccs/handshake"
TOPIC_DATA = "pccs/data"
TOPIC_LIGHTBAR_DATA = "pccs/lightbar/data"

# The /+ flag allows for all the PCCS_Sub_#
TOPIC_STATUS = "pccs/status/+"
TOPIC_ERROR = "pccs/error/+"

# Defining of the GPIO Pins that are used throughout

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

# Defining of the bus and address for the length control Potentiometer.
bus = smbus.SMBus(1)
pot_addr = 0x2c


# Logging of Desync, TODO update this to include more information.
def log_timestamp(file_path="desync.log", event="Unknown Event"):
    """Logs the current timestamp and event description to a file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "a") as f:
        f.write(f"{timestamp} - {event}\n")


def send_pulse(trigger):
    # The sequence to start a Pulse:
    # Sys_Rst is a hardware reset on many ICs all tied together, good practice to reset each time.
    # OE* is an enable pin for a buffer in the pulse sequence, it is put low to allow the pulse to pass
    # Pulse Enable is the 3rd signal in the 3 input AND Switch,without it no pulse (this pin can be grounded via switch)
    # Trigger_Send is the optional triggering of the MilliDAQ - Function
    # Pulse_Send is the signal that starts the one-shots, creating the pulse

    Sys_Rst.set_value(0)
    Sys_Rst.set_value(1)

    OE.set_value(0)
    Pulse_En.set_value(1)
    print("Pulse  Allowed")
    Trigger_Send.set_value(trigger)
    Pulse_Send.set_value(1)

    time.sleep(.1)

    Trigger_Send.set_value(0)
    Pulse_Send.set_value(0)
    Pulse_En.set_value(0)
    OE.set_value(1)
    print("Pulse No longer allowed")


def send_fastpulse(trigger):
    # Same as the regular pulse with a different time.sleep, can become a function
    Sys_Rst.set_value(0)
    Sys_Rst.set_value(1)

    OE.set_value(0)
    Pulse_En.set_value(1)
    print("Pulse  Allowed")

    Trigger_Send.set_value(trigger)
    Pulse_Send.set_value(1)
    time.sleep(1 / 300)  # 300Hz for DRS

    Trigger_Send.set_value(0)
    Pulse_Send.set_value(0)

    Pulse_En.set_value(0)
    OE.set_value(1)
    print("Pulse No longer allowed")


def set_length(length):
    # Set the length of the LED pulse.

    # First validate that length is a digit and within the range 100-1100
    if not length.isdigit() or int(length) < 100 or int(length) > 1100:
        # if it is not a number, too big or too small make it 500
        length = 500

    # Convert the 100-1100 ns range to 7-207 corresponding i2c hex range, 0x07 - 0xcf
    # This is the tested "Good" region of the potentiometer working with the oneshot
    i2c_bit = round((int(length) - 100) / 5) + 7

    # The potentiometer uses I2C, a communication protocol that is only used for a little in this program
    # but used extensively in the Picos. Hardware have hardwired address which we can write data into registers.
    # in this case, the register is 0x00 and the data we write to is the resistance which controls the one-shot RC and
    # therefore the pulse-length
    bus.write_i2c_block_data(pot_addr, 0x00, [i2c_bit])


# We now enter the objects used in the system
# They are listed in a top-down design as which is consistent with their logic
# The first one is the Import_csv object, which take the CSV file which contains the flashing info
# and turns it into individual flashing events, the instructions of which are passed to the detector.

class Import_csv:

    # Import_csv Init, the object is initialized with the csv file that is desired and the number of times that the
    # csv file should be repeated - allows for smaller files to be used

    # Aditionally a repeat column could be added to each flashing event in the csv file to allow more compression.

    def __init__(self, csv_file, repeat_times=1):
        # Data array that will store the csv file
        self.data = []
        # The Import_csv object itself initializes a Detector object
        # The detector object was coded around the bar detector, with a number of "bar layers" (16 channels) as a param
        # For the case of the Slab detector, we only need 24 channels (each of which have 2 PMTs on them) so we
        # call a 2 layer Detector.
        self.odetector = Detector(2)
        self.repeat = repeat_times
        self.good_events = 0

        # Opening the CSV file and emptying each row into the self.data array
        with open(csv_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            # Skip the header row
            next(reader)
            # Iterate over each row in the CSV file
            for row in reader:
                # Append each row to the data list
                self.data.append(row)

    # This function is utilized to sort the data into ones that "necessarily" need the data to be transmitted
    # throughout the system and which ones we can just flash the same settings again. We also use the code in
    # the first column of the csv to categorize the data as regular slab data or as lightbar data (other PCCS use-case).

    # Again utilizing a times repeat in the csv file will allow us to simplify this
    def start_csv_run(self):
        # repeat the number specified in the object init
        for repeat_times in range(0, self.repeat):
            # loop through every row (flashing event)
            for flashing_event in range(len(self.data)):
                datai = self.data[flashing_event]

                # detector/use-case mentioned above
                detecor_type = datai[0]

                # Debug
                # print(datai, detecor_type)

                # If the info in for example 1000 flashing events are the same, this makes it so only 6 times is
                # data actually moved to the pico and then bases. for tthe rest we just fire the LED pulse. Also ensure
                # that previous event transfer from to the sub PCCS was successful.
                if flashing_event > 6 and self.data[flashing_event - 5] == datai and self.good_events == 1:
                    send_fastpulse()
                    print("Fast Flash")
                # If not, give the data to the respective use-case
                elif detecor_type == 'lightbar':
                    print("Slow_Flash")
                    self.lightbar_run(datai)
                # This is the one we are interested in, the slab_run function is the next step of the data pipeline.
                elif detecor_type == 'slab':
                    self.slab_run(datai)
                else:
                    print("Wrong detector type format given")
                    exit()
            time.sleep(0.5)

    # Process the data in the csv for the different detector functions
    def slab_run(self, datai):
        time.sleep(1)
        print("Entered Slab Run")

        # If we trigger MilliDAQ or not
        trigger = int(datai[3])
        # Length of LED Pulse ~ 100-1100 ns
        pulse_length = datai[4]
        set_length(pulse_length)
        # The data for each of the 192 channels (PMT Leds) in the Slab detector
        chan_val = datai[5:197]

        # Clean up the CSV, limit the voltage to be 4000 DAC counts (voltage setter).
        processed_chan_val = [
            '0' if val.strip() == '' or not val.strip().isdigit()
            else ('4000' if int(val) > 4000 else val.strip())
            for val in chan_val
        ]

        # Split the Data for the whole detector into 4 parts for each slab layer. The zeros are needed here because
        # the detector objects expects data in 32 value amounts - corresponding to the maximum channels on a single
        # blade pair.
        data_segments_main = processed_chan_val[0:48] + ['0'] * 16
        data_sub = [int(x) for x in processed_chan_val[48:192]]
        data_slices = [data_sub[i * 48:(i + 1) * 48] for i in range(3)]

        # Pass the main data segment to the detector object's function
        # Then actually send the data to the picos and the detector's bases
        self.odetector.set_slab_blade_data(data_segments_main)
        self.odetector.send_slab_data()

        # Debug
        # print("data_main", data_segments_main)
        # print("data_sub", data_sub)

        # Ready_lock is a blocking method for the set ready_for_flash. It is used to keep track of when all hand-shook
        # devices have successfully sent their data to the picos and received good responses.
        with ready_lock:
            ready_for_flash.clear()

        for i, slice_ in enumerate(data_slices):
            # For each Sub PCCS, format the Data it needs into the MQTT req struct
            # Publish the data to the topic below, with /{device_id}
            packed = struct.pack(">48H", *slice_)
            device_id = f"PCCS_Sub_{i + 1}"
            client.publish(f"pccs/data/{device_id}", packed)

        # After sending all the instructions, we wait for the Sub PCCS to respond ready, if within 10 seconds
        # not every PCCS has responded, we will not send the pulse and instead skip the pulse, moving to the
        # next flashing event
        if wait_for_all_ready(set(workers_ready), timeout=10):
            print("All subs ready — firing pulse")
            send_pulse(trigger)
            self.good_events = 1
            time.sleep(0.50)
        else:
            print("Timeout waiting for all subs — skipping this pulse")
            self.good_events = 0
            time.sleep(0.50)

    def lightbar_run(self, datai):
        # Will not be described here, a similar idea expect now the previous voltage values are now 2 bytes which
        # we used the first to denote the location/LED on in the lightbar and the second as a voltage
        print("Entered Lightbar Run")
        trigger = datai[3]
        pulse_length = datai[4]
        chan_val = datai[5:197]

        processed_chan_val = [
            '0' if val.strip() == '' or not val.strip().isdigit()
            else ('65535' if int(val) > 65535 else val.strip())
            for val in chan_val
        ]

        data_segments_main = processed_chan_val[0:48] + ['0'] * 16
        data_sub = [int(x) for x in processed_chan_val[48:192]]

        # print("data_main", data_segments_main)
        # print("data_sub", data_sub)
        packed_data = struct.pack(">144H", *data_sub)

        client.publish("pccs/lightbar/data", packed_data)

        set_length(pulse_length)

        self.odetector.set_slab_blade_data(data_segments_main)

        self.odetector.send_lightbar_data()
        send_pulse(trigger)

        time.sleep(0.50)


# The next object is the Detector Object, which is the intermediary between the Import_csv and the detector layers
# It can really be though as a wrapper of the third object, DetecorLayer, which has alot of specifics coded into it.
# It is mainly used to handle the SPI object, which is connected to the SPI Bus and is only one.
# SPI, Serial Peripheral Interface, is the communication protocol that is used for the Raspberry Pi's to communicate to
# the Picos. Only one SPI communication can happen at a time as it utilizes a shared 4 wire setup


class Detector:
    # The Detector object is initialized with the number of layers. In the Multi-PCCS Setup, each PCCS considers
    # the slab layer that is connected to as the "Detector" object with the first 8 slabs being "DetectorLayer 1" object
    # and the last 4 being "DetectorLayer 2" object.

    def __init__(self, number_of_layers):
        # Transfer the called number of layers into a variable able to be used in the functions
        self.number_of_layers = number_of_layers

        # Open the SPI object, this object is used for every communication
        self.spi = spidev.SpiDev()

        # Create an array of the DetectorLayer Objects to be used in loops.
        # We assign the SPI object to each DetectorLayer where the communication happens.
        self.olayer = [DetectorLayer(_, self.spi) for _ in range(number_of_layers)]

        # TODO Figure out if this fixes having to run rpi5.py
        #  self.i2c_scan()

    # As described above, the functions in the Detector object are mostly just looping over the DetectorLayers
    # and splitting the function input into 4, I will instead focus on describing the way the functions work in the
    # DetectorLayer Object

    # Scans the I2C devices in each DetectorLayer Object
    def i2c_scan(self):
        for index in range(self.number_of_layers):
            self.olayer[index].layer_scan()

    # Sends the flashing_trial data for formatting into Pico acceptable arrays for each DetectorLayer Object
    # Each "DetectorLayer" Object Controls one blade pair, which is 16 channels, slab = 32 PMTs.
    def set_slab_blade_data(self, chan_val):
        for i in range(self.number_of_layers):
            self.olayer[i].set_data(chan_val[i * 32:(i + 1) * 32])

    # Sends the formatted arrays of data from each DetectorLayer Object to its respective Pico via SPI
    def send_slab_data(self):
        for _ in range(len(self.olayer)):
            self.olayer[_].send_slab_data()

    # Same idea but for lightbar use-case
    def send_lightbar_data(self):
        for _ in range(len(self.olayer)):
            self.olayer[_].send_lightbar_data()


# The DetectorLayer object is the lowest level object this code.
# It formats all the data into frames (Described Below) and sends them to the Picos.

# Thr SPI Frame Protocol.   Inspired by Websocket Protocol

# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                          Opcode Header                        |     Byte 0, 1
# |                    0xFF           0xF_   _ is variable        |     Examples are 0xFF - bar run. 0xFE I2C scan ...
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |              Bool Pattern byte 1 (Channels 0–7)               |
# |      1 bit per channel: MSB = ch0, LSB = ch7 (bit-packed)     |
# |                                                               |  Byte 2 , 3
# |              Bool Pattern byte 2 (Channels 8–15)              |  Controls where the pulse is permitted to go
# |      1 bit per channel: MSB = ch8, LSB = ch15 (bit-packed)    |  using a controllable  8 chan buffer
# |                                                               |  One is located on each the central and auxiliary
# |        Example first 4 channels on, Ch 10 on, else off        |  Blade
# |        [1 1 1 1] [0 0 0 0] | [0 0 1 0] [0 0 0 0 0]            |
# |            F        0             2         0                 |
# |            |f|0|                   |2|0|                      |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                   Voltage Data: Channels 0–15                 |
# |      Each channel = 2 bytes: High byte then Low byte          | Byte 4 - 35 (Voltage information 2 bytes each)
# |      Total = 16 channels × 2 = 32 bytes                       | This contains a variable amount of channels
# |      Example voltage 4000 = 0xfa0 = |0|f| |a|0|               | More on this below
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+


# Currently Implemented Opcode Options (the 0xF_ byte):
# 0xFF - Bar Detector Frame
# 0xFE - Calls for the Pico to scan available I2C devices on each channel Voltage values ignored
# 0xFC - Slab Detector Frame First Half - Central Blade - with upto 2 PMTs/LEDs per channel
# 0xFD - Slab Detector Frame Second Half - Auxiliary Blade - upto 2 devices in each chan
# 0xFB - Lightbar First half
# 0xFA - Lightbar Second Half
# TODO 0xF0 - Force Pico Restart


class DetectorLayer:
    # The detector Layer class is initialized with an ID and the SPI object created by the detector object.
    def __init__(self, cs_id, detector_spi):
        # Two data arrays, which will be filled with the SPI frame bytes are created.
        # We create two serperate arrays to allow for the two frame setup needed for the Slab detector's 2 bases per ch
        self.data_array = bytearray()
        self.data_array2 = bytearray()

        # The "previous array" will be used to ensure data security and fix desync,
        # The picos will return the first and last four values received in the last frame stored in Pico Return
        self.previous_array = ()
        self.pico_return = None

        # Taking object parameters to variables to use
        self.spi = detector_spi
        self.cs = cs_id

    def set_data(self, chan_val):
        # One of the Main Functions used by the Detector Object,
        # It creates the boolean mask of the data calls the functions that create the SPI frame (other than opcode)

        print("Chan Val in Set Data", chan_val)
        bool_data = [(val != '0' and val != '') for val in chan_val]  # lets pulse go to non zero channels
        print("Bool Data in Set Data", bool_data)
        voltage_data = chan_val
        # These functions are described below
        self.setByteData(bool_data)
        self.setVoltage(voltage_data)

    def setByteData(self, bool_data):

        # This function creates the pattern bytes, (Bytes 2,3) in the SPI frame
        # We do this by first turning the voltage data in a bool map, 1 for if voltage is non-zero, else 0
        # we then perform bitwise operations until the outcome is what is described in the frame

        # Debug
        # print(bool_data)

        # Local bytearray for storing the final values to append to the data arrays
        pattern_bytes = bytearray()

        # for the slab detector, we have up to 32 voltages to assign with only 16 channels
        # We must then first do an OR operation on each 2 pairs of bool data
        # That is, if one of the LEDs is going to be flashed but not the other we must still allow the pulse to go to
        # that channel. For regular bar frame there are only 16 voltage values.
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

        # Debug
        # print(byte1)
        # print(byte2)

        # Append the bytes to the local array and then extend the data arrays by this local array.

        pattern_bytes.append(byte1)
        pattern_bytes.append(byte2)
        self.data_array.extend(pattern_bytes)
        self.data_array2.extend(pattern_bytes)


        # Debug
        # print(self.data_array)
        # print(self.data_array2)

    def setVoltage(self, voltage):

        # This Code formats the voltages values, which are capped at 4000 into the two byte format described before
        # Create a local array which we then extend into the data arrays
        voltage_bytes = bytearray()

        for value in voltage:
            value = int(value)  # Convert value to integer
            voltage_bytes.append((value >> 8) & 0xFF)  # High byte (move the value by 8 bits and mask into 0xFF)
            voltage_bytes.append(value & 0xFF)  # Low byte

        # Debug
        # print(f"Voltage bytes length: {len(voltage_bytes)}")
        # print(f"Voltage bytes content: {voltage_bytes}")

        # If slab data append to both arrays, if bar only to the first
        if len(voltage) == 32:
            self.data_array.extend(voltage_bytes[:32])  # First 32 bytes
            self.data_array2.extend(voltage_bytes[32:64])  # Next 32 bytes
        else:
            self.data_array.extend(voltage_bytes)

        # Debug
        # print(self.data_array)
        # print(self.data_array2)

    def send_slab_data(self):

        # Sends 2 frames to the Pico, one for each blade in the blade pair
        # This is needed as 1 layer on the slab is 12*2 PMTs, need two 16 PMT frames.
        # A single Frame only supports 16 PMTs/Voltages.

        # Open the SPI Bus, initialize at a slow speed
        # mode = 0 is for clock phase, don't change

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        # Debug
        # print(data)

        # Create the SPI Frame, Opcode Data, extend by the Opcode and by the finalized data array which
        # has the pattern bytes and the voltage bytes.

        opcode_data1 = bytearray()
        opcode_data1.extend([0xff, 0xfc])
        opcode_data1.extend(self.data_array)

        # Transfer the data to the spi using xfer3
        # Since SPI is a two-way communication, for every byte that is sent, a byte is received
        # We write this return into the pico return variable which we then process verify is working correctly with the
        # verification function
        self.pico_return = self.spi.xfer3(opcode_data1)
        self.verification(opcode_data1)

        # Give time for the Pico to perform the voltage settings on each base
        time.sleep(0.5)

        # Repeat with the second half of the data
        opcode_data2 = bytearray()
        opcode_data2.extend([0xff, 0xfd])
        opcode_data2.extend(self.data_array2)
        self.pico_return = self.spi.xfer3(opcode_data2)
        self.verification(opcode_data2)

        # Close the SPI Bus, clear the two data arrays for the next flashing event.
        self.spi.close()
        self.clear()

    def verification(self, new_previous):

        # This function does some checks on the Pico's returned data
        # It and also can detect if a pico is actually connected and if it is desynced.
        # TODO Extract new error Pico Codes and Base infomation from the remaining pico return values
        #  Use these in the MQTT Server

        # Debug
        # print(self.pico_return)
        # print(self.previous_array)

        if (sum(self.pico_return) == 0):
            # If the return is all zeros, either the Pico is dead or there is none connected
            print("No Pico in this")
            self.previous_array = tuple(new_previous)
            return
        elif (self.pico_return[4] == [255] or self.previous_array == ()):
            # The defult value on startup from the Pico, tells us something is connected
            print("initial loops")
            self.previous_array = tuple(new_previous)
            return
        elif (self.pico_return[0:3] == self.previous_array[0:3]):
            # For the second flashing onwards, the pico return's first 4 bytes should match up with the previous
            # frames first 4 values
            print("Verified Correct")
            # update the previous array with the new array provided to the function
            self.previous_array = tuple(new_previous)
            return
        else:
            # If none of the conditions are met, that is we get random values, we enter the desync mode
            # Currently we do a pretty complex process to fix the desync
            # TODO Figure our if just having the Pico restart is a better solution
            log_timestamp(event="Desync detected")
            print("Entering Desync Fixing")
            self.desync_protocol()

    def desync_protocol(self):
        # When desynced the pico is recieving the opcode and data in the wrong order.
        # That is instead of the Pico's rolling buffer starting with the 0xff 0xf_ it starts with some other bytes
        # Typically the offset returns to some fixed value in the voltage bytes

        # Currently to fix, the desync, we send an array 0-35 two times to get some information from the
        # Pico return as to what the desync ofset is.
        # We then send a complementary short array which should reallign the buffer
        # Finally we send a 0xFF followed by all 0x00s twice to check the pico return and ensure that it is alligned.

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        desync_test = bytearray()
        desync_fix = bytearray()

        desync_test.extend([i for i in range(36)])  # An array 0-35 in bytes
        print(desync_test)
        time.sleep(0.5)
        print("Zeroth Test send", self.spi.xfer3(desync_test))
        time.sleep(0.5)
        test_return1 = self.spi.xfer3(desync_test)
        print(test_return1)
        print("CALCULATED DESYNC = ", test_return1[-1])

        time.sleep(0.5)
        # int(test_return1[-1])
        desync_fix.extend([i for i in range(test_return1[-1] + 1)])
        print(desync_fix)
        time.sleep(0.5)
        test_return2 = self.spi.xfer3(desync_fix)

        print(test_return2)
        time.sleep(0.5)
        revert_array = bytearray()
        revert_array.extend([255, 255])
        revert_array.extend([0 for i in range(34)])
        test_return3 = self.spi.xfer3(revert_array)
        self.previous_array = tuple(revert_array)
        print(test_return3[-1])

        self.spi.close()

        print("Desync Hopefully fixed")
        log_timestamp(event="Hopefully fixed")
        print("prev_return = ", self.previous_array)

    def layer_scan(self):
        # This function just sends the opcode to perform the device scan followed by a bunch of zeros
        # The Pico does the scan by attempting to communicate dummy data to the known I2C addresses.
        # If the I2C returns non-zero, we successfully found something, if not then we conclude that there is no device
        # The Pico scans the addresses for the V4,V5 and V6 bases, with the V5 and V6 having 2 addresses

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
        # Clears the two data arrays
        self.data_array.clear()
        self.data_array2.clear()

    def send_data(self):
        # The command to send the data for Bar like data (similar logic to the slab)

        # Enable SPI
        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0
        opcode_data = bytearray()
        opcode_data.extend([0xff, 0xff])  # Bar detector Opcode
        opcode_data.extend(self.data_array)
        self.pico_return = self.spi.xfer3(opcode_data)
        self.spi.close()

        self.verification(opcode_data)

        self.clear()

    def send_lightbar_data(self):
        # Send Lightbar data. Again similar logic to sending the slab but now the opcode is different
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
        opcode_data1.extend([0xff, 0xfa])  # Lightbar Opcode 1
        opcode_data1.extend(self.data_array)
        self.pico_return = self.spi.xfer3(opcode_data1)
        self.verification(opcode_data1)

        time.sleep(0.10)

        opcode_data2 = bytearray()
        opcode_data2.extend([0xff, 0xfb])  # Lightbar Opcode 2
        opcode_data2.extend(self.data_array2)
        self.pico_return = self.spi.xfer3(opcode_data2)
        self.verification(opcode_data2)

        self.spi.close()
        self.clear()


# The main callback function for the MQTT Message Handling
# Every message that the main Pi receives is processed through this function
# TODO There might be vestigial and upgrades to this still needs to be made
#  (IE Figure out what to do when Error are received)
def on_message(client, userdata, message):

    print(f"Main RPi received: {message.topic} -> {message.payload}")
    # Extract the message topic and payload (which needs to be decoded from the struct) for sorting
    topic = message.topic
    payload = message.payload.decode()

    if topic == TOPIC_HANDSHAKE:
        # If the message is on the HANDSHAKE topic,
        # Add the Sub_PCCS's ID to a list of alive devices (workers_ready)
        if payload.startswith("READY_"):
            sub_id = payload.removeprefix("READY_")  # Python 3.9+; or use slicing
            print(f"{sub_id} is online.")
            workers_ready.add(sub_id)


    elif topic.startswith("pccs/status/"):
        # If the message comes from the STATUS topic, extract the id of the sender and process
        sub_id = topic.split("/")[-1]  # Extracts "PCCS_Sub_1"
        try:
            data = json.loads(payload)
            status = data.get("status", "")

            # If the status is a ready to flash, which the Subs send after writing their Picos,
            # add that device to the list
            if status == "ready_for_flash":
                print(f"{sub_id} is ready for flash.")
                with ready_lock:
                    ready_for_flash.add(sub_id)

            # A heartbeat mechanism is implemented in which the Sub PCCS send out a heartbeat every n seconds.
            # We can use this information to figure out when network connectivity has issues
            elif status == "alive":  # Heartbeat messages
                #print(f"[{sub_id}] Heartbeat at {data['timestamp']}")
                last_heartbeat[sub_id] = data['timestamp']

        # if the status message is in a broken format
        except Exception as e:
            print("Error parsing status message:", e)

    elif topic.startswith("pccs/error/"):
        # Process Error messages from the sub PCCS
        # TODO this should stop the main PCCS from continuing its look until it has recieved a status maybe "All good"
        worker = topic.split("/")[-1]
        data = json.loads(payload)
        print(f"[{worker}] Error: {data['message']}")
        # Optionally log to file or alert here

# A function that checks if all the expected workers (from the handshake) are ready, checking every 0.1 seconds with a
# variable timeout
def wait_for_all_ready(expected_workers, timeout=5):
    start = time.time()
    print(f"[wait_for_all_ready] Expected: {expected_workers}")
    print(f"[wait_for_all_ready] Got ready: {ready_for_flash}")
    while time.time() - start < timeout:
        with ready_lock:
            if ready_for_flash >= expected_workers:
                return True
        time.sleep(0.1)
    return False


if __name__ == '__main__':
    time.sleep(2)

    # Init the MQTT Client and connect it to the MQTT Broker
    client = mqtt.Client(client_id="Sender")
    client.connect(broker_ip, 1883, 60)

    # Create the Ready for flash set and ready_lock which allows for blocking while receiving the messages
    # This helps prevent data corruption/race conditions.
    ready_for_flash = set()
    ready_lock = threading.Lock()

    # Start the listening/handling of the MQTT communication and subscribe to the topics
    client.loop_start()
    client.subscribe(TOPIC_HANDSHAKE)
    client.subscribe(TOPIC_STATUS)
    client.subscribe(TOPIC_ERROR)

    # Define the callback function that process incoming messages.
    client.on_message = on_message

    # The expected devices, these need to be hardcoded onto the Receiver.Py
    expected_workers = {"PCCS_Sub_1", "PCCS_Sub_2", "PCCS_Sub_3"}
    # Create a set of connected PCCS and keep info on their last heartbeat
    workers_ready = set()
    last_heartbeat = {}

    # Send out the "SYNC" message on the HANDSHAKE topic, the PCCS_Subs will respond with a message which will then
    # populate the workers_ready set
    client.publish(TOPIC_HANDSHAKE, "SYNC")
    print("Sent SYNC handshake to all listeners")

    # Wait up to 6 seconds for READY responses
    time.sleep(6)
    print(f"Workers online: {workers_ready}")

    # Finally try to create the Import_csv objects with the parameters called when running the function
    # The third optional argument is the number of repeats which defaults of 1
    if len(sys.argv) == 3:
        Import = Import_csv(sys.argv[1], int(sys.argv[2]))
        Import.start_csv_run()
        print("Import Run finished successfully")
    if len(sys.argv) == 2:
        Import = Import_csv(sys.argv[1])
        Import.start_csv_run()
        print("Import Run finished successfully")
    else:
        print("Usage: python LV_Import.py <file_path> Optional<number of repeats>\n")
        print(
            "For the usage and system information please refer to Github Repo: MilliQan-Experiment-LV-Dist-Calibration "
            "(will need to search within github)")
        sys.exit(1)
