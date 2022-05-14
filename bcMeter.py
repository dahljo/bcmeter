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
import typing
import re
import glob
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

MCP3426_DEFAULT_ADDRESS = 0x68

#parameters for calculation of bc
sampleTime=300 #time in seconds between samples
sampleCycles = 5000 #samples x 4 taken for sensor, reference, sensor bias and reference bias 
airFlow=0.360 #airflow per minute in liter
SGBase = 0.0000125 #dont change specific attenuation cross section in m2/ng - .0000125 is base as used for pallflex T60A20
SGCorrection = 1 #set to correction factor for calibration i.e. 0.75 for AE33 Paper
SG = SGBase * SGCorrection 
oneRunOnly = "false"
noBias = "false"
desTemp = 25
heating = False


spotArea=numpy.pi*(0.50/2)**2 #area of spot in cm2 from bcmeter, diameter 0.50cm
airVolume=(sampleTime/60)*airFlow #liters of air between samples	
debug = False #no need to change here
### hide this in admin interface

POWERPIN = 26
BUTTON = 16

ver = "bcMeter A/DC evaluation script v 0.9.5 2022-01-20"


class TemperatureSensor:
	RETRY_INTERVAL = 0.5
	RETRY_COUNT = 10

	def __init__(self, channel: int):
		GPIO.setmode(GPIO.BCM)
		GPIO.setup(channel, GPIO.IN)
		GPIO.setup(1,GPIO.OUT)
		GPIO.setup(23,GPIO.OUT)

	#def __del__(self):
		#GPIO.cleanup()

	@staticmethod
	def read_device() -> typing.List[str]:
		device_file_name = glob.glob('/sys/bus/w1/devices/28*')[0] + '/w1_slave'
		with open(device_file_name, 'r') as fp:
			return [line.strip() for line in fp.readlines()]

	def get_temperature_in_milli_celsius(self) -> int:
		"""
		$ cat /sys/bus/w1/devices/28-*/w1_slave
		c1 01 55 05 7f 7e 81 66 c8 : crc=c8 YES
		c1 01 55 05 7f 7e 81 66 c8 t=28062
		"""
		for i in range(self.RETRY_COUNT):
			lines = self.read_device()
			if len(lines) >= 2 and lines[0].endswith('YES'):
				match = re.search(r't=(\d{1,6})', lines[1])
				if match:
					return int(match.group(1), 10)
			time.sleep(self.RETRY_INTERVAL)
		raise Exception(
			F'Cannot read temperature (tried {self.RETRY_COUNT} times with an interval of {self.RETRY_INTERVAL})'
		)

class ADCPi:
	# internal variables

	__address = 0x68  # default address for adc 1 on adc pi and delta-sigma pi
	__config1 = 0x9C  # PGAx1, 18 bit, continuous conversion, channel 1
	__currentchannel1 = 1  # channel variable for adc 1
	__config2 = 0x9C  # PGAx1, 18 bit, continuous-shot conversion, channel 1
	__currentchannel2 = 1  # channel variable for adc2
	__bitrate = 12  # current bitrate
	__conversionmode = 1 # Conversion Mode
	__pga = float(0.5)  # current pga setting
	__lsb = float(0.0000078125)  # default lsb value for 18 bit

	# create byte array and fill with initial values to define size
	__adcreading = bytearray()
	__adcreading.append(0x00)
	__adcreading.append(0x00)
	__adcreading.append(0x00)
	__adcreading.append(0x00)

	global _bus

	# local methods

	def __updatebyte(self, byte, bit, value):
			# internal method for setting the value of a single bit within a
			# byte
		if value == 0:
			return byte & ~(1 << bit)
		elif value == 1:
			return byte | (1 << bit)

	def __checkbit(self, byte, bit):
			# internal method for reading the value of a single bit within a
			# byte
		bitval = ((byte & (1 << bit)) != 0)
		if (bitval == 1):
			return True
		else:
			return False

	def __twos_comp(self, val, bits):
		if((val & (1 << (bits - 1))) != 0):
			val = val - (1 << bits)
		return val

	def __setchannel(self, channel):
		# internal method for updating the config to the selected channel
		if channel != self.__currentchannel1:
			if channel == 1:
				self.__config1 = self.__updatebyte(self.__config1, 5, 0)
				self.__config1 = self.__updatebyte(self.__config1, 6, 0)
				self.__currentchannel1 = 1
			if channel == 2:
				self.__config1 = self.__updatebyte(self.__config1, 5, 1)
				self.__config1 = self.__updatebyte(self.__config1, 6, 0)
				self.__currentchannel1 = 2
			if channel == 3:
				self.__config1 = self.__updatebyte(self.__config1, 5, 0)
				self.__config1 = self.__updatebyte(self.__config1, 6, 1)
				self.__currentchannel1 = 3
			if channel == 4:
				self.__config1 = self.__updatebyte(self.__config1, 5, 1)
				self.__config1 = self.__updatebyte(self.__config1, 6, 1)
				self.__currentchannel1 = 4

		return

	# init object with i2caddress, default is 0x68, 0x69 for ADCoPi board
	def __init__(self, bus, address=0x68, rate=12):
		self._bus = bus
		self.__address = address
		self.set_bit_rate(rate)

	def read_voltage(self, channel):
		# returns the voltage from the selected adc channel - channels 1 to
		# 8
		raw = self.read_raw(channel)
		if (self.__signbit):
			return float(0.0)  # returned a negative voltage so return 0
		else:
			voltage = float(
				(raw * (self.__lsb / self.__pga)) * 2.471)
			return float(voltage)

	def read_raw(self, channel):
		# reads the raw value from the selected adc channel - channels 1 to 8
		h = 0
		l = 0
		m = 0
		s = 0

		# get the config and i2c address for the selected channel
		self.__setchannel(channel)
		if (channel < 5):            
			config = self.__config1
			address = self.__address
		else:
			config = self.__config2
			address = self.__address2
			
		# if the conversion mode is set to one-shot update the ready bit to 1
		if (self.__conversionmode == 0):
				config = self.__updatebyte(config, 7, 1)
				self._bus.write_byte(address, config)
				config = self.__updatebyte(config, 7, 0)
		# keep reading the adc data until the conversion result is ready
		while True:
			
			__adcreading = self._bus.read_i2c_block_data(address, config, 4)
			if self.__bitrate == 18:
				h = __adcreading[0]
				m = __adcreading[1]
				l = __adcreading[2]
				s = __adcreading[3]
			else:
				h = __adcreading[0]
				m = __adcreading[1]
				s = __adcreading[2]
			if self.__checkbit(s, 7) == 0:
				break

		self.__signbit = False
		t = 0.0
		# extract the returned bytes and combine in the correct order
		if self.__bitrate == 18:
			t = ((h & 0b00000011) << 16) | (m << 8) | l
			self.__signbit = bool(self.__checkbit(t, 17))
			if self.__signbit:
				t = self.__updatebyte(t, 17, 0)

		if self.__bitrate == 16:
			t = (h << 8) | m
			self.__signbit = bool(self.__checkbit(t, 15))
			if self.__signbit:
				t = self.__updatebyte(t, 15, 0)

		if self.__bitrate == 14:
			t = ((h & 0b00111111) << 8) | m
			self.__signbit = self.__checkbit(t, 13)
			if self.__signbit:
				t = self.__updatebyte(t, 13, 0)

		if self.__bitrate == 12:
			t = ((h & 0b00001111) << 8) | m
			self.__signbit = self.__checkbit(t, 11)
			if self.__signbit:
				t = self.__updatebyte(t, 11, 0)

		return t

	def set_pga(self, gain):
		"""
		PGA gain selection
		1 = 1x
		2 = 2x
		4 = 4x
		8 = 8x
		"""

		if gain == 1:
			self.__config1 = self.__updatebyte(self.__config1, 0, 0)
			self.__config1 = self.__updatebyte(self.__config1, 1, 0)
			self.__config2 = self.__updatebyte(self.__config2, 0, 0)
			self.__config2 = self.__updatebyte(self.__config2, 1, 0)
			self.__pga = 0.5
		if gain == 2:
			self.__config1 = self.__updatebyte(self.__config1, 0, 1)
			self.__config1 = self.__updatebyte(self.__config1, 1, 0)
			self.__config2 = self.__updatebyte(self.__config2, 0, 1)
			self.__config2 = self.__updatebyte(self.__config2, 1, 0)
			self.__pga = 1
		if gain == 4:
			self.__config1 = self.__updatebyte(self.__config1, 0, 0)
			self.__config1 = self.__updatebyte(self.__config1, 1, 1)
			self.__config2 = self.__updatebyte(self.__config2, 0, 0)
			self.__config2 = self.__updatebyte(self.__config2, 1, 1)
			self.__pga = 2
		if gain == 8:
			self.__config1 = self.__updatebyte(self.__config1, 0, 1)
			self.__config1 = self.__updatebyte(self.__config1, 1, 1)
			self.__config2 = self.__updatebyte(self.__config2, 0, 1)
			self.__config2 = self.__updatebyte(self.__config2, 1, 1)
			self.__pga = 4

		self._bus.write_byte(self.__address, self.__config1)
		#self._bus.write_byte(self.__address2, self.__config2)
		return

	def set_bit_rate(self, rate):
		"""
		sample rate and resolution
		12 = 12 bit (240SPS max)
		14 = 14 bit (60SPS max)
		16 = 16 bit (15SPS max)
		18 = 18 bit (3.75SPS max)
		"""

		if rate == 12:
			self.__config1 = self.__updatebyte(self.__config1, 2, 0)
			self.__config1 = self.__updatebyte(self.__config1, 3, 0)
			self.__config2 = self.__updatebyte(self.__config2, 2, 0)
			self.__config2 = self.__updatebyte(self.__config2, 3, 0)
			self.__bitrate = 12
			self.__lsb = 0.0005
		if rate == 14:
			self.__config1 = self.__updatebyte(self.__config1, 2, 1)
			self.__config1 = self.__updatebyte(self.__config1, 3, 0)
			self.__config2 = self.__updatebyte(self.__config2, 2, 1)
			self.__config2 = self.__updatebyte(self.__config2, 3, 0)
			self.__bitrate = 14
			self.__lsb = 0.000125
		if rate == 16:
			self.__config1 = self.__updatebyte(self.__config1, 2, 0)
			self.__config1 = self.__updatebyte(self.__config1, 3, 1)
			self.__config2 = self.__updatebyte(self.__config2, 2, 0)
			self.__config2 = self.__updatebyte(self.__config2, 3, 1)
			self.__bitrate = 16
			self.__lsb = 0.00003125
		if rate == 18:
			self.__config1 = self.__updatebyte(self.__config1, 2, 1)
			self.__config1 = self.__updatebyte(self.__config1, 3, 1)
			self.__config2 = self.__updatebyte(self.__config2, 2, 1)
			self.__config2 = self.__updatebyte(self.__config2, 3, 1)
			self.__bitrate = 18
			self.__lsb = 0.0000078125

		self._bus.write_byte(self.__address, self.__config1)
		return
	
	def set_conversion_mode(self, mode):
		"""
		conversion mode for adc
		0 = One shot conversion mode
		1 = Continuous conversion mode
		"""
		if (mode == 0):
			self.__config1 = self.__updatebyte(self.__config1, 4, 0)
			self.__config2 = self.__updatebyte(self.__config2, 4, 0)
			self.__conversionmode = 0
		if (mode == 1):
			self.__config1 = self.__updatebyte(self.__config1, 4, 1)
			self.__config2 = self.__updatebyte(self.__config2, 4, 1)
			self.__conversionmode = 1
		#self._bus.write_byte(self.__address, self.__config1)
		#self._bus.write_byte(self.__address2, self.__config2)    
		return




def temperatureControl(timeToRun):
	endTime = time()+timeToRun
	while (time() <= endTime):
		temperature = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
		#print(temperature)
		if temperature < desTemp:
			GPIO.output(1,True)
			GPIO.output(23,True)
			#print(temperature, "heating")
		else:
			GPIO.output(1,False)
			GPIO.output(23,False)

		sleep(0.5)
	GPIO.output(23,False)


def getRawData(sampleChan):
	
	#adc.set_pga(4)
	#adc.set_bit_rate(12)
	rawData = adc.read_voltage(sampleChan)*10000
	#sleep(0.1)
	#if (debug == True): print(sampleChan, str(int(rawData)))
	return rawData





def readChannel(sampleChan,sampleCycles):
	#threshold = 10
	#if (sampleCycles<threshold): sampleCycles=threshold*2
	sampleSum=sampledDataSum=0
	for i in range(sampleCycles): #get the rawdata for the number of times stored in "sampleCycles"
		#print("starting inner loop",i)
		sampledDataInner = getRawData(sampleChan) #get the actual rawdata
		#if (i == threshold): print("Start sampling")
		#if (i > (threshold-1)): 
		sampleSum += sampledDataInner #add the data up
			#print(i,sampleCycles)
		#if (debug == True): print("Channel ",i,  hex(sampleChan), sampledDataInner)
	sampledData = sampleSum/(sampleCycles)
	#print(sampledData)
	sampledDataSum +=sampledData
	return int(sampledData)

def startUp():
	global MCP3426_DEFAULT_ADDRESS, sampleTime, sampleCycles, oneRunOnly, debug, noBias
	cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
	process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, 
	stderr=subprocess.PIPE)
	my_pid, err = process.communicate()
	if len(my_pid.splitlines()) > 1:
		#print(len(my_pid.splitlines()))
		#print(my_pid)
		sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
		sys.exit(1)
	else:
		if (len(sys.argv)>=2):
			if (sys.argv[1] == "debug"):
				if len(sys.argv)<6:
					print("use parameters to customize: 'debug 1 200 true true' <- 1=seconds between samples, 200=cycles taken for 1 sample, true: single/continous debug, true=noBias measurement ")
					sampleTime = 1
					sampleCycles = 10
					oneRunOnly = "true"
					debug = True
					noBias = "true"
				else:
					sampleTime = int(sys.argv[2]) 
					sampleCycles = int(sys.argv[3])
					oneRunOnly = str(sys.argv[4])
					noBias = str(sys.argv[5])
					debug = True
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
		if (debug == True):
			print("ADC found at Address:", hex(MCP3426_DEFAULT_ADDRESS))

		GPIO.setmode(GPIO.BCM)
		GPIO.setup(POWERPIN, GPIO.OUT)
		GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP) 
		GPIO.setup(1,GPIO.OUT)
		GPIO.setup(23,GPIO.OUT)

			#for i in sys.argv:
			#	print(i)

		
startUp()

adc = ADCPi(bus, MCP3426_DEFAULT_ADDRESS, 14)

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
	
	try:
		bcmRefRaw=bcmRefBias=bcmSenBias=bcmRefFallback=bcmSenRef=bcmRefTmp=bcmRef=bcmRefOld=bcmRefNew=bcmSenNew=bcmSenOld=bcmATNold=BCngm3=BCngm3pos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=bcmTemperatureNew=bcmTemperatureOld=1
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
			print(today, now + " - happy debugging\nwhen device case is closed, sen & ref should be over 4000 and both bias close to 0")
		while(True):
			if (debug == False):
				with open("/home/pi/logs/" + logFileName, "a") as log:
					start = time()
					bcmSenTmp=bcmRefTmp=bcmSenBiasTmp=bcmRefBiasTmp=temperatureTmp=1
					threshold = 10
					bcmSenRaw = bcmRefRaw = 0
					start = time()
					bcmSenTmp=bcmRefTmp=bcmSenBiasTmp=bcmRefBiasTmp=temperatureTmp=1
					GPIO.output(POWERPIN, 1) 
					sleep(0.1)
					#if (debug == True): print("LED on, checking ATN, should be over 4000")
					for i in range(1,sampleCycles):
						a = readChannel(1,1)

						b =  readChannel(2,1)
						if (i>(threshold)):
							bcmSenRaw += a
							bcmRefRaw += b
							#print(i, a,b)
						if (sampleCycles/i == 10) or \
						(sampleCycles/i == 9) or \
						(sampleCycles/i == 8) or \
						(sampleCycles/i == 7) or \
						(sampleCycles/i == 6) or \
						(sampleCycles/i == 5) or \
						(sampleCycles/i == 4) or \
						(sampleCycles/i == 3) or \
						(sampleCycles/i == 2): 
							if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
								temperatureControl(5)
					bcmRefRaw=bcmRefRaw/(sampleCycles-threshold)
					bcmSenRaw=bcmSenRaw/(sampleCycles-threshold)
					#print(bcmSenRaw, bcmRefRaw)
					GPIO.output(POWERPIN, 0) 
					sleep(0.1)
					#if (noBias != "true"): 
					bcmSenBias = readChannel(1,1)
					bcmRefBias = readChannel(2,1)
					bcmSenNew=bcmSenRaw#-bcmSenBias
					bcmRefNew=bcmRefRaw#-bcmRefBias
					if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
						bcmTemperatureNew = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
					else:
						bcmTemperatureNew = 1
					if (bcmRefNew == 0): bcmRefNew = 1 #avoid later divide by 0; just for debug
					if (bcmSenNew == 0): bcmSenNew = 1#avoid later divide by 0; just for debug
					if (bcmRefNew < 100) and (bcmRefFallback == 1): #when there is no reference signal, use first sensor signal as reference fallback. suitable for stable environments
						bcmRefFallback = bcmSenNew
						flag=flag+"RefFallback-"
					if (bcmRefNew < 100) and (bcmRefFallback > 100):
						bcmRefNew = bcmRefFallback
						flag=flag+"noRef-"
					if (bcmRefFallback < bcmSenNew):
						bcmRefFallback=bcmRefNew
						flag=flag+"SetNewRef-"
					if (bcmSenNew < 1000): flag="checkLED-" 
					if (bcmSenOld==1): bcmSenOld = bcmSenNew
					if (bcmRefOld ==1):  bcmRefOld = bcmRefNew
					if (abs(bcmTemperatureOld-bcmTemperatureNew) > .5): flag = flag + "tempChange-"
					if (abs(bcmSenOld/bcmSenNew) < 0.9997):
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
					if (debug == True):
						print("sen; " + str(round(bcmSenRaw,3)) +"; ref; " + str(round(bcmRefRaw,3)) + "; senbias; " + str(round(bcmSenBias,3)) + "; refbias; "+ str(round(bcmRefBias,3)) + "; sampleTime; "+ str(round(delay,2)) )


				if (oneRunOnly == "true"): 
					print("cycle of " + str(sampleCycles) + " took " + str(round(delay,2)) + " seconds")
					print("exiting debug mode")
					GPIO.output(POWERPIN, 0)
					sys.exit(1)
				if (debug == False):
					with open('logs/log_current.csv','r') as csv_file:
						#os.system('clear')
						print(today, now, ver, logFileName)
						headers=[]
						with open('logs/log_current.csv','r') as csv_file:
							csv_reader = list(csv.reader(csv_file, delimiter=';'))
							print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
							print("Exit script with ctrl+c")


				if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
					if ((sampleTime)-delay <= 0):
						temperatureControl(sampleTime)
						#sleep(sampleTime)
					else:
						temperatureControl(sampleTime-delay)
						#sleep((sampleTime)-delay)
				else:
					if ((sampleTime)-delay <= 0):
						sleep(sampleTime)
					else:
						sleep((sampleTime)-delay)

				
			else: #debug mode
				print("debugging with sampleCycles, sampleTime:", sampleCycles, sampleTime)
				threshold = 10
				bcmSenRaw = bcmRefRaw = 0
				start = time()
				bcmSenTmp=bcmRefTmp=bcmSenBiasTmp=bcmRefBiasTmp=temperatureTmp=1
				GPIO.output(POWERPIN, 1) 
				sleep(0.1)
				#if (debug == True): print("LED on, checking ATN, should be over 4000")
				for i in range(sampleCycles):
					a = readChannel(1,1)

					b =  readChannel(2,1)
					if (i>(threshold-1)):
						bcmSenRaw += a
						bcmRefRaw += b
						#print(i, a,b)
				bcmRefRaw=bcmRefRaw/(sampleCycles-threshold)
				bcmSenRaw=bcmSenRaw/(sampleCycles-threshold)
				#print(bcmSenRaw, bcmRefRaw)
				GPIO.output(POWERPIN, 0) 
				sleep(0.1)
				#if (noBias != "true"): 
				bcmSenBias = readChannel(1,1)
				bcmRefBias = readChannel(2,1)
				bcmSenNew=bcmSenRaw#-bcmSenBias
				bcmRefNew=bcmRefRaw#-bcmRefBias
				bcmATNnew=round((numpy.log(bcmSenNew/bcmRefNew)*-100),5)
				bcRelativeLoad=round(((bcmATNnew-bcmATNold)/SG),5)
				BCngm3 = int(bcRelativeLoad * (spotArea / airVolume)) #bc nanograms per m3
				delay = time() - start
				bcmSenOld=bcmSenNew 
				bcmATNold=bcmATNnew
				print("sen; " + str(round(bcmSenRaw,3)) +"; ref; " + str(round(bcmRefRaw,3)) + "; senbias; " + str(round(bcmSenBias,3)) + "; refbias; "+ str(round(bcmRefBias,3)) + "; sampleTime; "+ str(round(delay,2)) +"; ATN; " + str(bcmATNnew))
				if (oneRunOnly == "true"): 
					print("cycle of " + str(sampleCycles) + " took " + str(round(delay,2)) + " seconds")
					print("exiting debug mode")
					GPIO.output(POWERPIN, 0)
					sys.exit(1)
				if ((sampleTime)-delay <= 0):
					temperatureControl(sampleTime)
					#sleep(sampleTime)
				else:
					temperatureControl(sampleTime-delay)
					#sleep((sampleTime)-delay)
					

	except KeyboardInterrupt: 
		#traceback.print_exc()
		print("\nWhen ready again, you may restart the script with 'python3 bcMeter.py' or just reboot the device itself")
		GPIO.output(POWERPIN, 0)
		pass

