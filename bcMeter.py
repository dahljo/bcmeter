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
import socket
import importlib
import bcMeterConf

bcMeter_version = "0.9.25 2023-03-11"

compair_upload = bcMeterConf.compair_upload 

if (compair_upload is True):
	import compair_data_upload

MCP3426_DEFAULT_ADDRESS = 0x68
i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1)
heating = False 
sigma_air_880nm = 0.0000000777
run_once = "false"
no_bias = "false"
devicename = socket.gethostname()
#pwm for pump:
GPIO.setup(12,GPIO.OUT)           # initialize as an output.
#using switch to adjust air volume
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)

output_to_terminal = False
online = False

pump_duty = GPIO.PWM(12,20)         #GPIO12 as PWM output, with 10Hz frequency

sample_spot_areasize=numpy.pi*(0.50/2)**2 #area of spot in cm2 from bcmeter, diameter 0.50cm
debug = False #no need to change here

POWERPIN = 26
BUTTON = 16

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
			sleep(self.RETRY_INTERVAL)
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







def sample_raw_values(sample_channel_number):
	

	raw_data = adc.read_voltage(sample_channel_number)*10000
	#sleep(0.1)
	if (debug == True): print(sample_channel_number, str(int(raw_data)))
	return raw_data





def read_channel_raw_value(sample_channel_number,sample_count):
	sampleSum=sampledDataSum=0
	for i in range(sample_count): #get the rawdata for the number of times stored in "sample_count"
		sampledDataInner = sample_raw_values(sample_channel_number) #get the actual rawdata
		sampleSum += sampledDataInner #add the data up
	sampledData = sampleSum/(sample_count)
	sampledDataSum +=sampledData
	return int(sampledData)

def get_location():
	import json
	import requests 
	my_ip = requests.get('https://api.ipify.org').text
	my_loc = requests.get('https://ipinfo.io/'+my_ip).text
	my_loc = json.loads(my_loc)
	my_lat =  float(my_loc['loc'].split(',')[0])
	my_lon = float(my_loc['loc'].split(',')[1])
	print(my_lat, my_lon)
	return [my_lat,my_lon]


def check_connection():
	current_time = 0
	while current_time < 5:
		try:
			socket.setdefaulttimeout(3)
			socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
			return True
		except Exception:
			current_time += 1
			sleep(1)


def startUp():
	global MCP3426_DEFAULT_ADDRESS, sample_time, sample_count, run_once, debug, no_bias
	cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
	process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, 
	stderr=subprocess.PIPE)
	my_pid, err = process.communicate()

	pump_duty.start(bcMeterConf.pump_dutycycle)     #generate PWM signal for pump
	if len(my_pid.splitlines()) > 1:
		sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
		sys.exit(1)
	else:
		if (len(sys.argv)>=2):
			if (sys.argv[1] == "debug"):
				sample_time = 1
				sample_count = 200
				run_once = "true"
				no_bias = "true"
				debug = True
		bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1
		for device in range(128):
			try:
				adc = bus.read_byte(device)
				if (hex(device) == "0x68"):
					MCP3426_DEFAULT_ADDRESS = 0x68
				elif (hex(device) == "0x6a"):
					MCP3426_DEFAULT_ADDRESS = 0x6a
				elif (hex(device) == "0x6d"):
					MCP3426_DEFAULT_ADDRESS = 0x6d
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

def get_sensor_values(sample_count):
	main_sensor_value = reference_sensor_value = 0
	threshold = sample_count / 10
	GPIO.output(POWERPIN, 1) 
	sleep(0.1)
	for i in range(1,sample_count):
		sen_raw = read_channel_raw_value(1,1)
		ref_raw =  read_channel_raw_value(2,1)
		if (i>(threshold)):
			main_sensor_value += sen_raw
			reference_sensor_value += ref_raw
			#print(i, sen_raw,ref_raw)
	reference_sensor_value=round(reference_sensor_value/(sample_count-threshold),0)
	main_sensor_value=round(main_sensor_value/(sample_count-threshold),0)
	GPIO.output(POWERPIN, 0) 
	if bcMeterConf.swap_channels is True:
		return reference_sensor_value, main_sensor_value
	return main_sensor_value, reference_sensor_value



adc = ADCPi(bus, MCP3426_DEFAULT_ADDRESS, 14)

def button_pressed():
	input_state = GPIO.input(16)
	if input_state == False:
		if (bcMeterConf.pump_dutycycle<=100) and (increase_duty  == True):
			bcMeterConf.pump_dutycycle+=5
		else:
			bcMeterConf.pump_dutycycle-=5
		if (bcMeterConf.pump_dutycycle == 100):
			increase_duty=False
		if (bcMeterConf.pump_dutycycle==0):
			increase_duty=True
		pump_duty.ChangeDutyCycle(bcMeterConf.pump_dutycycle)               #change duty cycle for varying the brightness of LED.
		time.sleep(0.1)
		print(bcMeterConf.pump_dutycycle)



def createLog(log,header):
	Path("/home/pi/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile("/home/pi/logs/log_current.csv"):
		os.remove("/home/pi/logs/log_current.csv")
	with open("/home/pi/logs/" + log, "a") as logfileArchive: #save this logfile for archive
		logfileArchive.write(header + "\n\n")
	with open("/home/pi/logs/log_current.csv", "a") as temporary_log: # temporary current logfile for web interface
		temporary_log.write(header + "\n\n")



def bcmeter_main():
	bcMeter_location = bcMeterConf.location
	filter_status = 0
	first_value = True
	samples_taken = 0
	delay=reference_sensor_value=reference_sensor_bias=main_sensor_bias=bcmRefFallback=bcmSenRef=reference_sensor_value_current=main_sensor_value_current=main_sensor_value_last_run=attenuation_last_run=BCngm3=BCngm3pos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=temperature_current=bcm_temperature_last_run=attenuation_coeff=absorption_coeff=0
	flag = ""
	calibrated = absorb = main_sensor_value = attenuation = attenuation_current = 0.0000
	today = str(datetime.now().strftime("%y-%m-%d"))
	now = str(datetime.now().strftime("%H:%M:%S"))
	logFileName =(str(today) + "_" + str(now) + ".csv").replace(':','')
	header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3;Temperature;flag;main_sensor_bias;reference_sensor_bias;sampleDuration"
	if (debug == False):
		print("Started new bcMeter log ", today, now, bcMeter_version, logFileName)
		createLog(logFileName,header)
		logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3) + ";" + str(temperature_current) + ";" + str(flag) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1))
	else:
		print(today, now + " - happy debugging\nwhen device case is closed, sen & ref should be over 4000 and both bias close to 0")

	internet_available = check_connection()
	if (internet_available  is True) and (bcMeterConf.get_location is True):
		location = get_location()
		if not 'location' in open('bcMeterConf.py').read():
			with open('bcMeterConf.py', 'a') as f:
				f.write("location=" + str(location) + "#Location of the bcMeter. Keep syntax exactly like that [lat,lon] ")
		else:
			with open('bcMeterConf.py', 'r') as f:
				lines = f.readlines()
			for i, line in enumerate(lines):
				if line.startswith('location'):
					lines[i] = "location=" + str(location) + "#Location of the bcMeter. Keep syntax exactly like that [lat,lon] "
			with open('bcMeterConf.py', 'w') as f:
				f.writelines(lines)
	print("using lat lon", bcMeter_location)

	while(True):
		if (debug == False):
			volume_air_per_minute=(bcMeterConf.sample_time/60)*bcMeterConf.airflow_per_minute #liters of air between samples	
			with open("/home/pi/logs/" + logFileName, "a") as log:
				samples_taken+=1
				start = time()
				threshold = bcMeterConf.sample_count/10
				sensor_values=get_sensor_values(bcMeterConf.sample_count)
				main_sensor_value = sensor_values[0]
				reference_sensor_value = sensor_values[1]
				main_sensor_bias = read_channel_raw_value(1,1)
				reference_sensor_bias = read_channel_raw_value(2,1)
				main_sensor_value_current=main_sensor_value#-main_sensor_bias
				reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
				if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
					temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
				else:
					temperature_current = 1
				if (reference_sensor_value_current == 0): reference_sensor_value_current = 1 #avoid later divide by 0; just for debug
				if (main_sensor_value_current == 0): main_sensor_value_current = 1#avoid later divide by 0; just for debug
				if (samples_taken == 1) and (reference_sensor_value_current > 8000):
					if ((main_sensor_value_current) > 8000):
						filter_status = 5
					elif (6000 < main_sensor_value_current < 8000):
						filter_status = 4
					elif (3000 < main_sensor_value_current < 6000):
						filter_status = 3
					elif (2000 < main_sensor_value_current < 3000):
						filter_status = 2
					elif (1000 < main_sensor_value_current < 2000):
						filter_status = 1
					elif (0000 < main_sensor_value_current < 1000):
						filter_status = 0
				if (abs(bcm_temperature_last_run-temperature_current) > .5): flag = flag + "tempChange-"
				attenuation_current=round((numpy.log(main_sensor_value_current/reference_sensor_value_current)*-100),5)
				atn_peak = False
				if (attenuation_last_run != 0) and (samples_taken>1):
					peakdetection = 1 - abs((attenuation_last_run/attenuation_current))
					if (peakdetection > 0.015) and (abs(attenuation_current- attenuation_last_run)>1.5):
						atn_peak = True
						flag = flag + "PEAK"
				if (attenuation_last_run == 0):
					attenuation_last_run = attenuation_current
				delay = time() - start
				if (samples_taken<3):
					volume_air_per_minute=(delay/60)*bcMeterConf.airflow_per_minute #liters of air between samples	
				else:
					volume_air_per_minute=(bcMeterConf.sample_time/60)*bcMeterConf.airflow_per_minute #liters of air between samples	
				if (atn_peak is False):
					attenuation_coeff = sample_spot_areasize*((attenuation_current-attenuation_last_run)/100)/volume_air_per_minute	
				else:
					attenuation_coeff = 0
				absorption_coeff = attenuation_coeff/bcMeterConf.filter_scattering_factor
				BCngm3 = int((absorption_coeff / sigma_air_880nm)*bcMeterConf.device_specific_correction_factor) #bc nanograms per m3
				logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3) + ";" + str(temperature_current) + ";" + str(flag) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1))
				log.write(logString+"\n")
				online = check_connection()
				if (compair_upload == True) and (samples_taken > 2) and (online is True):
					#print("uploading to CompAir Cloud",BCngm3,attenuation_current,main_sensor_value_current,reference_sensor_value_current,temperature_current, bcMeter_location, filter_status)
					compair_data_upload.upload_sample(BCngm3,attenuation_current,main_sensor_value_current,reference_sensor_value_current,temperature_current, bcMeter_location, filter_status)
				flag=""
				main_sensor_value_last_run=main_sensor_value_current 
				attenuation_last_run=attenuation_current
				bcm_temperature_last_run = temperature_current
				atn_peak = False
				online = False
				flag=""
				if (debug == True):
					print("sen; " + str(round(main_sensor_value,3)) +"; ref; " + str(round(reference_sensor_value,3)) + "; senbias; " + str(round(main_sensor_bias,3)) + "; refbias; "+ str(round(reference_sensor_bias,3)) + "; sample_time; "+ str(round(delay,2)) )
			if (samples_taken == 2):
				lines = open("/home/pi/logs/" + logFileName).readlines()
				lines.pop(2)
				with open("/home/pi/logs/" + logFileName, "w") as f:
					#write each line back to the file
					for line in lines:
						f.write(line)
			os.popen("cp /home/pi/logs/" + logFileName + " /home/pi/logs/log_current.csv")

			if (run_once == "true"): 
				print("cycle of " + str(sample_count) + " took " + str(round(delay,2)) + " seconds")
				print("exiting debug mode")
				GPIO.output(POWERPIN, 0)
				sys.exit(1)
			if (debug == False) and (reference_sensor_value_current !=0) and (main_sensor_value !=0) and (output_to_terminal is True): #output in terminal
				with open('logs/log_current.csv','r') as csv_file:
					os.system('clear')
					print(today, now, bcMeter_version, logFileName)
					headers=[]
					with open('logs/log_current.csv','r') as csv_file:
						csv_reader = list(csv.reader(csv_file, delimiter=';'))
						print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
						print("Exit script with ctrl+c")
			if ((bcMeterConf.sample_time)-delay <= 0):
				sleep(bcMeterConf.sample_time)
			else:
				sleep((bcMeterConf.sample_time)-delay)

			
		else: #debug mode
			print("debugging with sample_count, sample_time:", sample_count, sample_time)
			threshold = 10
			start = time()
			sensor_values=get_sensor_values(sample_count)
			main_sensor_value = sensor_values[0]
			reference_sensor_value = sensor_values[1]
			main_sensor_bias = read_channel_raw_value(1,1)
			reference_sensor_bias = read_channel_raw_value(2,1)
			main_sensor_value_current=main_sensor_value#-main_sensor_bias
			reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
			delay = time() - start
			main_sensor_value_last_run=main_sensor_value_current 
			attenuation_last_run=attenuation_current
			print("sen; " + str(round(main_sensor_value,3)) +"; ref; " + str(round(reference_sensor_value,3)) + "; senbias; " + str(round(main_sensor_bias,3)) + "; refbias; "+ str(round(reference_sensor_bias,3)) + "; sample_time; "+ str(round(delay,2)) +"; ATN; " + str(attenuation_current))
			if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
				temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
				print("measured temperature:", temperature_current)				
			else:
				print("no temperature sensor detected")
				temperature_current = 1
			if (run_once == "true"): 
				print("cycle of " + str(sample_count) + " took " + str(round(delay,2)) + " seconds")
				print("exiting debug mode")
				GPIO.output(POWERPIN, False)
				GPIO.output(1,False)
				GPIO.output(23,False)
				sys.exit(1)


def keep_the_temperature():			
	if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
		temperature_to_keep = 35
		while (True):
			#sneak in pwm adjustment for pump because we dont want do have on thread just for that
			importlib.reload(bcMeterConf)
			pump_duty.ChangeDutyCycle(bcMeterConf.pump_dutycycle) 
			#keep going with the temperature 
			temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
			if ((temperature_to_keep - temperature_current) > 10):
				if (temperature_to_keep > 10):
					temperature_to_keep = temperature_current - 5
				GPIO.output(1,True)
				GPIO.output(23,True)
				#print("adjusted temperature to keep to  ", temperature_to_keep)
			
			if temperature_current < temperature_to_keep:
				GPIO.output(1,True)
				GPIO.output(23,True)
				#print(temperature, "current, heating up to", temperature_to_keep)

			if (temperature_current >(temperature_to_keep+1)):
				if (temperature_to_keep < 40):
					temperature_to_keep = temperature_current+1
				GPIO.output(1,False)
				GPIO.output(23,False)
				#print("adjusted temperature to keep to ", temperature_to_keep)

			if ((temperature_to_keep - temperature_current)<0):
				GPIO.output(1,False)
				GPIO.output(23,False)

			sleep(5)




if __name__ == '__main__':
	try:
		sampling_thread = Thread(target=bcmeter_main)
		heating_thread = Thread(target=keep_the_temperature)

		sampling_thread.start()
		if (debug is False):
			heating_thread.start()

	except KeyboardInterrupt: 
		print("\nWhen ready again, you may restart the script with 'python3 bcMeter.py' or just reboot the device itself")
		GPIO.output(POWERPIN, False)
		GPIO.output(1,False)
		GPIO.output(23,False)
		pump_duty.ChangeDutyCycle(0) 
		sleep(0.1) #sometimes the dutycycle is not transmitted early

		pass

