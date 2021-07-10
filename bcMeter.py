#!/usr/bin/env python3

import os
os.chdir('/home/pi')

import smbus
import time, traceback
import datetime
import RPi.GPIO as GPIO
import subprocess
import numpy
import os
import busio
from pathlib import Path
from board import SCL, SDA
from time import sleep, strftime, time
from datetime import datetime
from threading import Thread
from gpiozero import Button
#import Python_BMP.BMP085 as BMP085 #uncomment for use with  temperature sensor 

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1)
#bmp = BMP085.BMP085() #uncomment for use with  temperature sensor 


#parameters for calculation of bc
sampleTime=5 #time between samples in minutes
airFlow=0.360 #airflow per minute in liter
SG = 0.0000125 * 1.7 #specific attenuation cross section in m2/ng - .0000125 is base as used for standard paper, 1.7 is correction for pallflex t60a20
spotArea=numpy.pi*(0.50/2)**2 #area of spot in cm2 from bcmeter, diameter 5mm
airVolume=sampleTime*airFlow #liters of air between samples	



BUTTON = 16
POWERPIN = 26


# MCP3426 I2C 16-Bit 1-Channel Analog to Digital Converter I2C Mini Module initialization by  Amanpal Singh

MCP3426_DEFAULT_ADDRESS			= 0x68
MCP3426_CONF_A0GND_A1GND		= 0x68
MCP3426_CONF_A0GND_A1FLT		= 0x69
MCP3426_CONF_A0GND_A1VCC		= 0x6A
MCP3426_CONF_A0FLT_A1GND		= 0x6B
MCP3426_CONF_A0VCC_A1GND		= 0x6C
MCP3426_CONF_A0VCC_A1FLT		= 0x6D
MCP3426_CONF_A0VCC_A1VCC		= 0x6E
MCP3426_CONF_A0FLT_A1VCC		= 0x6F

# /RDY bit definition
MCP3426_CONF_NO_EFFECT			= 0x38
MCP3426_CONF_RDY				= 0x80

# Conversion mode definitions
MCP3426_CONF_MODE_ONESHOT		= 0x00
MCP3426_CONF_MODE_CONTINUOUS	= 0x10

# Channel definitions
#MCP3425 have only the one channel
#MCP3426 & MCP3427 have two channels and treat 3 & 4 as repeats of 1 & 2 respectively
#MCP3428 have all four channels
MCP3426_CONF_CHANNEL_1			= 0x18
MCP3426_CONF_CHANNEL_2			= 0x38

MCP3426_CONF_SIZE_12BIT			= 0x00
MCP3426_CONF_SIZE_14BIT			= 0x04
MCP3426_CONF_SIZE_16BIT			= 0x08
#MCP342X_CONF_SIZE_18BIT		= 0x0C

# Programmable Gain definitions
MCP3426_CONF_GAIN_1X			= 0x00
MCP3426_CONF_GAIN_2X			= 0x01
MCP3426_CONF_GAIN_4X			= 0x02
MCP3426_CONF_GAIN_8X			= 0x03

#Default values for the sensor
ready = MCP3426_CONF_RDY
#channel = MCP3426_CONF_CHANNEL_1
channelSen = MCP3426_CONF_CHANNEL_1
channelRef = MCP3426_CONF_CHANNEL_2
mode = MCP3426_CONF_MODE_CONTINUOUS
rate = MCP3426_CONF_SIZE_12BIT
gain = MCP3426_CONF_GAIN_1X
VRef = 2.048






def initialise():
	GPIO.setmode(GPIO.BCM)
	GPIO.setup(POWERPIN, GPIO.OUT)
	GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP) 

	bus.write_byte(MCP3426_DEFAULT_ADDRESS,ready)
	bus.write_byte(MCP3426_DEFAULT_ADDRESS,channelSen)
	bus.write_byte(MCP3426_DEFAULT_ADDRESS,mode)
	bus.write_byte(MCP3426_DEFAULT_ADDRESS,rate)
	bus.write_byte(MCP3426_DEFAULT_ADDRESS,gain)   



def debugging():

    bus.write_byte(MCP3426_DEFAULT_ADDRESS, channelSen)
    sleep(0.1)
    data = bus.read_i2c_block_data(MCP3426_DEFAULT_ADDRESS, 0x00, 2)
    raw_adc = (data[0] * 256) + data[1]
    if raw_adc > 32767 :
            raw_adc -= 65536
    bcmSenRaw = (raw_adc/2**12)
    os.system('clear')
    print ("ADC bcmSenRaw Output channel 1 : %.2f" %bcmSenRaw) #sensor
    sleep(0.1)
    bus.write_byte(MCP3426_DEFAULT_ADDRESS, channelRef)
    sleep(0.1)
    data = bus.read_i2c_block_data(MCP3426_DEFAULT_ADDRESS, 0x00, 2)
    raw_adc = (data[0] * 256) + data[1]
    if raw_adc > 32767 :
            raw_adc -= 65536
    bcmSenRaw = (raw_adc/2**12)
	# Output data to screen
    print ("ADC bcmSenRaw Output channel 2 : %.2f" %bcmSenRaw) #reference
    GPIO.output(POWERPIN, 0)
    sleep(0.5)





#Get the measurement for the ADC values  from the register

def readADC(channel, light):	
	if (light == 1):
		GPIO.output(POWERPIN, 1)
	#sleep(0.01) #wait for led to be at full brightness
	bus.write_byte(MCP3426_DEFAULT_ADDRESS, channel)
	#debugging()
	sleep(0.1)
	data = bus.read_i2c_block_data(MCP3426_DEFAULT_ADDRESS, 0x00, 2)
	if (light == 1):
		GPIO.output(POWERPIN, 0)
	sleep(0.2)
	value = ((data[0] << 8) | data[1])
	if (value >= 32768):
		value = 65536 -value
	return value
	
# The output code is proportional to the bcmSenRaw difference b/w two analog points
#Checking the conversion value
#Conversion of the raw data into 
# Shows the output codes of input level using 16-bit conversion mode

def getSenRaw(light):
	if (light == 1): #LED on 
		adcOutSen = readADC(channelSen,1)
		adcOutRef = readADC(channelRef,1)
	else: #Check light bias
		adcOutSen = readADC(channelSen,0)
		adcOutRef = readADC(channelRef,0)
	N = 12 # resolution,number of bits
	bcmSenRawSen = (2 * VRef* adcOutSen)/ (2**N)
	bcmSenRawRef = (2 * VRef* adcOutRef)/ (2**N)
	return int(bcmSenRawSen*1000),int(bcmSenRawRef*1000)

		

#Initialising the Device.
initialise()


def pressed():
    #start / stop measuring, reboot, etc. - to be implemented
    sleep(0.2)

sw1 = Button(BUTTON)
sw1.when_pressed = pressed


def createLog(log,header):
	Path("/home/pi/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile("/home/pi/logs/current.csv"):
		os.remove("/home/pi/logs/current.csv")
	with open("/home/pi/logs/" + log, "a") as logfileArchive: #save this logfile for archive
		logfileArchive.write(header + "\n\n")
	with open("/home/pi/logs/current.csv", "a") as logfileCurrent: # temporary current logfile for web interface
		logfileCurrent.write(header + "\n\n")


try:
	bcmRefBias=bcmSenBias=bcmRefFallback=bcmSenRef=bcmRefTmp=bcmRef=bcmRefOld=bcmRefNew=bcmSenNew=bcmSenOld=bcmATNnew=bcmATNold=BCngm3=BCngm3pos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=bcmTemperatureNew=bcmTemperatureOld=1
	flag = ""
	calibrated = bcmSen = absorb = bcmSenRaw = attenuation = 0.000
	today = str(datetime.now().strftime("%y-%m-%d"))
	now = str(datetime.now().strftime("%H:%M:%S"))
	logFileName = str("log_" + str(today) + "_" + str(now) + ".csv").replace(':','')
	header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3;Temperature;flag;rawSen"
	createLog(logFileName,header)
	print(today, now, "bcM 1.0 10.07.21 - STARTED NEW LOG", logFileName)
	print(str(header).replace(";","\t\t"))
	while(True):
		with open("/home/pi/logs/" + logFileName, "a") as log:
			bcmSenTmp=bcmRefTmp=temperatureTmp=0
			for i in range(5):
				bcmSenRaw = getSenRaw(0) #get actual bias by environmental light change with LED OFF
				bcmSenTmp = bcmSenTmp + bcmSenRaw[0]
				bcmRefTmp = bcmRefTmp + bcmSenRaw[1]
			bcmSenBias=int(bcmSenTmp/(i+1))
			bcmRefBias=int(bcmRefTmp/(i+1))
			bcmSenTmp=bcmRefTmp=temperatureTmp=0
			for i in range(9):
				bcmSenRaw = getSenRaw(1)
				#temperatureTmp = temperatureTmp + (bmp.read_temperature()) #uncomment for use with  temperature sensor 
				bcmSenTmp = bcmSenTmp + bcmSenRaw[0]
				bcmRefTmp = bcmRefTmp + bcmSenRaw[1]
				#sleep(0.1) 
			if (temperatureTmp == 0):
				temperatureTmp=1
			bcmSenNew=int(bcmSenTmp/(i+1))-bcmSenBias
			bcmRefNew=int(bcmRefTmp/(i+1))-bcmRefBias
			if (bcmRefNew == 0):
				bcmRefNew = 1 #avoid divide by 0
			if (bcmRefNew < 100) and (bcmRefFallback == 1): #when there is no reference signal, use first sensor signal as reference fallback. suitable for stable environments
				bcmRefFallback = bcmSenNew
			if (bcmRefNew < 100) and (bcmRefFallback > 100):
				bcmRefNew = bcmRefFallback
			#bcmTemperatureNew = round(temperatureTmp/(i+1),1) # uncomment for use with  temperature sensor 
			if (bcmSenOld==1):
				bcmSenOld = bcmSenNew
			if (bcmRefOld ==1):
				bcmRefOld = bcmRefNew

			if (bcmTemperatureOld/bcmTemperatureNew != 1):
				flag = flag + "tempChange;" + str(bcmSenNew)
			if  ((bcmSenNew/bcmSenOld) < 0.999):
				flag="E;" + str(bcmSenNew) #"safe" attenuation for moderate pollution
			else:
				flag="U;" + str(bcmSenNew) #very low (unsure) attenuation - observe the trend / rolling average. 
			bcmATNnew=round((numpy.log(bcmSenNew/bcmRefNew)*-100),4)
			if (bcmATNold == 1):
				bcmATNold = bcmATNnew
			bcRelativeLoad=round(((bcmATNnew-bcmATNold)/SG),4)
			BCngm3 = int(bcRelativeLoad * (spotArea / airVolume)) #bc nanograms per m3
			logString = str(datetime.now().strftime("%y-%m-%d")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(bcmRefNew) +";"  +str(bcmSenNew) +";" +str(bcmATNnew) + ";"+  str(bcRelativeLoad) +";"+ str(BCngm3) + ";" + str(bcmTemperatureNew) + ";" + str(flag)
			print(str(logString).replace(";","\t\t"))
			log.write(logString+"\n")
			with open("/home/pi/logs/current.csv", "a") as logfileCurrent: #logfile for web interface. will be deleted every time a new measurement starts
				logfileCurrent.write(logString+"\n")
			flag=""
			bcmSenOld=bcmSenNew 
			bcmATNold=bcmATNnew
			bcmTemperatureOld = bcmTemperatureNew

			flag=""
						
			#sleep(240.1) #whole run takes about 20s so sleep for 4 minutes and 40 seconds to have 5 minutes time samples. adjust for other timebase here and also in "sampleTime" variable
			sleep(1) #for debugging
except KeyboardInterrupt: 
	#traceback.print_exc()
	print("Exit")
	GPIO.output(POWERPIN, 0)
	pass
	#print("Save to switch off in 30s!")

