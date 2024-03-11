# MilliQan-Experiment-LV-Dist-Calibration
Low-Voltage Distribution board for the MilliQan Experiment with abilities of PMT gain calibration and system emulation.

# Overview
The LV dist board can power up to 80 channels and selectively send pulses to each one. The system is made up of a motherboard and 5 submodules. These submodules are called blade pairs, one of which has a cheap microcontroller on it that communicates with the bases. Each submodule, henceforth blade(s), can control 8 bases with a pair controlling 16. There are 5 blade pairs on the system available.  The pulse will be of length ~ 450ns with variable voltage 0-3.3v in 4095 steps. The board has multiple safety features and overrides. These include replaceable 5x20mm fuses with LED indicators if they are blown, a manual pulse overrides off switch on the motherboard, and an easily replaceable and iterable system of motherboard and blades, which will allow for the system to have continued use with new applications.

The system uses SPI for communication from Raspberry Pi to the Blades. The messages will be detailed below but are a short byte sequence of which channels should be turned on and their respective voltages. The board also uses $I^2C$ communication for all integrated circuit chips on the board. This includes the light sensor ADC, the DAC voltage control on the bases, and a potentiometer. 

# Setup, Raspberry Pi
A standard installation can easily be g
