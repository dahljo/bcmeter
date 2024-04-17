#!/usr/bin/env python3

import subprocess, sys
import RPi.GPIO as GPIO
import smbus
import logging
import os
import json
from datetime import datetime
import re
from bcMeter_shared import load_config_from_json, check_connection, update_interface_status, show_display, config, i2c
subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()
bcMeter_version = "0.9.915 2024-04-15"

# Create the log folder if it doesn't exist
log_folder = '/home/pi/maintenance_logs/'
log_entity = 'bcMeter'
os.makedirs(log_folder, exist_ok=True)

# Create a logger
logger = logging.getLogger(f'{log_entity}_log')
logger.setLevel(logging.DEBUG)  # Set the logging level to DEBUG


# Clear the handlers to avoid duplicate log messages
logger.handlers.clear()

# Configure the log file with a generic name
log_file_generic = f'{log_folder}{log_entity}.log'
if os.path.exists(log_file_generic):
	os.remove(log_file_generic)
handler_generic = logging.FileHandler(log_file_generic)
handler_generic.setLevel(logging.DEBUG)
formatter_generic = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
handler_generic.setFormatter(formatter_generic)

# Configure the log file with a timestamp in its filename
current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file_timestamped = f'{log_folder}{log_entity}_{current_datetime}.log'
handler_timestamped = logging.FileHandler(log_file_timestamped)
handler_timestamped.setLevel(logging.DEBUG)
formatter_timestamped = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
handler_timestamped.setFormatter(formatter_timestamped)

# Add both handlers to the logger
logger.addHandler(handler_generic)
logger.addHandler(handler_timestamped)

log_file_prefix = f'{log_entity}_'
log_files = [f for f in os.listdir(log_folder) if f.startswith(log_file_prefix) and f.endswith('.log')]
log_files.sort()
if len(log_files) > 11:
	files_to_remove = log_files[:len(log_files) - 11]
	for file_to_remove in files_to_remove:
		os.remove(os.path.join(log_folder, file_to_remove))

logger.debug("New bcMeter %s Session started", bcMeter_version)


bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1


# Set variables with defaults
disable_pump_control = config.get('disable_pump_control', False)
compair_upload = config.get('compair_upload', False)
get_location = config.get('get_location', False)
heating = config.get('heating', False)
pump_pwm_freq = int(config.get('pwm_freq', 20))
af_sensor_type = int(config.get('af_sensor_type', 1))
use_rgb_led = config.get('use_rgb_led', 0)
use_display = config.get('use_display', False)
led_brightness = int(config.get('led_brightness', 100))
airflow_sensor = config.get('airflow_sensor', False)
pump_dutycycle = int(config.get('pump_dutycycle', 20))
reverse_dutycycle = config.get('reverse_dutycycle', False)
sample_spot_diameter = float(config.get('sample_spot_diameter', 0.5))
is_ebcMeter = config.get('is_ebcMeter', False)
mail_logs_to = config.get('mail_logs_to', "")
send_log_by_mail = config.get('send_log_by_mail', False)
filter_status_mail = config.get('filter_status_mail', False)
sender_password = config.get('email_service_password', 'email_service_password')


sigma_air_880nm = 0.0000000777
run_once = "false"

#pwm for pump:
#GPIO.setup(12,GPIO.OUT)           # initialize as an output.

airflow_debug = False
debug = False 
sht40_i2c = None
online = False
output_to_terminal = False 

zero_airflow = 0

show_display(f"Initializing bcMeter", False, 0)
show_display(f"bcMeter {bcMeter_version}", False, 1)


import traceback, numpy, os, csv, typing, glob, signal, socket, importlib, smtplib
from tabulate import tabulate
from pathlib import Path
from time import sleep, strftime, time
from threading import Thread, Event
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


GPIO.setmode(GPIO.BCM)

devicename = socket.gethostname()

sample_spot_areasize=numpy.pi*(float(sample_spot_diameter)/2)**2 #area of spot in cm2 from bcmeter, diameter 0.50cm

os.chdir('/home/pi')

debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "debug") else False
calibration = True if (len(sys.argv) > 1) and (sys.argv[1] == "cal") else False
airflow_debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "airflow") else False



GPIO.setmode(GPIO.BCM)
MONOLED_PIN=1
GPIO.setup(MONOLED_PIN, GPIO.OUT)

if (use_rgb_led == 1):
# Set up GPIO pins
	R_PIN = 6
	G_PIN = 7
	B_PIN = 8
	GPIO.setup(R_PIN, GPIO.OUT)
	GPIO.setup(G_PIN, GPIO.OUT)
	GPIO.setup(B_PIN, GPIO.OUT)

	GPIO.output(R_PIN, 1)
	GPIO.output(G_PIN, 1)
	GPIO.output(B_PIN, 1)

infrared_led_control = 26

# /RDY bit definition
MCP342X_CONF_RDY = 0x80

# Conversion mode definitions
MCP342X_CONF_MODE_ONESHOT = 0x00
MCP342X_CONF_MODE_CONTINUOUS = 0x10
# Channel definitions
MCP342X_CONF_CHANNEL_1 = 0x00
MCP342X_CHANNEL_2 = 0x20
MCP342X_CHANNEL_3 = 0x40
MCP342X_CHANNEL_4 = 0x60

# Sample size definitions - these also affect the sampling rate
MCP342X_CONF_SIZE_12BIT = 0x00
MCP342X_CONF_SIZE_14BIT = 0x04
MCP342X_CONF_SIZE_16BIT = 0x08

# Programmable Gain definitions
MCP342X_CONF_GAIN_1X = 0x00
MCP342X_CONF_GAIN_2X = 0x01
MCP342X_CONF_GAIN_4X = 0x02
MCP342X_CONF_GAIN_8X = 0x03


ready = MCP342X_CONF_RDY
channel1 = MCP342X_CONF_CHANNEL_1
channel2 = MCP342X_CHANNEL_2
channel3 = MCP342X_CHANNEL_3
channel4 = MCP342X_CHANNEL_4

mode = MCP342X_CONF_MODE_CONTINUOUS
rate_12bit = MCP342X_CONF_SIZE_12BIT
rate_14bit = MCP342X_CONF_SIZE_14BIT
rate_16bit = MCP342X_CONF_SIZE_16BIT 
gain = MCP342X_CONF_GAIN_1X
rate = rate_14bit
VRef = 2.048

airflow_only = True if (len(sys.argv) > 1) and (sys.argv[1] == "airflow") else False
airflow_channel = channel1 if airflow_only is True and sys.argv[1] == "1" else channel3

sampling_thread = housekeeping_thread = set_PWM_dutycycle_thread = None
stop_event = Event()
change_blinking_pattern = Event()






def shutdown(reason):
	global reverse_dutycycle, housekeeping_thread, set_PWM_dutycycle_thread
	update_interface_status(0)
	print(f"Quitting: {reason}")
	show_display("Goodbye",0,True)
	if reason == "SIGINT":
		show_display("Turn off bcMeter",1,True)
	else:
		show_display(f"{reason}",1,True)

	show_display("",2,True)
	logger.debug(reason)
	try:
		if (reverse_dutycycle is False):
			pi.set_PWM_dutycycle(12, 0)
			sleep(0.5)
		else:
			pi.set_PWM_dutycycle(12, pump_PWM_range)
			sleep(0.5)
		if (airflow_only is False):
			#subprocess.Popen(["sudo", "killall", "pigpiod"]).communicate
			GPIO.output(infrared_led_control, False)
			GPIO.output(1,False)
			GPIO.output(23,False)
			#pump_duty.ChangeDutyCycle(0) 
			if (use_rgb_led == 1):
				# Turn off the LED
				GPIO.output(R_PIN, 1)
				GPIO.output(G_PIN, 1)
				GPIO.output(B_PIN, 1)
				GPIO.cleanup()
	except:
		pass
	stop_event.set()
	change_blinking_pattern.set()
	sleep(0.5)
	os.kill(os.getpid(), 15)
	sys.exit(1)


cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
my_pid, err = process.communicate()
if len(my_pid.splitlines()) > 1:
	sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
	shutdown("Already running")


update_interface_status(0)


files = os.listdir("/home/pi")

for file in files:
	file_path = os.path.join("/home/pi", file)
	os.chmod(file_path, 0o777) #dont try this at home

online = check_connection()
if (online):
	logger.debug("bcMeter is online!")
else:
	logger.debug("bcMeter is offline!")

try:
	import adafruit_sht4x
except ImportError:
	logger.debug("need to be online to install sht library first!")
	shutdown("Update needed for sht4x")

if (airflow_only is False):
	try:
		import pigpio
	except ImportError:
		logger.error("need to be online to install pigpio first!")
		shutdown("Update needed for pigpiod")

	try:
		subprocess.Popen(["sudo", "killall", "pigpiod"]).communicate
		sleep(0.5)
		subprocess.Popen(["sudo", "pigpiod","-l", "-s","2","-b","200","-f"]).communicate
		sleep(5)
		pi = pigpio.pi()
		pump_PWM_range=255
		pi.set_PWM_range(12, pump_PWM_range)
		pi.set_PWM_frequency(12, pump_pwm_freq)

		pi.set_PWM_range(infrared_led_control,255)
		pi.set_PWM_frequency(infrared_led_control, 1000)

		sleep(0.1)
		logger.debug("pigpiod started")
	except Exception as e:
		logger.error("pigpiod Error: %s ", e)

try:
	from scipy.ndimage import median_filter

except ImportError:
	logger.error("Update bcMeter!")
	shutdown("Update needed for scipy")



try:
	sht = adafruit_sht4x.SHT4x(i2c)
	sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
	temperature, relative_humidity = sht.measurements
	logger.debug("Temperature: %0.1f C" % temperature)
	logger.debug("Humidity: %0.1f %%" % relative_humidity)

	sht40_i2c = True
	ds18b20 = False
except Exception as e:
	sht40_i2c = False
	logger.error("Error: %s", e)



if sht40_i2c is False:
	class TemperatureSensor:
		RETRY_INTERVAL = 0.5
		RETRY_COUNT = 10
		device_file_name = None
		def __init__(self, channel: int):
			GPIO.setmode(GPIO.BCM)
			GPIO.setup(channel, GPIO.IN)
			GPIO.setup(1,GPIO.OUT)
			GPIO.setup(23,GPIO.OUT)
			
		#def __del__(self):
			#GPIO.cleanup()

		@staticmethod
		def read_device() -> typing.List[str]:
			device_file_name = None
			try:
				device_file_name = glob.glob('/sys/bus/w1/devices/28*')[0] + '/w1_slave'
			except Exception as e:
				logger.error(f"Temperature Sensor Error {e}")
			if device_file_name is not None:
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
				try:
					if len(lines) >= 2 and lines[0].endswith('YES'):
						match = re.search(r't=(\d{1,6})', lines[1])
						if match:
							return int(match.group(1), 10)
					sleep(self.RETRY_INTERVAL)
				except:
					pass

			logger.error(f"Cannot read temperature (tried {self.RETRY_COUNT} times with an interval of {self.RETRY_INTERVAL})")
	try:
		temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2) #read once to decide if we use ds18b20
		if temperature_current is not None:
			ds18b20 = True
			if debug:
				print("using ds18b20")
			logger.debug("Usind ds18b20 as temperature sensor")
		
			logger.debug("Temperature: %0.1f C" % temperature_current)

	except:
		print("no temperature sensor detected!")
		ds18b20 = False

	



def startUp():
	global MCP342X_DEFAULT_ADDRESS, debug, airflow_sensor_bias
	airflow_sensor_bias = -1
	read_airflow_sensor_bias = read_adc(MCP342X_DEFAULT_ADDRESS,1)

	
	if (debug):
		print("now pump should start")
	if (airflow_only is False):
		try:
			pi.set_PWM_dutycycle(infrared_led_control, led_brightness)
		except Exception as e:
			logger.error(f"{e}")
			print(e)
			shutdown("pigpiod error on startup")
		GPIO.setup(infrared_led_control, GPIO.OUT)
		GPIO.setup(1,GPIO.OUT)
		GPIO.setup(23,GPIO.OUT)


def handle_signal(signum, frame):
	if signum == signal.SIGUSR1:
		signal_handler()
	elif signum == signal.SIGINT:
		shutdown("SIGINT")

#Signalhandler
signal.signal(signal.SIGUSR1, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

def signal_handler():
	file_path = '/tmp/bcMeter_signalhandler'
	if os.path.isfile(file_path):
		with open(file_path, 'r+') as file:
			content = file.read().strip()
			logger.debug("signal handler: %s", content)
			if content == 'pump_test':
				pump_test()
			if content == 'identify':
				led_communication()
			file.seek(0)
			file.truncate()


def initialise(channel, rate):
	config = (ready|channel|mode|rate|gain)
	bus.write_byte(MCP342X_DEFAULT_ADDRESS, config)


def update_config_entry(config, key, value, description, value_type, parameter):
	if key not in config:
		config[key] = {}  # Ensure config[key] is a dictionary

	config[key] = {
		"value": value,
		"description": description,
		"type": value_type,
		"parameter": parameter
	}




def calibrate_sens_ref():
	global MCP342X_DEFAULT_ADDRESS
	calibration_data = read_adc(MCP342X_DEFAULT_ADDRESS, 10)
	raw_sens = calibration_data[0]
	raw_ref = calibration_data[1]
	print(f"sens={raw_sens}, ref={raw_ref}")
	if raw_sens < raw_ref:
		ref_correction = 1
		sens_correction = raw_ref / raw_sens
	else:
		sens_correction = 1
		ref_correction = raw_sens / raw_ref

	# Load existing configuration or create a new one if it doesn't exist
	try:
		with open("bcMeter_config.json", "r") as f:
			config = json.load(f)
	except FileNotFoundError:
		config = convert_config_to_json()

	# Update or create entries for correction factors
	config["sens_correction"] = sens_correction
	config["ref_correction"] = ref_correction

	update_config_entry(config, "sens_correction", sens_correction, "Sensor Correction Factor", "float", "administration")
	update_config_entry(config, "ref_correction", ref_correction, "Reference Correction Factor", "float", "administration")

	# Store the updated configuration back to the file
	with open("bcMeter_config.json", "w") as f:
		json.dump(config, f, indent=4)
	print(f"correction factor sens: {sens_correction}  and ref: {ref_correction} ")

def find_mcp_adress():
	global MCP342X_DEFAULT_ADDRESS
	for device in range(128):
		try:
			adc = bus.read_byte(device)
			if (hex(device) == "0x68"):
				MCP342X_DEFAULT_ADDRESS = 0x68
			elif (hex(device) == "0x6a"):
				MCP342X_DEFAULT_ADDRESS = 0x6a			
			elif (hex(device) == "0x6b"):
				MCP342X_DEFAULT_ADDRESS = 0x6b
			elif (hex(device) == "0x6c"):
				MCP342X_DEFAULT_ADDRESS = 0x6c
			elif (hex(device) == "0x6d"):
				MCP342X_DEFAULT_ADDRESS = 0x6d

		except: 
			pass
	try:
		logger.debug("ADC found at Address: %s", hex(MCP342X_DEFAULT_ADDRESS))
		return(MCP342X_DEFAULT_ADDRESS)
	except:
		shutdown("NO ADC")


def getconvert(channel, rate):
	if rate == rate_12bit:
		N = 12
		mcp_sps = 1/240
	elif rate == rate_14bit:
		N = 14
		mcp_sps = 1/60
	elif rate == rate_16bit:
		N = 16
		mcp_sps = 1/15
	sleep(mcp_sps*1.4) #better sleep more than less else buffer can be clogged and we get same values for different channels

	try:
		data = bus.read_i2c_block_data(MCP342X_DEFAULT_ADDRESS, channel, 2)
	except Exception as e:
		logger.error(f"Error reading ADC ({e})")
		shutdown(f"Error reading ADC ({e})")
	

	voltage = ((data[0] << 8) | data[1])
	if voltage >= 32768:
		voltage = 65536 - voltage
	voltage = (2 * VRef * voltage) / (2 ** N)
	return round(voltage,5)


def read_adc(mcp_i2c_address, sample_time):
	global MCP342X_DEFAULT_ADDRESS, airflow_only, airflow_sensor, airflow_channel, airflow_sensor_bias, calibration
	MCP342X_DEFAULT_ADDRESS = mcp_i2c_address
	airflow_sample_voltage = voltage_channel1 = voltage_channel3 = voltage_channel2 = sum_channel1 = sum_channel2 = sum_channel3 = 0
	average_channel1 = average_channel2 = average_channel3 = airflow_avg = 0
	airflow_sample_index = 1
	skipsampling = False
	i=j=0

	start = time()
	last_check_time = time()
	airflow_samples_to_take = 5	if sample_time < 20 else 20
	airflow_samples_to_take = 200 if airflow_only is True else airflow_samples_to_take
	check_interval = 1

	try:
		if (airflow_sensor_bias == -1):
			sens_bias_samples_to_take = 100
			initialise(airflow_channel, rate_12bit)
			airflow_sample_sum = 0
			while airflow_sample_index<=sens_bias_samples_to_take:
				airflow_sample_voltage = getconvert(airflow_channel, rate_12bit)
				airflow_sample_sum += airflow_sample_voltage
				airflow_sample_index+=1
			average_channel3 = airflow_sample_sum / sens_bias_samples_to_take
			airflow_sensor_bias = 0.5-average_channel3
			#airflow_sensor_bias=0
			print(f"airflow_sensor_bias is set to {airflow_sensor_bias}")
			logger.debug(f"airflow_sensor_bias is set to {airflow_sensor_bias}")
			skipsampling = True
	except NameError:
		pass


	while ((time()-start)<sample_time-0.25) and (skipsampling is False):
		if (airflow_only is False):
			x=time()
			
			initialise(channel1, rate)
			voltage_channel1 = getconvert(channel1, rate)
			sum_channel1 += voltage_channel1
			x=time()
			initialise(channel2, rate)
			voltage_channel2 = getconvert(channel2, rate)
			sum_channel2 += voltage_channel2
			x=time()
		if (debug):
			try:
				atn_current=round((numpy.log(voltage_channel1/voltage_channel2)*-100),5)
			except:
				pass
		if ((airflow_sensor is True) or (airflow_only is True)) and (i % 5 == 0):
			initialise(airflow_channel, rate_12bit)
			airflow_sample_sum = 0
			while airflow_sample_index<=airflow_samples_to_take:
				airflow_sample_voltage = getconvert(airflow_channel, rate_12bit)
				if (airflow_sample_voltage)==2.047:
					airflow_sample_voltage=5 #overweigh for reduction
				airflow_sample_sum += airflow_sample_voltage
				airflow_sample_index+=1
			average_channel3 = airflow_sample_sum / airflow_samples_to_take
			if (average_channel3 >= 2.047):
				logger.debug("airflow over sensor limit")
			sum_channel3+=average_channel3
			current_airflow=round(airflow_by_voltage(average_channel3, af_sensor_type),4)
			
			#blink_led(235)
			if (airflow_sensor is True):
				check_airflow(current_airflow)
				pass
			airflow_sample_index=1
			j+=1
			if airflow_only:

				cycle = (j%20)+1
				if cycle == 1:
					airflow_avg = 0
				airflow_avg += current_airflow

				print(f"{current_airflow} lpm, avg {round(airflow_avg/cycle,4)} lpm")

		i+=1
		if (debug is True):
			print(f"{i}, {round(sum_channel1/i,3)}, {round(sum_channel2/i,3)}, {round(average_channel3,3)}, current: {round(voltage_channel1,3)}, {round(voltage_channel2,3)}, {round(voltage_channel3,3)} ")
			pass
	if (skipsampling is False):
		average_channel3 = (sum_channel3 / j) if (airflow_sensor is True) else 0
		#'''	
		average_channel1 = sum_channel1 / i
		average_channel2 = sum_channel2 / i



	#average_channel3 = sum_channel3 / i
	#logger.debug(round(airflow_by_voltage(average_channel3, af_sensor_type),4),j)
	end=time()-start
	#logger.debug(i, "SEN: ", round(average_channel1,2), ", REF: ", round(average_channel2,4), ", AIRFLOW/VOLTAGE", round(airflow_by_voltage(average_channel3,af_sensor_type),4),"/",round(average_channel3,1))
	return average_channel1, average_channel2, average_channel3

def airflow_by_voltage(voltage,sensor_type):
	global airflow_sensor_bias
	pump_type=2
	if (airflow_only is True) or (debug is True):
		#print("\033c", end="", flush=True)
		#print(voltage, airflow_sensor_bias)
		pass
	# Define the table data (replace with your actual table) # valid for OMRON D6F P0001A1 with 100ml; due to limitations of ADC only 77ml max
	if (sensor_type == 0):
		table = {
			0.5: 0.000,
			2.5: 0.100
		}

	if (sensor_type == 1) :
	# Define the table data (replace with your actual table) # valid for OMRON D6F P0010A2 with 1000ml; due to limitations of ADC only 473ml max
		table = {
			0.50:0,
			0.72:0.05,
			0.82:0.077,
			1.08:0.155,
			1.13:0.24,
			1.77:0.5,
			1.90:0.6
		}
	# Check if the voltage is in the table
	if voltage in table:
		return table[voltage]
	else:
		# Interpolate the value if voltage is between two table entries
		voltages = sorted(table.keys())
		if voltage < voltages[0]:
			return 0
		if voltage > voltages[-1]:	
			return 2.1  # Voltage is outside the range of the table
		
		lower_voltage = max(v for v in voltages if v <= voltage)
		upper_voltage = min(v for v in voltages if v >= voltage)
		
		# Linear interpolation formula
		lower_value = table[lower_voltage]
		upper_value = table[upper_voltage]
		interpolated_value = lower_value + (voltage - lower_voltage) * (upper_value - lower_value) / (upper_voltage - lower_voltage)
		#if ((airflow_sensor == 1) and (interpolated_value > 0.47)) or ((airflow_sensor == 0 and interpolated_value>0.075)):
		#	interpolated_value = 9999

		return interpolated_value-airflow_sensor_bias



def get_sensor_values(MCP342X_DEFAULT_ADDRESS,sample_time):
	main_sensor_value = reference_sensor_value = airflow_sensor_value = 0
	sensor_values = read_adc(MCP342X_DEFAULT_ADDRESS, sample_time)
	main_sensor_value = sensor_values[0]
	reference_sensor_value = sensor_values[1]
	airflow_sensor_value = sensor_values[2]
	return main_sensor_value, reference_sensor_value, airflow_sensor_value

def set_pwm_dutycycle(pump_dutycycle, stop_event):
	global config
	reverse_dutycycle = config.get('reverse_dutycycle', False)
	try:
		pi.set_PWM_dutycycle(12, pump_dutycycle)
	except:
		if (debug):
			print("exception in pwm thread")
		if reverse_dutycycle is False:
			pi.set_PWM_dutycycle(12, 0)
		else:
			pi.set_PWM_dutycycle(12, pump_PWM_range)

	if (stop_event.is_set()):
		if (debug):
			print("exiting pwm thread")
		if reverse_dutycycle is False:
			pi.set_PWM_dutycycle(12, 0)
		else:
			pi.set_PWM_dutycycle(12, pump_PWM_range)


def check_airflow(current_mlpm):
	global pump_dutycycle, reverse_dutycycle, zero_airflow, airflow_only, airflow_debug, config
	desired_airflow_in_mlpm = float(config.get('airflow_per_minute', 0.1))
	disable_pump_control = True if airflow_only is True else False
	
	if(disable_pump_control is False):
		if (current_mlpm<0.002) and (desired_airflow_in_mlpm>0):
			zero_airflow+=1
			if (zero_airflow==50):
				logger.debug("resetting pump... no airflow measured")
				pump_test()
				sleep(1)
				zero_airflow=0
				return

		if (current_mlpm<desired_airflow_in_mlpm) and airflow_debug is False:

			if (reverse_dutycycle is True):
				if (pump_dutycycle<=0):
				
					logger.error("cannot reach desired airflow. please lower it")
					shutdown("NOMAXAIRFLOW")
					pump_dutycycle = pump_PWM_range
				else:
					pump_dutycycle-=1
			else:
				if (pump_dutycycle>=pump_PWM_range):
					pump_dutycycle = 0
					logger.error("cannot reach desired airflow. please lower it")
					shutdown("NOMAXAIRFLOW")

				else:
					pump_dutycycle+=1

		if (current_mlpm>desired_airflow_in_mlpm) and airflow_debug is False:
			if (reverse_dutycycle is True):
				pump_dutycycle+=1
			else:
				pump_dutycycle-=1
		if (pump_dutycycle<=0): pump_dutycycle=0
		if (pump_dutycycle>=pump_PWM_range): pump_dutycycle=pump_PWM_range
		set_PWM_dutycycle_thread = Thread(target=set_pwm_dutycycle, args=(pump_dutycycle,stop_event,))
		set_PWM_dutycycle_thread.start()

		show_display(str(round(current_mlpm*1000)) + "ml/min",2,False)
	if (debug is True):
		print(str(round(current_mlpm*1000)) + "ml/min",2,False)
		os.system('clear')
		print("current_mlpm", round(current_mlpm*1000,2), "desired_airflow_in_mlpm", round(desired_airflow_in_mlpm*1000,2), "pump_dutycycle", pump_dutycycle)
		pass


def pump_test():
	#logger.debug("Reset Pump")
	if (reverse_dutycycle is True):
		for cyclepart in range(1,11):
			pi.set_PWM_dutycycle(12, pump_PWM_range/cyclepart)
			sleep(0.12)
		pi.set_PWM_dutycycle(12, pump_PWM_range)

	else:
		for cyclepart in range(1,11):
			try:
				pi.set_PWM_dutycycle(12, cyclepart*10*(pump_PWM_range/100))
				sleep(0.12)
			except Exception as e:
				logger.error(e)
		pi.set_PWM_dutycycle(12, 0)
'''	pi.set_PWM_dutycycle(12, 0)
	sleep(5)
	pi.set_PWM_dutycycle(12, pump_PWM_range/2)
	sleep(5)
'''


def button_pressed():
	input_state = GPIO.input(16)
	if input_state == False:
		print(yo)
		pass

def createLog(log,header):
	Path("/home/pi/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile("/home/pi/logs/log_current.csv"):
		os.remove("/home/pi/logs/log_current.csv")
	if os.path.isfile("/home/pi/logs/compair_offline_log.log"):
		os.remove("/home/pi/logs/compair_offline_log.log")
	with open("/home/pi/logs/" + log, "a") as logfileArchive: #save this logfile for archive
		logfileArchive.write(header + "\n\n")
		os.chmod("/home/pi/logs/" + log, 0o777)
	with open("/home/pi/logs/log_current.csv", "a") as temporary_log: # temporary current logfile for web interface
		temporary_log.write(header + "\n\n")
	with open("/home/pi/logs/compair_offline_log.log", "w") as compair_offline_log: #save this logfile for archive
		compair_offline_log.write("timestamp;bcngm3;atn;bcmsen;bcmref;bcmtemperature;location;filter_status" + "\n\n")
		os.chmod("/home/pi/logs/compair_offline_log.log", 0o777)

def filter_values(log, kernel):
	file_path = output_file_path = log
	delimiter = ';'
	with open(file_path, 'r') as file:
		reader = csv.DictReader(file, delimiter=delimiter)
		data = list(reader)

	# Extract 'BCngm3' values
	bcngm3_values = []
	for row in data:
		try:
			value = float(row['BCngm3_unfiltered'])
		except ValueError:
			value = float('nan')
		bcngm3_values.append(value)

	# Apply median filter with a kernel size
	filtered_bcngm3_values = median_filter(bcngm3_values, size=kernel)

	# Update the 'BCngm3' values with the filtered values
	for i, row in enumerate(data):
		if not float('nan') == filtered_bcngm3_values[i]:
			row['BCngm3'] = str(int(filtered_bcngm3_values[i]))  # Convert back to string for writing to CSV

	# Write the modified data back to the CSV file
	with open(output_file_path, 'w', newline='') as output_file:
		fieldnames = reader.fieldnames
		writer = csv.DictWriter(output_file, fieldnames=fieldnames, delimiter=delimiter)
		writer.writeheader()
		writer.writerows(data)

def send_email(payload):
	# Email configuration
	smtp_server = "live.smtp.mailtrap.io"
	sender_email = f"{devicename} Status <mailtrap@bcmeter.org>"
	receiver_email = f"{mail_logs_to}"
	message = MIMEMultipart()
	message["From"] = sender_email
	message["To"] = receiver_email
	email_receiver_list = receiver_email.split(",")
	subject_prefix ="bcMeter Status Mail: "

	if (payload == "Filter"):
		logger.debug("Filter Change Mail sent")
		subject = subject_prefix + "Change filter!"
		body = "Hello dear human, please consider changing the filter paper the next time you're around, thank you!"


	if (payload == "Log"):
		logger.debug("Log Mail sent")
		subject =subject_prefix + "Log file"
		body = "Hello dear human, please find attached the log file"

		# Attach the file
		file_path = "/home/pi/logs/log_current.csv"
		current_time = datetime.now().strftime("%y%m%d_%H%M")
		send_file_as = f"{devicename}_{current_time}.csv"
		with open(file_path, "rb") as file:
			attachment = MIMEApplication(file.read(), Name=send_file_as)

		# Add header for the attachment
		attachment["Content-Disposition"] = f"attachment; filename={send_file_as}"
		message.attach(attachment)

	if (payload == "Pump"):
		logger.error("Error mail (Pump Malfcuntion) sent")
		subject =subject_prefix + "Pump Malfunction"
		body = "I do not register any airflow. Please check the connections and if the pump is working"

		# Attach the file
		file_path = "/home/pi/logs/log_current.csv"
		current_time = datetime.now().strftime("%y%m%d_%H%M")
		send_file_as = f"{devicename}_{current_time}.csv"
		with open(file_path, "rb") as file:
			attachment = MIMEApplication(file.read(), Name=send_file_as)

		# Add header for the attachment
		attachment["Content-Disposition"] = f"attachment; filename={send_file_as}"
		message.attach(attachment)


	# Email content
	message["Subject"] = subject
	message.attach(MIMEText(body, "plain"))

	# Establish a connection to the SMTP server
	for receiver in email_receiver_list:
		try:
			with smtplib.SMTP(smtp_server, 587) as server:
				server.starttls()
				server.login("api", sender_password)

				# Send the email
				server.sendmail(sender_email, receiver, message.as_string())

			logger.debug("Email to %s sent successfully!", receiver)
		except Exception as e:
			logger.error("Email alert: %s", e)

def apply_temperature_correction(BCngm3_unfiltered, temperature_current):
    # Constants obtained from polynomial regression; EXPERIMENTAL
    intercept = -15358.619
    temperature_coefficient = 1918.009
    temperature_squared_coefficient = -54.284
    
    # Calculate the correction factor based on temperature
    correction_factor = intercept + temperature_current * temperature_coefficient + temperature_current**2 * temperature_squared_coefficient
    
    # Apply the correction factor to BCngm3_unfiltered
    corrected_BCngm3_unfiltered = BCngm3_unfiltered * correction_factor
    
    return corrected_BCngm3_unfiltered


def bcmeter_main(stop_event):
	global housekeeping_thread, airflow_sensor, temperature_to_keep, airflow_sensor_bias, session_running_since, sender_password, ds18b20, config
	compair_offline_logging = False
	if (airflow_only is True):
		get_sensor_values(MCP342X_DEFAULT_ADDRESS, 86400*31)
		return
	last_email_time = time()
	first_value = True
	filter_status = samples_taken = sht_humidity=delay=airflow_sensor_value=reference_sensor_value=reference_sensor_bias=main_sensor_bias=bcmRefFallback=bcmSenRef=reference_sensor_value_current=main_sensor_value_current=main_sensor_value_last_run=attenuation_last_run=BCngm3_unfiltered=BCngm3_unfilteredpos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=temperature_current=bcm_temperature_last_run=attenuation_coeff=absorption_coeff=0
	notice = devicename
	volume_air_per_sample = absorb = main_sensor_value = attenuation = attenuation_current = 0.0000
	today = str(datetime.now().strftime("%y-%m-%d"))
	session_running_since = datetime.now()
	now = str(datetime.now().strftime("%H:%M:%S"))
	logFileName =(str(today) + "_" + str(now) + ".csv").replace(':','')
	header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3_unfiltered;BCngm3;Temperature;notice;main_sensor_bias;reference_sensor_bias;sampleDuration;sht_humidity;airflow"
	compair_offline_log_header="timestamp,bcngm3,atn,bcmsen,bcmref,bcmtemperature, location, filter_status"
	new_log_message="Started log " + str(today) + " " + str(now) + " " + str(bcMeter_version) + " " + str(logFileName)
	print(new_log_message)
	logger.debug(new_log_message)
	createLog(logFileName,header)
	update_interface_status(1)
	logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3_unfiltered) + ";"+ str(BCngm3_unfiltered) + ";" + str(temperature_current) + ";" + str(notice) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(sht_humidity) + ";" + str(volume_air_per_sample) 
	online = check_connection()

	if (compair_upload is True):
		import compair_frost_upload
	if debug is True:
		#print("Airflow Sensor bias: ",  airflow_sensor_bias)
		pass
	if airflow_only is False:
		#pump_test()
		housekeeping_thread = Thread(target=housekeeping, args=(stop_event,))
		housekeeping_thread.start()

	y = 0
	
	while(True):
		get_location = config.get('get_location', False)
		location = config.get('location', [0,0])
		device_specific_correction_factor = float(config.get('device_specific_correction_factor', 1))
		filter_scattering_factor = float(config.get('filter_scattering_factor', 1.39))
		mail_sending_interval = int(config.get('mail_sending_interval', 6))
		filter_status_mail = config.get('filter_status_mail', False)
		send_log_by_mail = config.get('send_log_by_mail', False)
		email_service_password = config.get('email_service_password', 'email_service_password')
		led_brightness = int(config.get('led_brightness', 100))
		sample_time = int(config.get('sample_time', 300))
		sens_correction = float(config.get('sens_correction',1))
		ref_correction = float(config.get('ref_correction',1))

		pi.set_PWM_dutycycle(infrared_led_control, led_brightness)
		start = time()
		if (samples_taken < 3) and (sample_time >60):
			sample_time=60
		samples_taken+=1
		sensor_values=get_sensor_values(MCP342X_DEFAULT_ADDRESS, sample_time)
		main_sensor_value = sensor_values[0]*sens_correction
		reference_sensor_value = sensor_values[1]*ref_correction
		if (airflow_sensor is True):
			airflow_sensor_value = sensor_values[2]
			airflow_per_minute = round(airflow_by_voltage(airflow_sensor_value,af_sensor_type),4)
			if (af_sensor_type==0) and (airflow_per_minute>0.075):
				logger.error("To high airflow!")
			if (af_sensor_type==1) and (airflow_per_minute>450):
				logger.error("To high airflow!")
			delay = time() - start
			#logger.debug("measurement took ", delay)
			volume_air_per_sample=(delay/60)*airflow_per_minute #liters of air between samples	
		else:
			airflow_per_minute = float(config.get('airflow_per_minute', 0.100))
			volume_air_per_sample=(sample_time/60)*airflow_per_minute #liters of air between samples
		main_sensor_value_current=main_sensor_value#-main_sensor_bias
		reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
		if (ds18b20 is True):
			try:
				temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
			except:
				pass
		elif (sht40_i2c is True):
			try:
				sensor = adafruit_sht4x.SHT4x(i2c)
				temperature_samples = []
				humidity_samples = []
				for i in range(20):
					temperature_samples.append(sensor.temperature)
					humidity_samples.append(sensor.relative_humidity)

				temperature_current = sum(temperature_samples) / 20
				sht_humidity = sum(humidity_samples) / 20		
			except:
				pass
		
		else:
			logger.debug("no temperature sensor detected")
			temperature_current = 1
		if (reference_sensor_value_current == 0): reference_sensor_value_current = 1 #avoid later divide by 0; just for debug
		if (main_sensor_value_current == 0): main_sensor_value_current = 1#avoid later divide by 0; just for debug
		filter_status = (
			5 if reference_sensor_value_current/main_sensor_value_current <= 2 else
			4 if 3 < reference_sensor_value_current/main_sensor_value_current > 2 else
			3 if 4 < reference_sensor_value_current/main_sensor_value_current > 3 else
			2 if 6 < reference_sensor_value_current/main_sensor_value_current > 4 else
			1 if 8 < reference_sensor_value_current/main_sensor_value_current > 6 else
			0 if 10 < reference_sensor_value_current/main_sensor_value_current > 8 else
			-1
		)

		current_time = time()
		mail_sending_interval_in_seconds = mail_sending_interval*60*60
		if (current_time - last_email_time >= mail_sending_interval_in_seconds) and (samples_taken>1):
			online=check_connection()
			if (send_log_by_mail is True) and (mail_logs_to != "your@email.address"):
				if (sender_password =="email_service_password"):
					logger.error("Contact jd@bcmeter.org for email service password. this is a antispam protection.")
					send_log_by_mail = False
					filter_status_mail = False
				if (online is True):
					if (send_log_by_mail is True):
						send_email("Log")
					if (filter_status_mail is True) and (filter_status<3):
						send_email(f"Filter Status {filter_status}")
				last_email_time = current_time
		if (abs(bcm_temperature_last_run-temperature_current) > .5): notice = notice + "tempChange-"
		attenuation_current=round((numpy.log(main_sensor_value_current/reference_sensor_value_current)*-100),5)
		atn_peak = False
		if (attenuation_last_run != 0) and (samples_taken>1):
			peakdetection = 1 - abs((attenuation_last_run/attenuation_current))
			if (peakdetection > 0.015) and (abs(attenuation_current- attenuation_last_run)>1.5):
				atn_peak = True
				notice = notice + "PEAK"
		if (attenuation_last_run == 0):
			attenuation_last_run = attenuation_current
		if (airflow_per_minute<0.005) and (airflow_sensor is True):
			if (mail_logs_to is not None):
				online=check_connection()
				logger.error("PUMP MALFUNCTION - STOPPING")
				if (online is True): 
					send_email("Pump")
			notice=notice+"NO_AF"
			change_blinking_pattern.set()

			blinking_thread = Thread(target=blink_led, args=(555,change_blinking_pattern))
			blinking_thread.start()
			sleep(5)
			shutdown("PUMP MALFUNCTION")

		attenuation_coeff = sample_spot_areasize*((attenuation_current-attenuation_last_run)/100)/volume_air_per_sample	
		absorption_coeff = attenuation_coeff/filter_scattering_factor

		device_specific_correction_factor = device_specific_correction_factor/1000 if is_ebcMeter else device_specific_correction_factor

		BCngm3_unfiltered = int((absorption_coeff / sigma_air_880nm)*device_specific_correction_factor) #bc nanograms per m3
		#if (temperature_current != 1.0000):
		#	BCngm3_unfiltered = apply_temperature_correction(BCngm3_unfiltered, temperature_current)
		#logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3_unfiltered) + ";" + str(round(temperature_current,1)) + ";" + str(notice) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(round(sht_humidity,1))
		if (samples_taken>3) and (airflow_only is False):
			with open("/home/pi/logs/" + logFileName, "a") as log:
				logString = f"{datetime.now().strftime('%d-%m-%y')};{datetime.now().strftime('%H:%M:%S')};{reference_sensor_value_current};{main_sensor_value_current};{attenuation_current};{attenuation_coeff};{BCngm3_unfiltered};{BCngm3_unfiltered};{round(temperature_current, 1)};{notice};{main_sensor_bias};{reference_sensor_bias};{round(delay, 1)};{round(sht_humidity, 1)};{round(airflow_per_minute,3)}"
				log.write(logString+"\n")

			kernel = 5
			if (samples_taken<kernel):
				kernel = samples_taken

			filter_values("/home/pi/logs/" + logFileName, kernel)

			log_file_path = "/home/pi/logs/" + logFileName
			column_index = 7  
			sum_for_avg = []

			with open(log_file_path, 'r') as log_file:
				for line in log_file:
					columns = line.strip().split(';')
					try:
						value = float(columns[7])  # Index 7 corresponds to the "BCngm3" column
						sum_for_avg.append(value)
					except (ValueError, IndexError):
						pass

			average = sum(sum_for_avg[-12:]) / min(12, len(sum_for_avg))

			if samples_taken > 15:
				show_display(f"{int(average)} ngm3/hr", False, 0)
			else:
				show_display(f"No AVG yet", False, 0)

			compair_offline_log_path = "/home/pi/logs/compair_offline_log.log"
			if (compair_upload is True):
				online=check_connection()	
				if (online is True):
					if (compair_offline_logging is True):
						compair_offline_logging = False
						if os.path.isfile(compair_offline_log_path):
							with open(compair_offline_log_path, 'r') as file:
								lines = file.readlines()
							if len(lines) > 1:
								importlib.reload(compair_frost_upload)
								compair_frost_upload.compair_frost_upload_offline_log(compair_offline_log_path)
								os.remove(compair_offline_log_path)
					compair_frost_upload.upload_sample(str(BCngm3_unfiltered),str(attenuation_current),str(main_sensor_value_current),str(reference_sensor_value_current),str(temperature_current), str(location), str(filter_status))
				else:
					logger.debug("saved sample to offline log file")
					compair_offline_logging = True
					with open(compair_offline_log_path, "a") as log:
						timestamp = compair_frost_upload.get_timestamp()
						logString = str(timestamp) + ";" + str(BCngm3_unfiltered) + ";" + str(attenuation_current) + ";" + str(main_sensor_value_current) + ";" + str(reference_sensor_value_current) + ";" + str(temperature_current) + ";" +  str(location) + ";" +  str(filter_status)
						log.write(logString+"\n")
						

			os.popen("cp /home/pi/logs/" + logFileName + " /home/pi/logs/log_current.csv")
		notice=""
		main_sensor_value_last_run=main_sensor_value_current 
		attenuation_last_run=attenuation_current
		bcm_temperature_last_run = temperature_current
		atn_peak = False
		online = False

		if (run_once == "true"): 
			logger.debug("cycle of " + str(sample_time) + " took " + str(round(delay,2)) + " seconds")
			GPIO.output(infrared_led_control, 0)
			shutdown("RUN ONCE")
		if (debug == False) and (reference_sensor_value_current !=0) and (main_sensor_value !=0) and (output_to_terminal is True): #output in terminal
			with open('logs/log_current.csv','r') as csv_file:
				os.system('clear')
				logger.debug(today, now, bcMeter_version, logFileName)
				headers=[]
				with open('logs/log_current.csv','r') as csv_file:
					csv_reader = list(csv.reader(csv_file, delimiter=';'))
					print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
					print("Exit script with ctrl+c")
		delay = time() - start
		y = time()
		if (debug is True):
			print("main loop took ",delay)
		if (sample_time-delay>=0):
			if debug is True:
				print("sleeping", sample_time-delay)
			sleep(sample_time-delay)
	
def check_service_running(service_name):
	try:
		result = subprocess.run(['systemctl', 'is-active', service_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		return result.stdout.decode().strip() == 'active'
	except subprocess.CalledProcessError:
		return False

def housekeeping(stop_event):
	global temperature_to_keep, session_running_since, ds18b20, airflow_debug, config
	temperature_to_keep = 35

	while (True):
		config = load_config_from_json()
		if (check_service_running("hostapd")):
			update_interface_status(3)
		else:
			update_interface_status(2)

		now = datetime.now()
		time_diff = now - session_running_since
		hours, remainder = divmod(time_diff.seconds, 3600)
		minutes, seconds = divmod(remainder, 60)
		hours = "0"+ str(hours) if hours<9 else hours
		minutes = "0"+str(minutes) if minutes<9 else minutes
		if (int(minutes) + int(hours) > 0):
			show_display("Running: "+ f"{hours}:{minutes}",1,False)
		else:
			show_display("Just started...", 1, False)

		if (airflow_sensor is False) or (airflow_debug is True):
			pump_dutycycle = int(config.get('pump_dutycycle', 20))
			try:
				if (pump_dutycycle >= 0 ) and (pump_dutycycle <= pump_PWM_range):
					pi.set_PWM_dutycycle(12,pump_dutycycle)
				else:
					logger.error(f"wrong pump_dutycycle {pump_dutycycle}")
					pi.set_PWM_dutycycle(12, 50)
			except Exception as e:
				print(e)
		#go on with temperature stabilization
		skipheat=False
		if (sht40_i2c is True):
			try:
				sensor = adafruit_sht4x.SHT4x(i2c)
				temperature_current = sensor.temperature
				sht_humidity  = sensor.relative_humidity
				#logger.debug(temperature_current, sht_humidity)
			except:
				temperature_current = 1
				skipheat=True	
		if (ds18b20 is True):
			try:
				temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
			except:
				pass

		heating = config.get('heating', False)
		#logger.debug("skip heating: " + str(skipheat) + " / heating: " + str(heating) + " / current temp: " + str(temperature_current) + " / temp to keep: " + str(temperature_to_keep))
		if (heating is True) and (skipheat is False):
			if ((temperature_to_keep - temperature_current) > 10):
				if (temperature_to_keep > 10):
					temperature_to_keep = temperature_current - 5
				GPIO.output(1,True)
				GPIO.output(23,True)
				#logger.debug("adjusted temperature to keep to  ", temperature_to_keep)
			
			elif temperature_current < (temperature_to_keep):
				GPIO.output(1,GPIO.HIGH)
				GPIO.output(23,GPIO.HIGH)
				#logger.debug(temperature_current, "current, heating up to", temperature_to_keep)
			elif (temperature_current > temperature_to_keep+0.2):
				if (temperature_to_keep <= 40):
					temperature_to_keep = round(temperature_current+0.5,1)
					GPIO.output(1,True)
					GPIO.output(23,True)
					#logger.debug("adjusted to", temperature_to_keep)
				else:
					GPIO.output(1,False)
					GPIO.output(23,False)
			elif ((temperature_to_keep - temperature_current)<0):
				GPIO.output(1,False)
				GPIO.output(23,False)
				#logger.debug("off because too hot", temperature_to_keep)
		sleep(5)


def blink_led(pattern, change_blinking_pattern):
	if debug:
		print(f"blinking pattern = {pattern}")
	while not change_blinking_pattern.is_set():
		R_PIN=G_PIN=B_PIN=1#remove for RGB Led; valid for mono LED

		red_blinks = pattern // 100
		green_blinks = (pattern - (red_blinks * 100)) // 10
		blue_blinks = pattern - red_blinks * 100 - green_blinks * 10

		blink_duration = 0.5 if pattern != 555 else 0.1

		for _ in range(red_blinks):
			GPIO.output(R_PIN, GPIO.HIGH)  # Change LOW to HIGH
			sleep(blink_duration)
			GPIO.output(R_PIN, GPIO.LOW)  # Change HIGH to LOW


		sleep(blink_duration * 2)

		for _ in range(green_blinks):
			GPIO.output(G_PIN, GPIO.HIGH)  # Change LOW to HIGH
			sleep(blink_duration)
			GPIO.output(G_PIN, GPIO.LOW)  # Change HIGH to LOW


		sleep(blink_duration * 2)

		for _ in range(blue_blinks):
			GPIO.output(B_PIN, GPIO.HIGH)  # Change LOW to HIGH
			sleep(blink_duration)
			GPIO.output(B_PIN, GPIO.LOW)  # Change HIGH to LOW

		sleep(blink_duration * 2)



def led_communication():

	# Blink each color
	for pin in [R_PIN, G_PIN, B_PIN]:
		GPIO.output(pin, GPIO.HIGH)  # Turn on the LED
		sleep(1)  # Wait for 1 second
		GPIO.output(pin, GPIO.LOW)  # Turn off the LED

	# Rainbow gradient
	colors = [[255, 0, 0], [255, 127, 0], [255, 255, 0], [0, 255, 0], [0, 0, 255], [75, 0, 130], [148, 0, 211]]
	duration = 5  # Total duration in seconds
	interval = 0.5  # Interval between colors in seconds
	steps = int(duration / (interval * len(colors)))

	for _ in range(steps):
		for color in colors:
			r, g, b = color
			GPIO.output(R_PIN, GPIO.HIGH if r > 0 else GPIO.LOW)
			GPIO.output(G_PIN, GPIO.HIGH if g > 0 else GPIO.LOW)
			GPIO.output(B_PIN, GPIO.HIGH if b > 0 else GPIO.LOW)
			sleep(interval)
			r = max(0, r - 5)
			g = max(0, g - 5)
			b = max(0, b - 5)
			color = [r, g, b]

	# Turn off the LED
	GPIO.output(R_PIN, 0)
	GPIO.output(G_PIN, 0)
	GPIO.output(B_PIN, 0)



if __name__ == '__main__':
	if (calibration):
		find_mcp_adress()
		pi.set_PWM_dutycycle(infrared_led_control, led_brightness)
		sleep(1)
		print("Starting calibration, will take about a minute")
		calibrate_sens_ref()
		shutdown("Calibration done")
	blinking_pattern = 111
	show_display(f"Sampling...", False, 0)
	try:
		blinking_thread = Thread(target=blink_led, args=(blinking_pattern,change_blinking_pattern))
		blinking_thread.start()
		if debug is True:
			print("Init")

		find_mcp_adress()
		pump_test()
		sleep(0.5)
		startUp()

		if debug:
			print("starting main thread")
		sampling_thread = Thread(target=bcmeter_main, args=(stop_event,))
		sampling_thread.start()
		if (airflow_only is False):
			if debug:
				print("starting housekeeping thread")
		if debug:
			print("everything set up and running")



	except KeyboardInterrupt: 
		shutdown("CTRL+C")

