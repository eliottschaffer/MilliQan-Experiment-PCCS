import RPi.GPIO as GPIO
import time


GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(5,GPIO.OUT)
GPIO.setup(23, GPIO.OUT)
GPIO.setup(26, GPIO.OUT)


time.sleep(5)

GPIO.output(26,GPIO.LOW)

GPIO.output(26,GPIO.HIGH)


GPIO.output(5,GPIO.HIGH)
print("Pulse  Allowed")

GPIO.output(23,GPIO.HIGH)
time.sleep(1)
GPIO.output(23,GPIO.LOW)

GPIO.output(5,GPIO.LOW)
print("Pulse No longer allowed")




