#!/usr/bin/env python3

import subprocess, sys
import RPi.GPIO as GPIO
import smbus
import os
import json
from datetime import datetime
import re
from collections import deque
from bcMeter_shared import config_json_handler, check_connection, manage_bcmeter_status, show_display, config, i2c, setup_logging, run_command, send_email, update_config
import pigpio
#os.system('clear')
bcMeter_version = "0.9.938 2025-03-14"

base_dir = '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

logger = setup_logging('bcMeter')
logger.debug(config)
logger.debug(f"bcMeter Version {bcMeter_version}")

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
sample_spot_diameter = float(str(config.get('sample_spot_diameter', 0.5)).replace(',', '.'))
is_ebcMeter = config.get('is_ebcMeter', False)
mail_logs_to = config.get('mail_logs_to', "")
send_log_by_mail = config.get('send_log_by_mail', False)
filter_status_mail = config.get('filter_status_mail', False)
disable_led = config.get('disable_led', False)
airflow_type = int(config.get('af_sensor_type', 1))
TWELVEVOLT_ENABLE = config.get('TWELVEVOLT_ENABLE', False)

if airflow_type == 9:
	print("configuring for honeywell airflow sensor")
	from bcMeter_shared import read_airflow_ml



cooling = False
temperature_to_keep = 35 if cooling is False else 0
override_airflow = False


sigma_air_880nm = 0.0000000777
run_once = "false"

airflow_debug = False
debug = False 
sht40_i2c = None
online = False
output_to_terminal = False 

zero_airflow = 0

show_display(f"Initializing bcMeter", False, 0)
show_display(f"bcMeter {bcMeter_version}", False, 1)


import traceback, numpy, os, csv, typing, glob, signal, socket, importlib
from tabulate import tabulate
from pathlib import Path
from time import sleep, strftime, time
from threading import Thread, Event

GPIO.setmode(GPIO.BCM)

devicename = socket.gethostname()

sample_spot_areasize=numpy.pi*(float(sample_spot_diameter)/2)**2 

os.chdir(base_dir)

debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "debug") else False
calibration = True if (len(sys.argv) > 1) and (sys.argv[1] == "cal") else False
airflow_debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "airflow") else False


GPIO.setmode(GPIO.BCM)
MONOLED_PIN=1
PUMP_PIN = 12
TWELVEVOLT_PIN = 27
INFRARED_LED_PIN = 26
GPIO.setup(MONOLED_PIN, GPIO.OUT)

if TWELVEVOLT_ENABLE:
	GPIO.setup(TWELVEVOLT_PIN, GPIO.OUT)
#update_config(variable='TWELVEVOLT_ENABLE', value=False)
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


# Pump and LED PWM configurations
PUMP_PWM_RANGE = 100 if reverse_dutycycle else 255
PUMP_PWM_FREQ = int(config.get('pwm_freq', 20))  # Configured pump PWM frequency

LED_PWM_RANGE = 255
LED_PWM_FREQ = 1000  



def shutdown(reason, shutdown_code=None):
	global reverse_dutycycle, housekeeping_thread, set_PWM_dutycycle_thread, sampling_thread
	
	# Set stop event to signal all threads to exit
	stop_event.set()
	change_blinking_pattern.set()
	
	# Log the shutdown reason
	print(f"Quitting: {reason}")
	logger.debug(f"Shutdown initiated: {reason}")
	
	if shutdown_code is None:
		shutdown_code = 5
	
	# Turn off 12V if configured
	if GPIO.gpio_function(TWELVEVOLT_PIN) == GPIO.OUT:
		GPIO.output(TWELVEVOLT_PIN, 0)
	
	# Update status
	manage_bcmeter_status(action='set', bcMeter_status=shutdown_code)
	
	# Update display
	show_display("Goodbye", 0, True)
	if reason == "SIGINT" or reason == "SIGTERM":
		show_display("Turn off bcMeter", 1, True)
	else:
		show_display(f"{reason}", 1, True)
	show_display("", 2, True)
	
	# Stop pigpio cleanly if it's running
	if reason != "Already running":
		try:
			# Only stop pigpio if it's connected
			if 'pi' in globals() and pi.connected:
				# Set pump to safe state before stopping
				if reverse_dutycycle is False:
					try:
						pi.set_PWM_dutycycle(PUMP_PIN, 0)
					except:
						pass
				else:
					try:
						pi.set_PWM_dutycycle(PUMP_PIN, PUMP_PWM_RANGE)
					except:
						pass
				
				# Stop pigpio connection
				pi.stop()
				logger.debug("pigpio connection stopped")
				
				# Kill the daemon with a timeout
				try:
					subprocess.run(["sudo", "killall", "pigpiod"], 
								 check=False, timeout=2)
					logger.debug("pigpiod process terminated")
				except subprocess.TimeoutExpired:
					logger.warning("Timeout while trying to kill pigpiod")
		except Exception as e:
			logger.error(f"Error stopping pigpio: {e}")
	
	# Get current thread ID to avoid joining the thread that's executing this function
	from threading import current_thread
	current_thread_id = current_thread().ident
	
	# Prepare list of threads to join
	threads_to_join = []
	if sampling_thread and sampling_thread.is_alive() and sampling_thread.ident != current_thread_id:
		threads_to_join.append(sampling_thread)
	if housekeeping_thread and housekeeping_thread.is_alive() and housekeeping_thread.ident != current_thread_id:
		threads_to_join.append(housekeeping_thread)
	if set_PWM_dutycycle_thread and set_PWM_dutycycle_thread.is_alive() and set_PWM_dutycycle_thread.ident != current_thread_id:
		threads_to_join.append(set_PWM_dutycycle_thread)
	
	# Join threads with timeout
	for thread in threads_to_join:
		thread.join(timeout=1)
		if thread.is_alive():
			logger.warning(f"Thread {thread.name} didn't terminate within timeout")
	
	# Clean up GPIO resources
	try:
		GPIO.cleanup()
		logger.debug("GPIO cleanup completed")
	except Exception as e:
		logger.error(f"Error during GPIO cleanup: {e}")
	
	# Exit the program
	sys.exit(1)

cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
my_pid, err = process.communicate()
if len(my_pid.splitlines()) > 1:
	sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
	shutdown("Already running")


if manage_bcmeter_status(parameter='bcMeter_status') !=5:
	manage_bcmeter_status(action='set', bcMeter_status=0)

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


def initialize_pwm_control():
	"""Initialize PWM control and verify connection"""
	global pi
	
	if airflow_only:
		return True
		
	try:
		# Check if pigpiod is already running
		pigpiod_running = subprocess.run(["pgrep", "-x", "pigpiod"], 
									 stdout=subprocess.PIPE).returncode == 0
		
		# Only try to kill it if it's running
		if pigpiod_running:
			try:
				subprocess.run(["sudo", "killall", "pigpiod"], check=False)
				sleep(2)  # Give it time to fully stop
			except:
				pass
			
		# Start pigpiod with additional options for stability
		os.system("sudo pigpiod -l -m")  # Add logging and minimize CPU usage
		
		# Give it time to start
		sleep(3)
		
		# Verify daemon is responsive
		retry_count = 0
		while retry_count < 5:
			try:
				pi = pigpio.pi()
				if pi.connected:
					break
				retry_count += 1
				sleep(2)
			except:
				retry_count += 1
				sleep(2)
		
		if not pi.connected:
			raise Exception("Failed to connect to pigpiod after multiple attempts")
			
		# Configure PWM pins
		pi.set_mode(PUMP_PIN, pigpio.OUTPUT)
		pi.set_mode(INFRARED_LED_PIN, pigpio.OUTPUT)
		pi.set_PWM_range(PUMP_PIN, PUMP_PWM_RANGE)
		pi.set_PWM_frequency(PUMP_PIN, PUMP_PWM_FREQ)
		pi.set_PWM_range(INFRARED_LED_PIN, LED_PWM_RANGE)
		pi.set_PWM_frequency(INFRARED_LED_PIN, LED_PWM_FREQ)
		
		sleep(0.5)  # Longer delay to ensure settings are applied
				
		return True
		
	except Exception as e:
		logger.error(f"Error initializing PWM control: {e}")
		return False



if not airflow_only:
	try:
		if not initialize_pwm_control():
			logger.error("Failed to initialize PWM control")
			shutdown("Pigpiod Error. Reboot and retry.", 6)
		if debug:
			print("pigpiod initialized")
	except Exception as e:
		logger.error("Error: %s", e)
		shutdown("PWM initialization failed", 6)

try:
	from scipy.ndimage import median_filter

except ImportError:
	logger.error("Update bcMeter!")
	shutdown("Update needed for scipy",6)



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

		@staticmethod
		def read_device() -> typing.List[str]:
			device_file_name = None
			try:
				device_file_name = glob.glob('/sys/bus/w1/devices/28*')[0] + '/w1_slave'
			except Exception as e:
				logger.error(f"Temperature Sensor DS18b20 Error {e}")
			if device_file_name is not None:
				with open(device_file_name, 'r') as fp:
					return [line.strip() for line in fp.readlines()]
		def get_temperature_in_milli_celsius(self) -> int:
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
			logger.debug("Using ds18b20 as temperature sensor")
		
			logger.debug("Temperature: %0.1f C" % temperature_current)

	except:
		print("no temperature sensor detected!")
		ds18b20 = False

def handle_signal(signum, frame):
	if signum == signal.SIGUSR1:
		signal_handler()
	elif signum == signal.SIGINT:
		shutdown("SIGINT")
	elif signum == signal.SIGTERM:
		shutdown("SIGTERM")  # Handle systemctl stop		

#Signalhandler
signal.signal(signal.SIGUSR1, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

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


def initialise(channel, rate, max_retries=3):
	global bus
	config = (ready|channel|mode|rate|gain)
	retry_count = 0
	backoff_time = 0.1
	while retry_count < max_retries:
		try:
			bus.write_byte(MCP342X_DEFAULT_ADDRESS, config)
			return True  # Successfully initialized
		except OSError as e:
			# Specific handling for I/O errors like [Errno 5]
			retry_count += 1
			error_msg = f"I2C error during initialization (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			
			if retry_count < max_retries:
				# Try resetting the I2C bus
				try:
					bus.close()
					sleep(backoff_time)
					bus = smbus.SMBus(1)
				except:
					pass
				
				sleep(backoff_time)
				backoff_time *= 2  # Exponential backoff
			else:
				logger.error(f"Failed to initialize ADC after {max_retries} attempts: {e}")
				# Don't shut down immediately, return failure instead
				return False
		except Exception as e:
			# Handle other exceptions
			retry_count += 1
			error_msg = f"Error during initialization (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			
			if retry_count < max_retries:
				sleep(backoff_time)
				backoff_time *= 2
			else:
				logger.error(f"Failed to initialize ADC: {e}")
				# Don't shut down immediately, return failure instead
				return False
	
	return False  # Failed to initialize

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
	raw_sens, raw_ref = calibration_data[0], calibration_data[1]
	print(f"sens={raw_sens}, ref={raw_ref}")
	
	if (raw_sens > 1.99) or (raw_ref > 1.99):
		logger.error("LED to bright! Please check if filter paper present or dim the LED brightness!")
		shutdown("LED brightness",6)
	
	if (raw_sens < 0.1) or (raw_ref < 0.1):
		logger.error("LED to dim!! Please check LED and sensor connection and orientation!")
		shutdown("LED to dim",6)
		

	sens_correction = 1 if raw_sens >= raw_ref else raw_ref / raw_sens
	ref_correction = 1 if raw_ref >= raw_sens else raw_sens / raw_ref 


	try:
		with open("bcMeter_config.json", "r") as f:
			config = json.load(f)
	except FileNotFoundError:
		config = convert_config_to_json()

	config["sens_correction"] = sens_correction
	config["ref_correction"] = ref_correction
	
	update_config_entry(config, "sens_correction", sens_correction, "Sensor Correction Factor", "float", "administration")
	update_config_entry(config, "ref_correction", ref_correction, "Reference Correction Factor", "float", "administration")
	
	# Set calibration time
	calibration_time = datetime.now().strftime("%y%m%d_%H%M%S")
	manage_bcmeter_status(action='set', calibration_time=calibration_time)
	print(f"set calibration time to {calibration_time}")

	filter_status_quotient = (raw_sens*sens_correction) / (raw_ref*ref_correction)
	if filter_status_quotient == 1:
		manage_bcmeter_status(action='set', filter_status=5)
		print(f"set filter status to 5")
	else:
		logger.debug("Filter status quotient not 1 after calibration")
		print("Filter status quotient not 1 after calibration")
	# Store the updated configuration back to the file
	with open("bcMeter_config.json", "w") as f:
		json.dump(config, f, indent=4)
	print(f"correction factor sens: {sens_correction}  and ref: {ref_correction} ")
	print (f" using {sens_correction*raw_sens} and {ref_correction*raw_ref} as default now")

def find_mcp_adress():
	global MCP342X_DEFAULT_ADDRESS
	try:
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
		
		if 'MCP342X_DEFAULT_ADDRESS' in globals():
			logger.debug("ADC found at Address: %s", hex(MCP342X_DEFAULT_ADDRESS))
			return(MCP342X_DEFAULT_ADDRESS)
		else:
			raise Exception("No ADC found on I2C bus")
	except Exception as e:
		logger.error(f"I2C bus error while scanning for ADC: {e}")
		shutdown(f"I2C bus error: {e}", 6)

exception_timestamps = deque(maxlen=10)  # Keep track of the last 10 errors
shutdown_threshold = 2  # Number of errors allowed per minute


def getconvert(channel, rate):
	global bus
	"""Get ADC conversion with improved error handling and retries"""
	if rate == rate_12bit:
		N = 12
		mcp_sps = 1 / 240
	elif rate == rate_14bit:
		N = 14
		mcp_sps = 1 / 60
	elif rate == rate_16bit:
		N = 16
		mcp_sps = 1 / 15
	
	sleep(mcp_sps * 1.4)
	
	max_retries = 5  # Increased from 3
	retry_count = 0
	backoff_time = 0.1
	
	while retry_count < max_retries:
		try:
			data = bus.read_i2c_block_data(MCP342X_DEFAULT_ADDRESS, channel, 2)
			voltage = ((data[0] << 8) | data[1])
			if voltage >= 32768:
				voltage = 65536 - voltage
			voltage = (2 * VRef * voltage) / (2 ** N)
			return round(voltage, 5)
			
		except OSError as e:
			# Specific handling for I/O errors
			retry_count += 1
			error_msg = f"I2C error (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			
			if retry_count < max_retries:
				# Try resetting the I2C bus
				if retry_count > 1:
					try:
						bus.close()
						sleep(backoff_time * 2)
						bus = smbus.SMBus(1)
					except:
						pass
				sleep(backoff_time)
				backoff_time *= 2
			else:
				logger.error(f"Failed to read ADC after {max_retries} attempts")
				return -1  # Return error value instead of raising exception
		except Exception as e:
			# Handle other exceptions
			retry_count += 1
			error_msg = f"ADC error (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			
			if retry_count < max_retries:
				sleep(backoff_time)
				backoff_time *= 2
			else:
				logger.error(f"Failed to read ADC: {e}")
				return -1  # Return error value instead of raising exception
				
	return -1 

def read_adc(mcp_i2c_address, sample_time):
	global MCP342X_DEFAULT_ADDRESS, airflow_only, airflow_sensor, airflow_channel, airflow_sensor_bias, calibration
	MCP342X_DEFAULT_ADDRESS = mcp_i2c_address
	
	airflow_sample_voltage = voltage_channel1 = voltage_channel3 = voltage_channel2 = sum_channel1 = sum_channel2 = sum_channel3 = 0
	average_channel1 = average_channel2 = average_channel3 = airflow_avg = 0
	airflow_sample_index = 1
	skipsampling = False
	i = j = 0
	error_count = 0
	max_errors = 5  # Maximum consecutive errors before giving up

	start = time()
	last_check_time = time()
	airflow_samples_to_take = 5 if sample_time < 20 else 20
	airflow_samples_to_take = 200 if airflow_only is True else airflow_samples_to_take
	check_interval = 1
	if airflow_type != 9:
		try:
			if (airflow_sensor_bias == -1):
				sens_bias_samples_to_take = 100
				initialise(airflow_channel, rate_12bit)
				airflow_sample_sum = 0
				try:
					while airflow_sample_index<=sens_bias_samples_to_take:
						airflow_sample_voltage = getconvert(airflow_channel, rate_12bit)
						airflow_sample_sum += airflow_sample_voltage
						airflow_sample_index+=1
					average_channel3 = airflow_sample_sum / sens_bias_samples_to_take
					airflow_sensor_bias = 0.5-average_channel3
					
					# Print debug info
					print(f"DEBUG: Raw airflow sum: {airflow_sample_sum}")
					print(f"DEBUG: Samples: {sens_bias_samples_to_take}")
					print(f"DEBUG: Avg: {average_channel3}")
					print(f"DEBUG: Calculated bias: {airflow_sensor_bias}")
					
					if (airflow_sensor_bias > abs(0.05)):
						logger.error(f"Airflow Sensor Bias is to high ({airflow_sensor_bias}). Check Sensor")
						shutdown(f"Airflow Sensor Bias is to high ({airflow_sensor_bias}). Check Sensor.",6)
					print(f"airflow_sensor_bias is set to {airflow_sensor_bias}")
					logger.debug(f"airflow_sensor_bias is set to {airflow_sensor_bias}")
				except Exception as e:
					# If there's an error, reset the bias to a default value
					print(f"Error calculating airflow sensor bias: {e}")
					airflow_sensor_bias = 0
				skipsampling = True
		except NameError:
			pass



	while ((time()-start) < sample_time-0.25) and (skipsampling is False):
		if (airflow_only is False):
			initialise(channel1, rate)
			voltage_channel1 = getconvert(channel1, rate)
			if voltage_channel1 == -1:
				error_count += 1
				if error_count > max_errors:
					logger.error(f"Too many consecutive ADC errors ({error_count})")
					# Instead of shutdown, return sentinel values
					return -1, -1, -1
				continue  # Skip this iteration and try again
			error_count = 0  # Reset error count on success
			sum_channel1 += voltage_channel1
			
			initialise(channel2, rate)
			voltage_channel2 = getconvert(channel2, rate)
			if voltage_channel2 == -1:
				error_count += 1
				if error_count > max_errors:
					logger.error(f"Too many consecutive ADC errors ({error_count})")
					return -1, -1, -1
				continue
			error_count = 0
			sum_channel2 += voltage_channel2
		if (debug):
			try:
				atn_current=round((numpy.log(voltage_channel1/voltage_channel2)*-100),5)
			except:
				pass
		sample_every_x_cycle = 5 if rate == rate_12bit else 2
		if ((airflow_sensor is True) or (airflow_only is True)) and (i % sample_every_x_cycle == 0) and (calibration is False):
			if (airflow_type < 9):
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
			if airflow_type==9:
				current_airflow = read_airflow_ml()
				if current_airflow == -1:
					continue
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
	if (skipsampling is False) and (i>0):
		average_channel3 = (sum_channel3 / j) if (airflow_sensor is True) and (calibration is False) and (j > 0) else 0

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
			0.511:0.010,
			0.8:0.055,
			0.9:0.09,
			1.34:0.19,
			1.855:0.39,
			1.96:0.46,
			2.0:0.487,
			2.024:0.504

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

		return interpolated_value#-airflow_sensor_bias



def get_sensor_values(MCP342X_DEFAULT_ADDRESS,sample_time):
	main_sensor_value = reference_sensor_value = airflow_sensor_value = 0
	try:
		sensor_values = read_adc(MCP342X_DEFAULT_ADDRESS, sample_time)
	except Exception as e:
		print(f"Can't read from ADC: {e}")
		return -1, -1, -1
	main_sensor_value = sensor_values[0]
	reference_sensor_value = sensor_values[1]
	airflow_sensor_value = sensor_values[2]
	return main_sensor_value, reference_sensor_value, airflow_sensor_value

def set_pwm_duty_cycle(component, duty_cycle, stop_event=None):
	"""Set PWM duty cycle with error handling and reconnection logic"""
	global config, pi
	reverse_dutycycle = config.get('reverse_dutycycle', False)
	
	# First check if we should terminate early
	if stop_event and stop_event.is_set():
		if debug:
			print(f"Exiting PWM thread for {component} immediately")
		return
	
	try:
		duty_cycle = int(duty_cycle)
		
		if component == 'pump':
			# Validate duty cycle range
			if 0 <= duty_cycle <= PUMP_PWM_RANGE:
				adjusted_duty = PUMP_PWM_RANGE - duty_cycle if reverse_dutycycle else duty_cycle
				
				# Set the PWM with proper error handling
				try:
					# Check if pi is defined and connected
					if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
						pi.set_PWM_dutycycle(PUMP_PIN, adjusted_duty)
					else:
						# Try to reinitialize if not connected
						if initialize_pwm_control():
							pi.set_PWM_dutycycle(PUMP_PIN, adjusted_duty)
				except Exception as e:
					logger.warning(f"PWM error for {component}: {e}")
					
		elif component == 'infrared_led':
			# Similar logic for LED
			if 0 <= duty_cycle <= LED_PWM_RANGE:
				try:
					if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
						pi.set_PWM_dutycycle(INFRARED_LED_PIN, duty_cycle)
					else:
						if initialize_pwm_control():
							pi.set_PWM_dutycycle(INFRARED_LED_PIN, duty_cycle)
				except Exception as e:
					logger.warning(f"PWM error for {component}: {e}")
					
	except Exception as e:
		logger.error(f"PWM control failed for {component}: {e}")
		# Try to set a safe state
		if component == 'pump':
			try:
				if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
					safe_duty = PUMP_PWM_RANGE if reverse_dutycycle else 0
					pi.set_PWM_dutycycle(PUMP_PIN, safe_duty)
			except:
				pass

def check_airflow(current_mlpm):
	global pump_dutycycle, reverse_dutycycle, zero_airflow, airflow_only, airflow_debug, config, temperature_current, temperature_to_keep, disable_pump_control, override_airflow, desired_airflow_in_lpm, set_PWM_dutycycle_thread
	
	threshold_airflow = 0.005  # liter per minute minimum; else pump might be defective
	if override_airflow is False:
		desired_airflow_in_lpm = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))
	
	if airflow_only is True:
		disable_pump_control = True
	
	if disable_pump_control is False:
		if current_mlpm < 0.005 and desired_airflow_in_lpm > 0:
			zero_airflow += 1
			if zero_airflow == 5 and not stop_event.is_set():
				print("resetting pump; no airflow?!")
				logger.debug("resetting pump... no airflow measured")
				pump_test()
				sleep(1)
				zero_airflow = 0
				return
		zero_airflow = 0 if current_mlpm > 0.005 and zero_airflow > 0 else zero_airflow

		if current_mlpm < desired_airflow_in_lpm and airflow_debug is False:
			if reverse_dutycycle is True:
				if pump_dutycycle <= 0:
					adjust_airflow(current_mlpm)
					pump_dutycycle = pump_pwm_freq
				else:
					pump_dutycycle += 1
			else:
				if pump_dutycycle >= PUMP_PWM_RANGE:
					adjust_airflow(current_mlpm)
					pump_dutycycle = 0
				else:
					pump_dutycycle += 1

		if current_mlpm > desired_airflow_in_lpm and airflow_debug is False:
			if reverse_dutycycle is True:
				pump_dutycycle -= 1
			else:
				pump_dutycycle -= 1

		pump_dutycycle = max(0, min(pump_dutycycle, PUMP_PWM_RANGE))
		
		# Make sure previous thread completed or is not running
		if set_PWM_dutycycle_thread and set_PWM_dutycycle_thread.is_alive():
			# Just wait a tiny bit for the previous thread to complete
			set_PWM_dutycycle_thread.join(timeout=0.1)
		
		# Only start a new thread if not stopping
		if not stop_event.is_set():
			set_PWM_dutycycle_thread = Thread(
				target=set_pwm_duty_cycle, 
				args=('pump', pump_dutycycle, stop_event,),
				name="PWM_Thread"
			)
			set_PWM_dutycycle_thread.daemon = True  # Make thread daemon so it won't block program exit
			set_PWM_dutycycle_thread.start()

		show_display(f"{round(current_mlpm*1000)} ml/min", 2, False)
	else:
		if not stop_event.is_set():
			set_PWM_dutycycle_thread = Thread(
				target=set_pwm_duty_cycle, 
				args=('pump', pump_dutycycle, stop_event,),
				name="PWM_Thread"
			)
			set_PWM_dutycycle_thread.daemon = True
			set_PWM_dutycycle_thread.start()

	if debug is True:
		print(f"{round(current_mlpm*1000, 2)} ml/min, desired: {round(desired_airflow_in_lpm*1000, 2)} ml/min, pump_dutycycle: {pump_dutycycle}")


def adjust_airflow(current_mlpm):
	global pump_dutycycle, override_airflow, desired_airflow_in_lpm
	print(current_mlpm, desired_airflow_in_lpm)
	if current_mlpm < desired_airflow_in_lpm:
		override_airflow = True
		desired_airflow_in_lpm -= 0.01 
		logger.debug(f"Cannot reach airflow. Adjusting to {round(desired_airflow_in_lpm,3)}")
		print(f"Adjusting airflow to {desired_airflow_in_lpm}")
		sleep(1)
		if desired_airflow_in_lpm <= 0.06:
			logger.error("Minimum airflow of 60 ml not reached. Stopping the script.")
			print("Minimum airflow of 60 ml not reached. Stopping the script.")
			shutdown("NOMAXAIRFLOW",6)
	return

def pump_test():
	logger.debug("Init Pump")
	if (reverse_dutycycle is True):
		for cyclepart in range(1,11):
			set_pwm_duty_cycle('pump', PUMP_PWM_RANGE/cyclepart)
			sleep(0.1)
		set_pwm_duty_cycle('pump', PUMP_PWM_RANGE)

	else:
		for cyclepart in range(1,11):
			try:
				set_pwm_duty_cycle('pump', cyclepart*10*(PUMP_PWM_RANGE/100))
				sleep(0.1)
			except Exception as e:
				logger.error(e)
		set_pwm_duty_cycle('pump', 0)



def button_pressed():
	input_state = GPIO.input(16)
	if input_state == False:
		print(yo)
		pass

def createLog(log,header):
	Path(base_dir +"/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile(base_dir+"/logs/log_current.csv"):
		os.remove(base_dir+"/logs/log_current.csv")
	if os.path.isfile(base_dir+"/logs/compair_offline_log.log"):
		os.remove(base_dir+"/logs/compair_offline_log.log")
	with open(base_dir+"/logs/" + log, "a") as logfileArchive: #save this logfile for archive
		logfileArchive.write(header + "\n\n")
		os.chmod(base_dir+"/logs/" + log, 0o777)
	with open(base_dir+"/logs/log_current.csv", "a") as temporary_log: # temporary current logfile for web interface
		temporary_log.write(header + "\n\n")
	with open(base_dir+"/logs/compair_offline_log.log", "w") as compair_offline_log: #save this logfile for archive
		compair_offline_log.write("timestamp;bcngm3;atn;bcmsen;bcmref;bcmtemperature;location;filter_status" + "\n\n")
		os.chmod(base_dir+ "/logs/compair_offline_log.log", 0o777)

def filter_values(log, kernel):
	file_path = output_file_path = log
	delimiter = ';'
	with open(file_path, 'r') as file:
		reader = csv.DictReader(file, delimiter=delimiter)
		data = list(reader)
	bc_values = []
	for row in data:
		try:
			value = float(row['BCngm3_unfiltered']) if not is_ebcMeter else float(row['BCugm3_unfiltered'])
		except ValueError:
			value = float('nan')
		bc_values.append(value)
	filtered_bc_values = median_filter(bc_values, size=kernel)
	for i, row in enumerate(data):
		if not float('nan') == filtered_bc_values[i]:
			column_name = 'BCugm3' if is_ebcMeter else 'BCngm3'
			row[column_name] = str(int(filtered_bc_values[i]))

	with open(output_file_path, 'w', newline='') as output_file:
		fieldnames = reader.fieldnames
		writer = csv.DictWriter(output_file, fieldnames=fieldnames, delimiter=delimiter)
		writer.writeheader()
		writer.writerows(data)


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
	global housekeeping_thread, airflow_sensor, temperature_to_keep, airflow_sensor_bias, session_running_since, sender_password, ds18b20, config, temperature_current, TWELVEVOLT_ENABLE, notice
	TWELVEVOLT_IS_ENABLED = False
	filter_status_threshold = 3
	compair_offline_logging = False
	if (airflow_only is True):
		get_sensor_values(MCP342X_DEFAULT_ADDRESS, 86400*31)
		return
	last_email_time = time()
	first_value = True
	reference_sensor_value_last_run=filter_status = samples_taken = sht_humidity=delay=airflow_sensor_value=reference_sensor_value=reference_sensor_bias=main_sensor_bias=bcmRefFallback=bcmSenRef=reference_sensor_value_current=main_sensor_value_current=main_sensor_value_last_run=attenuation_last_run=BCngm3=BCngm3_unfiltered=temperature_current=bcm_temperature_last_run=attenuation_coeff=absorption_coeff=0
	notice = devicename
	volume_air_per_sample = absorb = main_sensor_value = attenuation = attenuation_current = 0.0000
	today = str(datetime.now().strftime("%y-%m-%d"))
	session_running_since = datetime.now()
	now = str(datetime.now().strftime("%H:%M:%S"))
	if debug == False:
		logFileName =(str(today) + "_" + str(now) + ".csv").replace(':','')
		if is_ebcMeter:
			header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCugm3_unfiltered;BCugm3;Temperature;notice;main_sensor_bias;reference_sensor_bias;sampleDuration;sht_humidity;airflow"
		else:
			header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3_unfiltered;BCngm3;Temperature;notice;main_sensor_bias;reference_sensor_bias;sampleDuration;sht_humidity;airflow"
		compair_offline_log_header="timestamp,bcngm3,atn,bcmsen,bcmref,bcmtemperature, location, filter_status"
		new_log_message="Started log " + str(today) + " " + str(now) + " " + str(bcMeter_version) + " " + str(logFileName)
		print(new_log_message)
		logger.debug(new_log_message)
		createLog(logFileName,header)
		manage_bcmeter_status(action='set', bcMeter_status=1)
		logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3_unfiltered) + ";"+ str(BCngm3) + ";" + str(temperature_current) + ";" + str(notice) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(sht_humidity) + ";" + str(volume_air_per_sample) 
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
		if stop_event.is_set():
			logger.debug("Main sampling thread received stop signal")
			return
		if (TWELVEVOLT_ENABLE is True) and (TWELVEVOLT_IS_ENABLED is False):
			GPIO.output(TWELVEVOLT_PIN, 1)
			TWELVEVOLT_IS_ENABLED = True
			print("12V Power is on")
		get_location = config.get('get_location', False)
		location = config.get('location', [0,0])
		device_specific_correction_factor = float(str(config.get('device_specific_correction_factor', 1)).replace(',', '.'))
		filter_scattering_factor = float(str(config.get('filter_scattering_factor', 1.39)).replace(',', '.'))
		mail_sending_interval = float(str(config.get('mail_sending_interval', 6)).replace(',', '.'))
		filter_status_mail = config.get('filter_status_mail', False)
		send_log_by_mail = config.get('send_log_by_mail', False)
		email_service_password = config.get('email_service_password', 'email_service_password')
		led_brightness = int(config.get('led_brightness', 100))
		sample_time = int(config.get('sample_time', 300))
		if (is_ebcMeter and sample_time>30):
			sample_time=30
		sens_correction = float(str(config.get('sens_correction', 1)).replace(',', '.'))
		ref_correction = float(str(config.get('ref_correction', 1)).replace(',', '.'))
		sample_spot_diameter = float(str(config.get('sample_spot_diameter', 0.5)).replace(',', '.'))
		sender_password = str(config.get('sender_password'))
		set_pwm_duty_cycle('infrared_led', led_brightness)
		start = time()
		if (samples_taken < 3) and (sample_time >60):
			sample_time=60
		samples_taken+=1
		reference_sensor_value_last_run=reference_sensor_value
		sensor_values=get_sensor_values(MCP342X_DEFAULT_ADDRESS, sample_time)
		if sensor_values == [-1,-1,-1]:
			continue
		main_sensor_value = sensor_values[0]*sens_correction
		reference_sensor_value = sensor_values[1]*ref_correction
		#test small compensation:
		#env_change = reference_sensor_value_last_run - reference_sensor_value
		#if env_change !=0:
		#	main_sensor_value = main_sensor_value * (1 - (numpy.log10(abs(env_change) + 1) * -1 * (1 + abs(env_change))))
		if (airflow_sensor is True):
			if airflow_type < 9:
				airflow_sensor_value = sensor_values[2]
				airflow_per_minute = round(airflow_by_voltage(airflow_sensor_value,af_sensor_type),4)
				if (af_sensor_type==0) and (airflow_per_minute>0.075):
					logger.error("To high airflow!")
				if (af_sensor_type==1) and (airflow_per_minute>450):
					logger.error("To high airflow!")

				#logger.debug("measurement took ", delay)
			else:
				airflow_per_minute = read_airflow_ml()
			delay = time() - start
			volume_air_per_sample=(delay/60)*airflow_per_minute #liters of air between samples	
		else:
			airflow_per_minute = float(config.get('airflow_per_minute', 0.100).replace(',', '.'))
			volume_air_per_sample=(sample_time/60)*airflow_per_minute #liters of air between samples
		main_sensor_value_current=main_sensor_value#-main_sensor_bias
		reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
		try:
			temperature_current = get_temperature()
		except:
			temperature_current = 1
		if (reference_sensor_value_current == 0): reference_sensor_value_current = 1 #avoid later divide by 0; just for debug
		if (main_sensor_value_current == 0): main_sensor_value_current = 1#avoid later divide by 0; just for debug#
		filter_status_quotient = main_sensor_value_current/reference_sensor_value_current
		filter_status = (
			5 if filter_status_quotient > 0.8 else
			4 if filter_status_quotient > 0.7 else
			3 if filter_status_quotient > 0.6 else
			2 if filter_status_quotient > 0.4 else
			1 if filter_status_quotient > 0.2 else
			0 if filter_status_quotient <= 0.2 else
			-1
		)

		manage_bcmeter_status(action='set', filter_status=filter_status)
		current_time = time()
		mail_sending_interval_in_seconds = mail_sending_interval*60*60
		if (current_time - last_email_time >= mail_sending_interval_in_seconds) and (samples_taken>1):

			if (send_log_by_mail is True) and (mail_logs_to != "your@email.address") and (mail_logs_to is not None) and (sender_password !="email_service_password"):
				if (check_connection()):
					if (send_log_by_mail):
						send_email("Log")
					if (filter_status_mail) and (filter_status<filter_status_threshold):
						send_email(f"Filter Status {filter_status}")
			else:
				logger.error("Contact jd@bcmeter.org for email service password. this is a antispam protection.")
				send_log_by_mail = False
				filter_status_mail = False
			last_email_time = current_time
		if (abs(bcm_temperature_last_run-temperature_current) > .5): notice = notice + "tempChange-"
		attenuation_current=round((numpy.log(main_sensor_value_current/reference_sensor_value_current)*-100),5)

		atn_peak = False
		if (attenuation_last_run != 0) and (samples_taken>1) and (attenuation_current != 0):
			peakdetection = 1 - abs((attenuation_last_run/attenuation_current))
			if (peakdetection > 0.015) and (abs(attenuation_current- attenuation_last_run)>1.5):
				atn_peak = True
				notice = notice + "PEAK"
		if (attenuation_last_run == 0):
			attenuation_last_run = attenuation_current
		if (airflow_per_minute<0.005) and (airflow_sensor is True) and (disable_pump_control is False):
			if (mail_logs_to is not None) and (mail_logs_to != "your@email.address"):
				online=check_connection()
				logger.error("PUMP MALFUNCTION - STOPPING")
				if (online is True): 
					send_email("Pump")
			notice=notice+"NO_AF"
			print("disable_led", disable_led)
			if (disable_led is False):
				change_blinking_pattern.set()
				blinking_thread = Thread(target=blink_led, args=(555,change_blinking_pattern))
				blinking_thread.start()
			sleep(5)
			shutdown("PUMP MALFUNCTION",6)
		attenuation_coeff = sample_spot_areasize*((attenuation_current-attenuation_last_run)/100)/volume_air_per_sample	
		absorption_coeff = attenuation_coeff/filter_scattering_factor
		device_specific_correction_factor = device_specific_correction_factor/1000 if is_ebcMeter else device_specific_correction_factor
		try:
			BCngm3_unfiltered = int((absorption_coeff / sigma_air_880nm)*device_specific_correction_factor) #bc nanograms per m3
		except Exception as e:
			BCngm3_unfiltered = 1 #fallback
			logger.error("invalid value of BC: ",e)
			print(e)
		#if (temperature_current != 1.0000):
		#	BCngm3_unfiltered = apply_temperature_correction(BCngm3_unfiltered, temperature_current)
		#logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3_unfiltered) + ";" + str(round(temperature_current,1)) + ";" + str(notice) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(round(sht_humidity,1))
		sample_threshold_to_display = 4 if not is_ebcMeter else 6

		if (samples_taken>sample_threshold_to_display) and (airflow_only is False) and (debug is False):
			with open(base_dir+"/logs/" + logFileName, "a") as log:
				if is_ebcMeter:
					BCugm3 = BCngm3_unfiltered / 1000
					logString = f"{datetime.now().strftime('%d-%m-%y')};{datetime.now().strftime('%H:%M:%S')};{reference_sensor_value_current};{main_sensor_value_current};{attenuation_current};{attenuation_coeff};{BCngm3_unfiltered};{BCugm3};{round(temperature_current, 1)};{notice};{main_sensor_bias};{reference_sensor_bias};{round(delay, 1)};{round(sht_humidity, 1)};{round(airflow_per_minute,3)}"
				else:
					logString = f"{datetime.now().strftime('%d-%m-%y')};{datetime.now().strftime('%H:%M:%S')};{reference_sensor_value_current};{main_sensor_value_current};{attenuation_current};{attenuation_coeff};{BCngm3_unfiltered};{BCngm3_unfiltered};{round(temperature_current, 1)};{notice};{main_sensor_bias};{reference_sensor_bias};{round(delay, 1)};{round(sht_humidity, 1)};{round(airflow_per_minute,3)}"

				log.write(logString+"\n")
			kernel = 5 if not is_ebcMeter else 3
			if (samples_taken<kernel):
				kernel = samples_taken
			filter_values(base_dir + "/logs/" + logFileName, kernel)
			log_file_path = base_dir+"/logs/" + logFileName
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
				unit = "ng" if not is_ebcMeter else "ug"
				if average > 0:
					show_display(f"{int(average)} {unit}m3/hr", False, 0)
				else:
					show_display(f"Sampling...", False, 0)
			else:
				show_display(f"No AVG yet", False, 0)
			compair_offline_log_path = base_dir+"/logs/compair_offline_log.log"
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
			os.popen("cp " + base_dir + "/logs/" + logFileName + " " + base_dir + "/logs/log_current.csv")
		notice=""
		main_sensor_value_last_run=main_sensor_value_current 
		reference_sensor_value_last_run = reference_sensor_value
		attenuation_last_run=attenuation_current
		bcm_temperature_last_run = temperature_current
		atn_peak = False
		online = False
		if (run_once == "true"): 
			logger.debug("cycle of " + str(sample_time) + " took " + str(round(delay,2)) + " seconds")
			GPIO.output(INFRARED_LED_PIN, 0)
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
		if stop_event.is_set():
			logger.debug("Main sampling thread received stop signal")
			return


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

def get_temperature():
	global last_valid_temperature, temperature_error_count, notice
	
	try:
		if ds18b20:
			temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000, 2)
		elif sht40_i2c:
			sensor = adafruit_sht4x.SHT4x(i2c)
			temperature_samples = []
			humidity_samples = []
			for i in range(20):
				temperature_samples.append(sensor.temperature)
				humidity_samples.append(sensor.relative_humidity)
			temperature_current = sum(temperature_samples) / 20
			sht_humidity = sum(humidity_samples) / 20
		else:
			logger.warning("No temperature sensor detected, using fallback value")
			return last_valid_temperature if 'last_valid_temperature' in globals() else 1
		
		# If we got here, we have a valid reading
		last_valid_temperature = temperature_current
		temperature_error_count = 0
		return temperature_current
		
	except Exception as e:
		# Log specific error for debugging
		error_message = f"Temperature sensor error: {str(e)}"
		logger.warning(error_message)
		
		# Increment error counter
		if 'temperature_error_count' not in globals():
			temperature_error_count = 0
		temperature_error_count += 1
		
		# Add to notice if there are repeated errors
		if temperature_error_count > 3:
			notice += f"TempErr({temperature_error_count})-"
		
		# Return last valid temperature if we have one, otherwise fallback value
		return last_valid_temperature if 'last_valid_temperature' in globals() else 1


def housekeeping(stop_event):
	global temperature_to_keep, session_running_since, ds18b20, airflow_debug, config, temperature_current, TWELVEVOLT_ENABLE, notice
	while (True):
		config = config_json_handler()
		TWELVEVOLT_ENABLE = config.get('TWELVEVOLT_ENABLE')
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
				if (pump_dutycycle >= 0 ) and (pump_dutycycle <= PUMP_PWM_RANGE):
					set_pwm_duty_cycle('pump',pump_dutycycle)
				else:
					logger.error(f"wrong pump_dutycycle {pump_dutycycle}")
					set_pwm_duty_cycle('pump', 50)
			except Exception as e:
				print(e)
		#go on with temperature stabilization
		try:
			temperature_current = get_temperature()
			# No need for an except block since get_temperature() handles errors internally
		except Exception as e:
			# This should rarely happen, but just in case
			logger.error(f"Unexpected error in temperature handling: {str(e)}")
			temperature_current = temperature_current if 'temperature_current' in locals() else 1
			notice += "TempFail-"
		skipheat = False
		skipheat = True if temperature_current == 1 else skipheat
		heating = config.get('heating', False)
		led_brightness = config.get('led_brightness',100)
		set_pwm_duty_cycle('infrared_led', led_brightness)
		#if debug:
		#	print("skip heating: " + str(skipheat) + " / heating: " + str(heating) + " / current temp: " + str(temperature_current) + " / temp to keep: " + str(temperature_to_keep))

		#logger.debug("skip heating: " + str(skipheat) + " / heating: " + str(heating) + " / current temp: " + str(temperature_current) + " / temp to keep: " + str(temperature_to_keep))
		if (cooling is True):
			GPIO.output(23,True)


		if (heating is True) and (skipheat is False) and (cooling is False):
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
		pass
	while not change_blinking_pattern.is_set():
		blink_duration = 0.5 if pattern != 555 else 3
		GPIO.output(MONOLED_PIN, GPIO.HIGH)
		sleep(blink_duration)
		GPIO.output(MONOLED_PIN, GPIO.LOW)
		sleep(blink_duration*2)



if __name__ == '__main__':
	GPIO.setup(1,GPIO.OUT)
	GPIO.setup(23,GPIO.OUT)

	if (calibration):
		find_mcp_adress()
		set_pwm_duty_cycle('infrared_led', led_brightness)
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
		airflow_sensor_bias = -1
		read_airflow_sensor_bias = read_adc(MCP342X_DEFAULT_ADDRESS,1)
		#pump_test()
		sleep(0.5)

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

