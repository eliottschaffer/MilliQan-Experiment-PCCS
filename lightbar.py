import smbus2
import time

#Init the lightbar Mux, Address 0x20 or 0x21 to be set to all outputs.

bus = smbus2.SMBus(1)
MUX = 0x20

OUTPUT_PORT = 0x01
CONFIG_REGISTER = 0x03

#Sets all the MUX to Output mode (as opposed to input) Can now be controlled by 0x01 output port
bus.write_byte_data(MUX, CONFIG_REGISTER, 0x00)

def lightbar(row,column,red,yellow,blue):
    if not (0 <= row <= 3 or 0 <= column <= 7 or -1 < red < 2 or -1 < yellow < 2 or -1 < blue < 2):
        raise ValueError("Row 0-3, Column 0-7,  red, yellow, blue are all 0(off) or 1 (on)")

    #Lightbar Works as such
    # Mux controlls the exact location and which LED are on with its 8 outputs (a byte)
    #  row, bar(B,Y,R) ,column.   Bar means that 0 is light goes on, 1 is off
    #  [7 6] [5 4 3] [2 1 0]
    # So for example if we want column 2, with Yellow and Red in row 3, we would have
    # Column 2 in binary = 010
    # Yellow and Red is (011)Bar = (100)
    # row 3 is 11
    #Get binary of 11100010 = 0xE2  (Works)
#
    # Map cell colors to binary values (0 is on, 1 is off)
    LEDs = [blue, yellow, red]  # List of the color states (1 means off, 0 means on)
    LEDs_bar = [1 - b for b in LEDs]  # Convert it to the desired format where 0 means on

    # Row in binary (2 bits for 4 rows)
    row_bin = format(row, '02b')

    # Column in binary (3 bits for 8 columns)
    col_bin = format(column, '03b')

    # Now form the final byte:
    #  First, take the row bits and prepend to the binary representation
    #  Then, add the bar color bits
    #  Finally, the column bits will follow
    final_bin = row_bin + ''.join(map(str, LEDs_bar)) + col_bin

    # Convert the binary string to an integer
    final_value = int(final_bin, 2)

    # Convert the final integer to hexadecimal

    # Print the result in hexadecimal format
    print(f"Final value (hex): {final_value}")

    bus.write_byte_data(MUX, OUTPUT_PORT, final_value)

for row in range(4):  # Loop through rows 0-3
    for column in range(8):  # Loop through columns 0-7
        for red in [0, 1]:
            for yellow in [0, 1]:
                for blue in [0, 1]:
                    lightbar(row, column, red, yellow, blue)
                    time.sleep(0.5)  # Sleep for 0.5 seconds between each call

lightbar(2,4,1,0,0)


