#!/usr/bin/env python3
import os
os.chdir('/home/pi')

import sys
import smbus
import time, traceback
import datetime
import RPi.GPIO as GPIO
import subprocess
import numpy
import os
import busio
import csv
from tabulate import tabulate
from pathlib import Path
from board import SCL, SDA, I2C
from time import sleep, strftime, time
from datetime import datetime
from threading import Thread
from gpiozero import Button

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1)

### show this in admin interface

#uncomment for BMP Temperature Sensor:

#import Python_BMP.BMP085 as BMP085 #uncomment for use with  temperature sensor 
#bmp = BMP085.BMP085() #uncomment for use with  temperature sensor 
#uncomment line 218


#uncomment for DHT Sensor connected to M2 Header:

#import MyPyDHT
##import board
#import adafruit_dht
#dhtDevice = adafruit_dht.DHT22(board.D13, use_pulseio=False)



#parameters for calculation of bc
sampleTime=300 #time in seconds between samples
sampleCycles = 199 #higher = more accurate but takes more time. 0 is also a number so if you want 100 cycles use 99 here. 
airFlow=0.360 #airflow per minute in liter
SGBase = 0.0000125 #dont change specific attenuation cross section in m2/ng - .0000125 is base as used for pallflex T60A20
SGCorrection = 1 #set to correction factor for calibration i.e. 0.75 for AE33 Paper
SG = SGBase * SGCorrection 


spotArea=numpy.pi*(0.50/2)**2 #area of spot in cm2 from bcmeter, diameter 5mm
airVolume=(sampleTime/60)*airFlow #liters of air between samples	
debug = False #no need to change here
### hide this in admin interface


BUTTON = 16
POWERPIN = 26


# MCP3426 I2C 16-Bit 1-Channel Analog to Digital Converter I2C Mini Module initialization by  Amanpal Singh

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
ver = "bcMeter A/DC evaluation script v 0.9.5 2022-01-02"


def initialise():
	global MCP3426_DEFAULT_ADDRESS
	bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1
	for device in range(128):
		try:
			adc = bus.read_byte(device)
			if (hex(device) == "0x68"):
				MCP3426_DEFAULT_ADDRESS = 0x68
			elif (hex(device) == "0x6a"):
				MCP3426_DEFAULT_ADDRESS = 0x6a
		except: # exception if read_byte fails
			pass
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
		sleep(0.01) #wait for led to be at full brightness
	bus.write_byte(MCP3426_DEFAULT_ADDRESS, channel)
	sleep(0.1) #slower makes readings unstable. adc only likes max 15sps
	data = bus.read_i2c_block_data(MCP3426_DEFAULT_ADDRESS, 0x00, 2)
	if (light == 1):
		GPIO.output(POWERPIN, 0)
	sleep(0.05)
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
	else: #Check light/sensor bias
		adcOutSen = readADC(channelSen,0)
		adcOutRef = readADC(channelRef,0)
	N = 12 # resolution,number of bits
	bcmSenRawSen = (2 * VRef* adcOutSen)/ (2**N)
	bcmSenRawRef = (2 * VRef* adcOutRef)/ (2**N)
	return int(bcmSenRawSen*1000),int(bcmSenRawRef*1000)


def checkRun():
	cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fv screen | grep python3']
	process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, 
	stderr=subprocess.PIPE)
	my_pid, err = process.communicate()
	if len(my_pid.splitlines()) > 2:
		#print(len(my_pid.splitlines()))
		#print(my_pid)
		sys.stdout.write("bcMeter Script already running.\n")
		exit()
	else:
		initialise()

		
checkRun()



def pressed():
	#start / stop measuring, reboot, etc. - to be implemented
	sleep(0.2)

sw1 = Button(BUTTON)
sw1.when_pressed = pressed


def createLog(log,header):
	Path("/home/pi/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile("/home/pi/logs/log_current.csv"):
		os.remove("/home/pi/logs/log_current.csv")
	with open("/home/pi/logs/" + log, "a") as logfileArchive: #save this logfile for archive
		logfileArchive.write(header + "\n\n")
	with open("/home/pi/logs/log_current.csv", "a") as logfileCurrent: # temporary current logfile for web interface
		logfileCurrent.write(header + "\n\n")


if __name__ == '__main__':
	if (len(sys.argv)==2):
		if (sys.argv[1] == "debug"):
			sampleTime = 0 
			sampleCycles = 999
			debug = True
	try:
		bcmRefBias=bcmSenBias=bcmRefFallback=bcmSenRef=bcmRefTmp=bcmRef=bcmRefOld=bcmRefNew=bcmSenNew=bcmSenOld=bcmATNold=BCngm3=BCngm3pos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=bcmTemperatureNew=bcmTemperatureOld=1
		flag = ""
		calibrated = bcmSen = absorb = bcmSenRaw = attenuation = bcmATNnew = bcRelativeLoad = 0.0000
		today = str(datetime.now().strftime("%d-%m-%y"))
		now = str(datetime.now().strftime("%H:%M:%S"))
		logFileName = str("log_" + str(today) + "_" + str(now) + ".csv").replace(':','')
		header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3;Temperature;flag;bcmSenBias;bcmRefBias;sampleDuration"
		if (debug == False):
			createLog(logFileName,header)
			print(today, now, ver, "STARTED NEW LOG", logFileName)
		else:
			print(today, now + " - happy debugging")
		while(True):
			with open("/home/pi/logs/" + logFileName, "a") as log:
				start = time()
				bcmSenTmp=bcmRefTmp=bcmSenBiasTmp=bcmRefBiasTmp=temperatureTmp=1
				for i in range(sampleCycles):
					bcmSenRaw = getSenRaw(1)
					bcmSenTmp = bcmSenTmp + bcmSenRaw[0]
					bcmRefTmp = bcmRefTmp + bcmSenRaw[1]
					bcmSenRawBias = getSenRaw(0) #get actual bias by environmental light change with LED OFF
					bcmSenBiasTmp = bcmSenBiasTmp + bcmSenRawBias[0]
					bcmRefBiasTmp = bcmRefBiasTmp + bcmSenRawBias[1]

					if (debug == True):
						print(str(i) + " - BIAS (sen,ref): " + str(bcmSenRawBias) + ", RAW (sen, ref): " + str(bcmSenRaw))
### show this in admin interface
				#uncomment following line for temperature sensor BMP180
				#temperatureTmp = temperatureTmp + (bmp.read_temperature()) #uncomment for use with  temperature sensor 
				#uncomment the following line for use with DHT22
				#temperatureTmp = int(MyPyDHT.sensor_read(MyPyDHT.Sensor.DHT22, 13, reading_attempts=10, use_cache=True)[1]*10)/10
### hide this in admin interface

				bcmSenBias=int(bcmSenBiasTmp/(i+1))
				bcmRefBias=int(bcmRefBiasTmp/(i+1))
				bcmSenNew=int(bcmSenTmp/(i+1))-bcmSenBias
				bcmRefNew=int(bcmRefTmp/(i+1))-bcmRefBias
				if (temperatureTmp == 0):
					temperatureTmp=1
				bcmTemperatureNew = round(temperatureTmp,2) 
				if (bcmRefNew == 0):
					bcmRefNew = 1 #avoid later divide by 0; just for debug
				if (bcmSenNew == 0):
					bcmSenNew = 1#avoid later divide by 0; just for debug
				if (bcmRefNew < 100) and (bcmRefFallback == 1): #when there is no reference signal, use first sensor signal as reference fallback. suitable for stable environments
					bcmRefFallback = bcmSenNew
					flag=flag+"RefFallback-"
				if (bcmRefNew < 100) and (bcmRefFallback > 100):
					bcmRefNew = bcmRefFallback
					flag=flag+"noRef-"
				if (bcmRefFallback < bcmSenNew):
					bcmRefFallback=bcmRefNew
					flag=flag+"SetNewRef-"
				if (bcmSenNew < 1000):
					flag="checkLED-" 
				if (bcmSenOld==1):
					bcmSenOld = bcmSenNew
				if (bcmRefOld ==1):
					bcmRefOld = bcmRefNew

				if (bcmTemperatureOld/bcmTemperatureNew != 1):
					flag = flag + "tempChange-"
				if  ((bcmSenNew/bcmSenOld) < 0.999):
					flag=flag+"SA-" #"safe" attenuation for moderate pollution
				else:
					flag=flag+"LA-" # low (unsure) attenuation - observe the trend / rolling average. 
				
				bcmATNnew=round((numpy.log(bcmSenNew/bcmRefNew)*-100),5)
				if (numpy.isnan(bcmATNnew) == True):
					bcmATNnew = bcmATNold
					flag=flag+"noATN"
				if (bcmATNold == 1):
					bcmATNold = bcmATNnew
				bcRelativeLoad=round(((bcmATNnew-bcmATNold)/SG),5)
				BCngm3 = int(bcRelativeLoad * (spotArea / airVolume)) #bc nanograms per m3
				delay = time() - start
				logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(bcmRefNew) +";"  +str(bcmSenNew) +";" +str(bcmATNnew) + ";"+  str(bcRelativeLoad) +";"+ str(BCngm3) + ";" + str(bcmTemperatureNew) + ";" + str(flag) + ";" + str(bcmSenBias)  + ";" + str(bcmRefBias) + ";" + str(round(delay,1))
				if (debug == False):
					log.write(logString+"\n")
					with open("/home/pi/logs/log_current.csv", "a") as logfileCurrent: #logfile for web interface. will be deleted every time a new measurement starts
						logfileCurrent.write(logString+"\n")
				#else:
					#print(header.replace(";","\t"))
					#print(logString.replace(";","\t"))
				flag=""
				bcmSenOld=bcmSenNew 
				bcmATNold=bcmATNnew
				bcmTemperatureOld = bcmTemperatureNew

				flag=""
			
			if (debug == False):
				with open('logs/log_current.csv','r') as csv_file:
					os.system('clear')
					print(today, now, ver, logFileName)
					headers=[]
					with open('logs/log_current.csv','r') as csv_file:
						csv_reader = list(csv.reader(csv_file, delimiter=';'))
						print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
						print("Exit script with ctrl+c")


			#else:
				#print("cycle took " + str(round(delay,2)) + " seconds")
			if ((sampleTime)-delay <= 0):
				sleep(sampleTime)
			else:
				sleep((sampleTime)-delay)

	except KeyboardInterrupt: 
		#traceback.print_exc()
		print("\nWhen ready again, you may restart the script with 'python3 bcMeter.py' or just reboot the device itself")
		GPIO.output(POWERPIN, 0)
		pass

