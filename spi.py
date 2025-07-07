# # spitest.py
# # A brief demonstration of the Raspberry Pi SPI interface, using the Sparkfun
# # Pi Wedge breakout board and a SparkFun Serial 7 Segment display:
# # https://www.sparkfun.com/products/11629
#
# import time
# import spidev
#
# # We only have SPI bus 0 available to us on the Pi
# bus = 0
#
# #Device is the chip select pin. Set to 0 or 1, depending on the connections
# device = 3
#
# # Enable SPI
# spi = spidev.SpiDev()
#
# # Open a connection to a specific bus and device (chip select pin)
# spi.open(bus, 0)
#
# # Set SPI speed and mode
# spi.max_speed_hz = 50
# spi.mode = 0
#
# # Clear display
# msg = [0x76]
# spi.xfer2(msg)
#
#
#
# msg = [0x21, 0x31, 0xf2, 0x2d]
# print(msg[0])
# spi.xfer2([msg[0]])
# spi.xfer2([msg[1]])
# spi.xfer2([msg[2]])
# spi.xfer2([msg[3]])
#
# spi.xfer([0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d])


# spitest.py
# A brief demonstration of the Raspberry Pi SPI interface, using the Sparkfun
# Pi Wedge breakout board and a SparkFun Serial 7 Segment display:
# https://www.sparkfun.com/products/11629

import time
import spidev

# We only have SPI bus 0 available to us on the Pi
bus = 0

#Device is the chip select pin. Set to 0 or 1, depending on the connections
device = 3

# Enable SPI
spi = spidev.SpiDev()

# Open a connection to a specific bus and device (chip select pin)
spi.open(bus, 0)

# Set SPI speed and mode
spi.max_speed_hz = 50
spi.mode = 0

# Clear display
msg = [0x76]
spi.xfer2(msg)



msg = [0x21, 0x31, 0xf2, 0x2d]
print(msg[0])
spi.xfer2([msg[0]])
spi.xfer2([msg[1]])
spi.xfer2([msg[2]])
spi.xfer2([msg[3]])

spi.xfer([0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d,0x21, 0x31, 0xf2, 0x2d])
