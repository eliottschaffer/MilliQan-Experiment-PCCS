# PCCS_Receiver - This Program is designed for the MilliQan Slab detector Utilization of the PCCS. In the slab schema,
# there are 4 PCCS crates, one for each layer, which need to all work together. Specifically this program is the
# "Sub" Code which is run by one of the Sub PCCS. This is a streamlined version of the PCCS_Sender code which instead
# of processing the data from the csv, receives the data from the MQTT TOPICs.

# Only the new MQTT Functions will be Commented, for info about the main three objects, currently look at PCCS_Sender


#from rpi5 import Run

import paho.mqtt.client as mqtt
import struct
import time
import spidev
import gpiod
import smbus
import json
import threading
import traceback
import argparse
import logging

HEARTBEAT_INTERVAL = 15  # seconds

# Command-line argument for the receiver's ID
parser = argparse.ArgumentParser(description="Start PCCS Receiver with a specific ID")
parser.add_argument("--id", required=True, help="ID of this receiver (e.g., PCCS_Flasher, PCCS_Sub_1)")
args = parser.parse_args()

PI_ID = args.id

client_id = PI_ID
broker_ip = "128.141.91.10" # Change the Real IP


FIRST_RECONNECT_DELAY = 1
RECONNECT_RATE = 2
MAX_RECONNECT_COUNT = 12
MAX_RECONNECT_DELAY = 60

FLAG_EXIT = False


TOPIC_HANDSHAKE = "pccs/handshake"
TOPIC_DATA = f"pccs/data/{PI_ID}"
TOPIC_ACK = f"pccs/ack/{PI_ID}"
TOPIC_STATUS = f"pccs/status/{PI_ID}"
TOPIC_ERROR = f"pccs/error/{PI_ID}"
TOPIC_PULSE = f"pccs/pulse/{PI_ID}"
TOPIC_PREP = f"pccs/prep/{PI_ID}"


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

bus = smbus.SMBus(1)
pot_addr = 0x2c


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


def send_fastpulse(trigger, flashing_hz=3, number_of_pulses=10):
    # Same as the regular pulse with a different time.sleep, can become a function
    for i in range(0,number_of_pulses):
        Sys_Rst.set_value(0)
        Sys_Rst.set_value(1)

        OE.set_value(0)
        Pulse_En.set_value(1)
        print("Pulse  Allowed")

        Trigger_Send.set_value(trigger)
        Pulse_Send.set_value(1)
        time.sleep(1 / flashing_hz)  # 300Hz for DRS, ~ 3 for triggered DAQ

        Trigger_Send.set_value(0)
        Pulse_Send.set_value(0)

        Pulse_En.set_value(0)
        OE.set_value(1)
        print("Pulse No longer allowed")

    print("Fast Flash Over")
def set_length(length):
    # Set the length of the LED pulse.

    # First validate that length is a digit and within the range 100-1100
    if not isinstance(length, int) or length < 100 or length > 1100:
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
        bool_data = [(val != 0 and val != '') for val in chan_val]  # lets pulse go to non zero channels
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
            publish_error(err_msg=f"Desync Error in Pico {self.cs}", context="Failed Pico Verification")
            print("Entering Desync Fixing")
            self.desync_protocol()
    def desync_protocol(self):
        ## When desynced the pico is recieving the opcode and data in the wrong order.

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

        time.sleep(0.4)

        opcode_data2 = bytearray()
        opcode_data2.extend([0xff, 0xfd])
        opcode_data2.extend(self.data_array2)
        self.pico_return = self.spi.xfer3(opcode_data2)
        self.verification(opcode_data2)

        self.spi.close()
        self.clear()

    def layer_scan(self, bad_chans):

        self.spi.open(0, self.cs)
        self.spi.max_speed_hz = 50 * 1000
        self.spi.mode = 0

        # print(data)
        # for byte in data:
        #     self.spi.xfer3([byte])
        opcode_scan = bytearray()
        opcode_scan.extend([0xff, 0xfe])
        opcode_scan.extend(bad_chans) # 16 values
        opcode_scan.extend([0x00 for _ in range(18)])
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

    def i2c_scan(self, bad_chans):
        for index in range(self.number_of_layers):
            self.olayer[index].layer_scan(bad_chans[index * 16:(index+1) * 16])

    def set_slab_blade_data(self, chan_val):
        for i in range(self.number_of_layers):
            print("Chan ", i, "is getting data ", chan_val[i * 32:(i + 1) * 32])
            self.olayer[i].set_data(chan_val[i * 32:(i + 1) * 32])


    def send_slab_data(self):
        # Tells the layer objects to send their data to the Picos
        for _ in range(len(self.olayer)):
            self.olayer[_].send_slab_data()

class PCCS_Receiver:
    def __init__(self):
        self.odetector = Detector(2)

    def set_layer(self,data):
        self.slab_run(data)

    def initialize(self,bad_chans):
        Sys_Rst.set_value(0)
        Sys_Rst.set_value(1)
        time.sleep(1)
        self.odetector.i2c_scan(bad_chans)


    def slab_run(self, data):
        print("Entered Slab Run")
        print("Processed chan val", data)

        self.odetector.set_slab_blade_data(data)
        self.odetector.send_slab_data()
        time.sleep(0.3)


def publish_heartbeat():
    while True:
        try:
            payload = {
                "status": "alive",
                "timestamp": int(time.time()),
                "hostname": PI_ID
            }
            client.publish(TOPIC_STATUS, json.dumps(payload))
        except Exception as e:
            print("Heartbeat error:", e)
        time.sleep(HEARTBEAT_INTERVAL)

def publish_error(err_msg, context="general"):
    error = {
        "status": "error",
        "timestamp": int(time.time()),
        "context": context,
        "message": err_msg,
    }
    client.publish(TOPIC_ERROR, json.dumps(error))

def publish_ready_for_flash():
    ready_msg = {
        "status": "ready_for_flash",
        "timestamp": int(time.time()),
        "hostname": PI_ID
    }
    client.publish(TOPIC_STATUS, json.dumps(ready_msg))


def publish_flash_done():
    ready_msg = {
        "status": "flash_done",
        "timestamp": int(time.time()),
        "hostname": PI_ID
    }
    client.publish(TOPIC_STATUS, json.dumps(ready_msg))


def on_message(client, userdata, message):
    try:
        topic = message.topic

        if topic == TOPIC_HANDSHAKE:
            msg = message.payload.decode()
            if msg == "SYNC":
                print(f"Handshake request received, responding with READY from {PI_ID}")
                client.publish(TOPIC_HANDSHAKE, f"READY_{PI_ID}")


        elif topic == TOPIC_PREP:
            bad_channel_packed = message.payload
            bad_channels = struct.unpack(">24B", bad_channel_packed)
            bad_channels_data = list(bad_channels) + [0] * 16
            pccs_receiver.initialize(bad_channels_data)

        elif topic == TOPIC_DATA:

            data = message.payload
            if PI_ID == "PCCS_Flasher":
                unpacked = struct.unpack(">49H", data)
                length = unpacked[0]
                set_length(length)
                voltages = unpacked[1:]  # 48 values
            else:
                voltages = struct.unpack(">48H", data)

            slab_layer_data = list(voltages) + [0] * 16
            pccs_receiver.set_layer(slab_layer_data)
            publish_ready_for_flash()

        elif topic == TOPIC_PULSE:
            try:
                msg = json.loads(message.payload.decode())  # Decode and parse JSON
            except Exception as e:
                print(f"Failed to parse pulse message: {e}")
                return

            pulse_type = msg.get("type", "")
            trigger = msg.get("trigger", 0)

            if pulse_type == "single":
                send_pulse(trigger)

            elif pulse_type == "fast":
                rate = msg.get("rate", None)
                count = msg.get("count", None)
                if rate is not None and count is not None:
                    send_fastpulse(trigger, rate, count)  # Define this function to handle fast pulses
                    publish_flash_done()
                else:
                    print(f"Incomplete fast pulse info: {msg}")

            else:
                print(f"Unknown pulse type received: {pulse_type}")


    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{PI_ID}] Error in on_message: {e}")
        publish_error(tb, context="on_message")


def on_disconnect(client, userdata, rc):
    logging.info("Disconnected with result code: %s", rc)
    reconnect_count, reconnect_delay = 0, FIRST_RECONNECT_DELAY
    while reconnect_count < MAX_RECONNECT_COUNT:
        logging.info("Reconnecting in %d seconds...", reconnect_delay)
        time.sleep(reconnect_delay)

        try:
            client.reconnect()
            logging.info("Reconnected successfully!")
            return
        except Exception as err:
            logging.error("%s. Reconnect failed. Retrying...", err)

        reconnect_delay *= RECONNECT_RATE
        reconnect_delay = min(reconnect_delay, MAX_RECONNECT_DELAY)
        reconnect_count += 1
    logging.info("Reconnect failed after %s attempts. Exiting...", reconnect_count)
    global FLAG_EXIT
    FLAG_EXIT = True


if __name__ == '__main__':

    client = mqtt.Client(client_id=PI_ID)

    pccs_receiver = PCCS_Receiver()

    client.on_message = on_message
    client.connect(broker_ip, 1883, 60)
    client.on_disconnect = on_disconnect
    client.subscribe(TOPIC_HANDSHAKE)
    client.subscribe(TOPIC_DATA)
    client.subscribe(TOPIC_PREP)

    if PI_ID == "PCCS_Flasher":
        client.subscribe(TOPIC_PULSE)

    # client.publish(TOPIC_HANDSHAKE, f"READY_{PI_ID}")

    # Heartbeat of PCCS Sub ID to Main Pi. Will be used in Combination with the ACK to determine what is wrong.
    heartbeat_thread = threading.Thread(target=publish_heartbeat, daemon=True)
    heartbeat_thread.start()

    client.loop_forever()
