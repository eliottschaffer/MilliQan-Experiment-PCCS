# PCCS Sender - This Program is designed for the MilliQan Slab detector Utilization of the PCCS. In the slab schema,
# there are 4 PCCS crates, one for each layer, which need to all work together. Specifically this program is the
# "Main" Code which is run by the Main PCCS and this is where the CSV file is imported.

# from rpi5 import Run
import paho.mqtt.client as mqtt
import struct
import json
import threading
import time
from threading import Event
import datetime
import csv
import sys

broker_ip = "128.141.91.10"  # Replace with MillQan PC's IP (Or where ever the MQTT Broker is initialized),
# see GitHub readme

# MQTT Topics (Sending)
TOPIC_HANDSHAKE = "pccs/handshake"
TOPIC_DATA = "pccs/data"
TOPIC_PULSE = f"pccs/pulse/PCCS_Flasher"
TOPIC_PREP = "pccs/prep"

TOPIC_LIGHTBAR_DATA = "pccs/lightbar/data"


# MQTT Topics (Receiving)
# The /+ flag allows for all the PCCS_Sub_#
TOPIC_STATUS = "pccs/status/+"
TOPIC_ERROR = "pccs/error/+"
TOPIC_CLEAR = "pccs/clear/+"

# The expected devices, these need to be hardcoded onto the Receiver.Py
expected_workers = {"PCCS_Flasher", "PCCS_Sub_1", "PCCS_Sub_2", "PCCS_Sub_3"}

# Known Bad Channels, hardcoded into Controller - distributed to the rest
bad_channels = [0] * 96

# Encode all the bad Channels Manually
# 0 (default) both devices are assumed working
# 1 Means 0x4D is dead
# 2 Means 0x4C is dead
# 3 Means both I2C devices are dead

bad_channels[0] = 3  # channel 4 has dead chan 1
bad_channels[1] = 3
bad_channels[3] = 3
bad_channels[8] = 3
bad_channels[16] = 3
bad_channels[17] = 3
bad_channels[21] = 3

bad_channels[4 + 24] = 3
bad_channels[5 + 24] = 3
bad_channels[6 + 24] = 3
bad_channels[4 + 24] = 3
bad_channels[8 + 24] = 3
bad_channels[15 + 24] = 3
bad_channels[17 + 24] = 3

bad_channels[6 + 48] = 3
bad_channels[14 + 48] = 3

bad_channels[12 + 72] = 3
bad_channels[13 + 72] = 3
bad_channels[16 + 72] = 3
bad_channels[17 + 72] = 3

# Logging of Desync, TODO update this to include more information.
def log_timestamp(file_path="desync.log", event="Unknown Event"):
    """Logs the current timestamp and event description to a file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "a") as f:
        f.write(f"{timestamp} - {event}\n")


def log_error(error=None, device=None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("error.log", "a") as f:
        if isinstance(error, Exception):
            f.write(f"[{timestamp}] {device or 'UNKNOWN'}: Exception: {str(error)}\n")
        else:
            f.write(f"[{timestamp}] {device or 'UNKNOWN'}: Error: {error}\n")


class ErrorManager:
    def __init__(self, expected_devices=None):
        # device_id -> set of active error IDs
        self.error_events = {}
        self.lock = threading.Lock()

    def set_error(self, device_id, error_id):
        with self.lock:
            if device_id not in self.error_events:
                self.error_events[device_id] = set()
            self.error_events[device_id].add(error_id)

    def clear_error(self, device_id, error_id):
        with self.lock:
            if device_id in self.error_events:
                self.error_events[device_id].discard(error_id)
                if not self.error_events[device_id]:
                    del self.error_events[device_id]

    def wait_for_all_clear(self, timeout=None):
        start = time.time()
        while True:
            with self.lock:
                has_errors = any(self.error_events.values())
            if not has_errors:
                return True
            if timeout and (time.time() - start) >= timeout:
                return False
            time.sleep(0.1)


def Initialize_Devices():
    # Send Command to Init Picos/Base Reading - Where we expect the majority of Errors to occur
    publish_bad_channels_data(bad_channels)
    time.sleep(6)


class Import_csv:

    # Import_csv Init, the object is initialized with the csv file that is desired and the number of times that the
    # csv file should be repeated - allows for smaller files to be used

    # Aditionally a repeat column could be added to each flashing event in the csv file to allow more compression.

    def __init__(self, csv_file, repeat_times=1):
        # Data array that will store the csv file
        self.data = []
        self.repeat = repeat_times
        self.flash_count_per_event = 0
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
        for CSV_repeat_times in range(0, self.repeat):

            # loop through every row (super flashing event, since we can have many flashes in one row)
            for flashing_super_event in range(len(self.data)):

                datai = self.data[flashing_super_event]
                # detector/use-case mentioned above
                detector_type = datai[0]
                # This is the one we are interested in, the slab_run function is the next step of the data pipeline.
                if detector_type != 'slab':
                    print("Wrong detector type format given")
                    exit()

                # How many times you want this flashing setup to be run
                flashing_event_repeat_times = (
                    int(datai[1].strip()) if datai[1].strip().isdigit() else 1
                )

                # Frequency of flashing
                flashing_rate = (
                    int(datai[2].strip()) if datai[2].strip().isdigit() else 3
                )

                # Trigger MilliDAQ or not
                trigger = (
                    int(datai[3].strip()) if datai[3].strip().isdigit() else 0
                )

                for flash in range(0, flashing_event_repeat_times):
                    print(f"flash_count_per_event: {self.flash_count_per_event}, good_events: {self.good_events}")
                    if self.flash_count_per_event > 4 and self.good_events > 4:
                        print("Switching to fast flashing")
                        pccs_controller.clear_flash_done()

                        publish_send_fast_pulse(trigger, flashing_rate, flashing_event_repeat_times - 5)

                        expected_flashing_time = int(flashing_event_repeat_times / flashing_rate)
                        acceptable_delay_time = expected_flashing_time * 2

                        # wait for a signal back (e.g., "READY_FOR_NEXT")
                        pccs_controller.wait_for_flashing_end(acceptable_delay_time)

                        self.flash_count_per_event = 0  # reset for next super event
                        break
                    else:
                        self.slab_run(datai)
                        self.flash_count_per_event += 1

                # Debug
                # print(datai, detector_type)

            time.sleep(0.5)

    # Process the data in the csv for the different detector functions
    def slab_run(self, datai):

        print("Entered Slab Run")

        # Length of LED Pulse ~ 100-1100 ns
        pulse_length = int(datai[4])
        trigger = int(datai[3])

        # The data for each of the 192 channels (PMT Leds) in the Slab detector
        chan_val = datai[5:197]

        # Clean up the CSV, limit the voltage to be 4000 DAC counts (voltage setter).
        processed_chan_val = [
            '0' if val.strip() == '' or not val.strip().isdigit()
            else ('4000' if int(val) > 4000 else val.strip())
            for val in chan_val
        ]

        # Split the Data for the whole detector into 4 parts for each slab layer.
        data_segment_flasher = [int(x) for x in processed_chan_val[0:48]]
        data_sub = [int(x) for x in processed_chan_val[48:192]]
        data_slices = [data_sub[i * 48:(i + 1) * 48] for i in range(3)]

        # Debug
        # print("data_main", data_segments_main)
        # print("data_sub", data_sub)

        # Ready_lock is a blocking method for the set ready_for_flash. It is used to keep track of when all hand-shook
        # devices have successfully sent their data to the picos and received good responses.
        pccs_controller.clear_ready_for_flash()

        # Construct the flashing data, which is larger to as it needs to set the pulse length of the event

        flasher_data = [int(pulse_length)] + data_segment_flasher
        flasher_packed = struct.pack(">49H", *flasher_data)
        client.publish(f"pccs/data/PCCS_Flasher", flasher_packed)

        for i, slice_ in enumerate(data_slices):
            # For each Sub PCCS, format the Data it needs into the MQTT req struct
            # Publish the data to the topic below, with /{device_id}
            sub_packed = struct.pack(">48H", *slice_)
            device_id = f"PCCS_Sub_{i + 1}"
            client.publish(f"pccs/data/{device_id}", sub_packed)

        # After sending all the instructions, we wait for the Sub PCCS to respond ready, if within 10 seconds
        # not every PCCS has responded, we will not send the pulse and instead skip the pulse, moving to the
        # next flashing event
        if pccs_controller.wait_for_all_ready(timeout=10):
            print("All subs ready — firing pulse")
            publish_send_pulse(trigger)
            self.good_events += 1
            print(f"good_events incremented: {self.good_events}")
            time.sleep(3)
        else:
            print("Timeout waiting for all subs — skipping this pulse")
            log_error(device="System", error="Timeout waiting for Devices to respond ready after sending Data")
            self.good_events = 0
            time.sleep(0.10)


class PCCSController:
    def __init__(self):
        self.ready_for_flash = set()
        self.ready_lock = threading.Lock()

        self.workers_online = set()
        self.workers_lock = threading.Lock()

        self.flash_done = Event()
        self.flash_lock = threading.Lock()

        self.last_heartbeat = {}
        self.heartbeat_status = {}
        self.heartbeat_lock = threading.Lock()

        self.expected_workers = set(expected_workers)

    def update_heartbeat(self, device_id, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        with self.heartbeat_lock:
            self.last_heartbeat[device_id] = timestamp
            if not self.heartbeat_status.get(device_id, True):
                print(f"[INFO] {device_id} heartbeat restored.")
            self.heartbeat_status[device_id] = True

    def get_heartbeat(self, device_id):
        with self.heartbeat_lock:
            return self.last_heartbeat.get(device_id, 0)

    def mark_unhealthy(self, device_id):
        with self.heartbeat_lock:
            self.heartbeat_status[device_id] = False

    def is_healthy(self, device_id):
        with self.heartbeat_lock:
            return self.heartbeat_status.get(device_id, True)

    def mark_healthy(self, device_id):
        with self.heartbeat_lock:
            self.heartbeat_status[device_id] = True

    def add_worker_online(self, worker_id):
        with self.workers_lock:
            self.workers_online.add(worker_id)

    def get_workers_online(self):
        with self.workers_lock:
            return set(self.workers_online)

    def add_ready_for_flash(self, worker_id):
        with self.ready_lock:
            self.ready_for_flash.add(worker_id)

    def remove_ready_for_flash(self, worker_id):
        with self.ready_lock:
            self.ready_for_flash.discard(worker_id)

    def get_ready_for_flash(self):
        with self.ready_lock:
            return set(self.ready_for_flash)

    def is_worker_ready_for_flash(self, worker_id):
        with self.ready_lock:
            return worker_id in self.ready_for_flash

    def clear_ready_for_flash(self):
        with self.ready_lock:
            self.ready_for_flash.clear()

    def set_flash_done(self):
        with self.flash_lock:
            self.flash_done.set()

    def clear_flash_done(self):
        with self.flash_lock:
            self.flash_done.clear()

    # A function that checks if all the expected workers (from the handshake) are ready, checking every 0.1 seconds with a
    # variable timeout

    def wait_for_all_ready(self, timeout=10):
        start = time.time()
        print(f"[wait_for_all_ready] Expected: {self.workers_online}")

        while time.time() - start < timeout:
            with self.ready_lock:
                ready_copy = set(self.ready_for_flash)

            if ready_copy >= self.workers_online:
                print(f"[wait_for_all_ready] Got ready: {ready_copy}")
                return True
            time.sleep(0.5)

        print(f"[wait_for_all_ready] Got ready: {ready_copy}")
        return False

    def wait_for_flashing_end(self, timeout):
        print("Fast flash timeout length = ", timeout)
        self.flash_done.clear()  # Ensure we start waiting fresh
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.flash_done.is_set():
                self.flash_done.clear()
                print("Flashing complete")
                return True
            time.sleep(0.1)

        print("Timeout waiting for flasher finishing flashes")
        log_error(device="System", error="Timeout waiting for flashing complete signal")
        return False


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
            pccs_controller.add_worker_online(worker_id=sub_id)

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
                pccs_controller.add_ready_for_flash(sub_id)

            elif status == "flash_done":
                print("Received flash done")
                pccs_controller.set_flash_done()

            # A heartbeat mechanism is implemented in which the Sub PCCS send out a heartbeat every n seconds.
            # We can use this information to figure out when network connectivity has issues
            elif status == "alive":  # Heartbeat messages
                # print(f"[{sub_id}] Heartbeat at {data['timestamp']}")
                pccs_controller.update_heartbeat(sub_id, data['timestamp'])

        # if the status message is in a broken format
        except Exception as e:
            print("Error parsing status message:", e)
            log_error(error=e, device=sub_id)

    elif topic.startswith("pccs/error/"):
        # Process Error messages from the sub PCCS
        # TODO this should stop the main PCCS from continuing its look until it has recieved a status maybe "All good"
        worker = topic.split("/")[-1]
        try:
            data = json.loads(payload)
            message = data.get("message", "Unknown error")
            print(f"[{worker}] Error: {message}")

            # Set error state and log
            error_manager.set_error(worker, message)
            log_error(error=message, device=worker)
        except Exception as e:
            print(f"Failed to parse error message from {worker}: {e}")
            log_error(error=e, device=worker)

    elif topic.startswith("pccs/clear/"):
        # Clear Error from Picos
        worker = topic.split("/")[-1]
        try:
            data = json.loads(payload)
            message = data.get("message", "Unknown error")
            print(f"[{worker}] Error: {message}")

            # Set error state and log
            error_manager.set_error(worker, message)
            log_error(error=message, device=worker)
        except Exception as e:
            print(f"Failed to parse error message from {worker}: {e}")
            log_error(error=e, device=worker)

def monitor_heartbeat(pccs_ctrl, error_mang, timeout=60, check_interval=15):
    while True:
        now = time.time()
        for sub_id in pccs_ctrl.expected_workers:
            last = pccs_ctrl.get_heartbeat(sub_id)
            healthy = (now - last) < timeout

            if not healthy and pccs_ctrl.is_healthy(sub_id):
                print(f"[WARNING] Missed heartbeat from {sub_id}")
                pccs_ctrl.mark_unhealthy(sub_id)
                log_error(f"Missed heartbeat from {sub_id} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
                error_mang.set_error(sub_id, "Missing Heartbeat")

            if healthy and not pccs_controller.is_healthy(sub_id):
                print(f"[INFO] Heartbeat restored from {sub_id}")
                error_manager.clear_error(sub_id, "Missing Heartbeat")
                pccs_controller.mark_healthy(sub_id)
        time.sleep(check_interval)


def publish_send_pulse(trig):
    pulse_msg = {
        "type": "single",
        "trigger": trig
    }
    client.publish(TOPIC_PULSE, json.dumps(pulse_msg))


def publish_send_fast_pulse(trig, rate, number):
    pulse_msg = {
        "type": "fast",
        "trigger": trig,
        "rate": rate,  # e.g., Hz
        "count": number  # total number of pulses
    }
    client.publish(TOPIC_PULSE, json.dumps(pulse_msg))


def publish_bad_channels_data(bad_data_array):
    bad_channels_flasher = [int(x) for x in bad_data_array[0:24]]
    bad_chans_sub = [int(x) for x in bad_data_array[24:96]]

    data_slices = [bad_chans_sub[i * 24:(i + 1) * 24] for i in range(3)]

    flasher_packed = struct.pack(">24B", *bad_channels_flasher)
    client.publish(f"pccs/prep/PCCS_Flasher", flasher_packed)

    for i, slice_ in enumerate(data_slices):
        # For each Sub PCCS, format the Data it needs into the MQTT req struct
        # Publish the data to the topic below, with /{device_id}
        sub_packed = struct.pack(">24B", *slice_)
        device_id = f"PCCS_Sub_{i + 1}"
        client.publish(f"pccs/prep/{device_id}", sub_packed)


if __name__ == '__main__':
    time.sleep(2)

    # Init the MQTT Client and connect it to the MQTT Broker
    client = mqtt.Client(client_id="Controller")
    client.connect(broker_ip, 1883, 60)

    # Start the listening/handling of the MQTT communication and subscribe to the topics
    client.loop_start()
    client.subscribe(TOPIC_HANDSHAKE)
    client.subscribe(TOPIC_STATUS)
    client.subscribe(TOPIC_ERROR)
    client.subscribe(TOPIC_CLEAR)

    # PCCS Controller - Class that handles Locks
    # Error Manager - A separate class which handles locking of everything when errors occur
    # Heartbeat Manager - A class which handles the MQTT hearbeats
    pccs_controller = PCCSController()
    error_manager = ErrorManager(expected_workers)

    # Start Heartbeat monitor
    threading.Thread(target=monitor_heartbeat, args=(pccs_controller, error_manager), daemon=True).start()

    # Define the callback function that process incoming messages.
    client.on_message = on_message

    # Create a set of connected PCCS and keep info on their last heartbeat
    while "PCCS_Flasher" not in pccs_controller.get_workers_online():
        # Send out the "SYNC" message on the HANDSHAKE topic, the PCCS_Subs will respond with a message which will then
        # populate the workers_ready set
        client.publish(TOPIC_HANDSHAKE, "SYNC")
        print("Sent SYNC handshake to all listeners")

        # Wait up to 6 seconds for READY responses
        time.sleep(6)
        print(f"Workers online: {pccs_controller.get_workers_online()}")
        # Repeat until at least PCCS_Flasher device is connected

    # Finally try to create the Import_csv objects with the parameters called when running the function
    # The third optional argument is the number of repeats which defaults of 1
    if len(sys.argv) == 3:
        Import = Import_csv(sys.argv[1], int(sys.argv[2]))
        Initialize_Devices()
        Import.start_csv_run()
        print("Import Run finished successfully")
    if len(sys.argv) == 2:
        Import = Import_csv(sys.argv[1])
        Initialize_Devices()
        Import.start_csv_run()
        print("Import Run finished successfully")
    else:
        print("Usage: python PCCS_Control.py <file_path> Optional<number of repeats>\n")
        print(
            "For the usage and system information please refer to Github Repo: MilliQan-Experiment-LV-Dist-Calibration "
            "(will need to search within github)")
        sys.exit(1)
