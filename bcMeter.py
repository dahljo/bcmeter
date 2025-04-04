#!/usr/bin/env python3
import subprocess, sys
import RPi.GPIO as GPIO
import smbus
import os
import json
from datetime import datetime
import re
from collections import deque
from bcMeter_shared import (config_json_handler, check_connection, manage_bcmeter_status, 
						   show_display, config, i2c, setup_logging, run_command, 
						   send_email, update_config, filter_values_ona, apply_dynamic_airflow)
import pigpio

#os.system('clear')

bcMeter_version = "0.9.97 2025-04-04"
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
sample_spot_diameter = float(str(config.get('sample_spot_diameter', 0.4)).replace(',', '.'))
is_ebcMeter = config.get('is_ebcMeter', False)
mail_logs_to = config.get('mail_logs_to', "")
send_log_by_mail = config.get('send_log_by_mail', False)
filter_status_mail = config.get('filter_status_mail', False)
disable_led = config.get('disable_led', False)
airflow_type = int(config.get('af_sensor_type', 1))
TWELVEVOLT_ENABLE = config.get('TWELVEVOLT_ENABLE', False)
automatic_airflow_control = config.get('automatic_airflow_control', False)

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
	global reverse_dutycycle, housekeeping_thread, set_PWM_dutycycle_thread, sampling_thread,TWELVEVOLT_ENABLE
	stop_event.set()
	change_blinking_pattern.set()
	print(f"Quitting: {reason}")
	logger.debug(f"Shutdown initiated: {reason}")
	if shutdown_code is None:
		shutdown_code = 5
	manage_bcmeter_status(action='set', bcMeter_status=shutdown_code)
	show_display("Goodbye", 0, True)
	if reason == "SIGINT" or reason == "SIGTERM":
		show_display("Turn off bcMeter", 1, True)
	else:
		show_display(f"{reason}", 1, True)
	show_display("", 2, True)
	if reason != "Already running":
		try:
			if 'pi' in globals() and pi.connected:
				if TWELVEVOLT_ENABLE:
					pi.set_PWM_dutycycle(TWELVEVOLT_PIN, 0)
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
				pi.stop()
				logger.debug("pigpio connection stopped")
				try:
					subprocess.run(["sudo", "killall", "pigpiod"], 
								 check=False, timeout=2)
					logger.debug("pigpiod process terminated")
				except subprocess.TimeoutExpired:
					logger.warning("Timeout while trying to kill pigpiod")
		except Exception as e:
			logger.error(f"Error stopping pigpio: {e}")
	from threading import current_thread
	current_thread_id = current_thread().ident
	threads_to_join = []
	if sampling_thread and sampling_thread.is_alive() and sampling_thread.ident != current_thread_id:
		threads_to_join.append(sampling_thread)
	if housekeeping_thread and housekeeping_thread.is_alive() and housekeeping_thread.ident != current_thread_id:
		threads_to_join.append(housekeeping_thread)
	if set_PWM_dutycycle_thread and set_PWM_dutycycle_thread.is_alive() and set_PWM_dutycycle_thread.ident != current_thread_id:
		threads_to_join.append(set_PWM_dutycycle_thread)
	for thread in threads_to_join:
		thread.join(timeout=1)
		if thread.is_alive():
			logger.warning(f"Thread {thread.name} didn't terminate within timeout")
	try:
		GPIO.cleanup()
		logger.debug("GPIO cleanup completed")
	except Exception as e:
		logger.error(f"Error during GPIO cleanup: {e}")
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
		pigpiod_running = subprocess.run(["pgrep", "-x", "pigpiod"], 
									 stdout=subprocess.PIPE).returncode == 0
		if pigpiod_running:
			try:
				subprocess.run(["sudo", "killall", "pigpiod"], check=False)
				sleep(2)  # Give it time to fully stop
			except:
				pass
		os.system("sudo pigpiod -l -m")  # Add logging and minimize CPU usage
		sleep(3)
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
		pi.set_mode(PUMP_PIN, pigpio.OUTPUT)
		pi.set_mode(INFRARED_LED_PIN, pigpio.OUTPUT)
		pi.set_PWM_range(PUMP_PIN, PUMP_PWM_RANGE)
		pi.set_PWM_frequency(PUMP_PIN, PUMP_PWM_FREQ)
		pi.set_PWM_range(INFRARED_LED_PIN, LED_PWM_RANGE)
		pi.set_PWM_frequency(INFRARED_LED_PIN, LED_PWM_FREQ)
		sleep(0.5)  
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
		shutdown("SIGTERM") 	
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
			retry_count += 1
			error_msg = f"I2C error during initialization (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			if retry_count < max_retries:
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
				return False
		except Exception as e:
			retry_count += 1
			error_msg = f"Error during initialization (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			if retry_count < max_retries:
				sleep(backoff_time)
				backoff_time *= 2
			else:
				logger.error(f"Failed to initialize ADC: {e}")
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
	calibration_data = read_adc(MCP342X_DEFAULT_ADDRESS, 20)
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
	calibration_time = datetime.now().strftime("%y%m%d_%H%M%S")
	manage_bcmeter_status(action='set', calibration_time=calibration_time)
	print(f"set calibration time to {calibration_time}")
	filter_status_quotient = (raw_sens*sens_correction) / (raw_ref*ref_correction)
	if abs(filter_status_quotient - 1) < 0.01:
		manage_bcmeter_status(action='set', filter_status=5)
		print(f"set filter status to 5")
	else:
		logger.debug("Filter status quotient not 1 after calibration but {filter_status_quotient}")
		print("Filter status quotient not 1 after calibration")
	with open("bcMeter_config.json", "w") as f:
		json.dump(config, f, indent=4)
	print(f"correction factor sens: {sens_correction}  and ref: {ref_correction} ")
	print (f" using {sens_correction*raw_sens} and {ref_correction*raw_ref} as default now")


def find_mcp_address():
	global MCP342X_DEFAULT_ADDRESS
	try:
		for device in range(128):
			try:
				bus.read_byte(device)
				if hex(device) in ["0x68", "0x6a", "0x6b", "0x6c", "0x6d"]:
					MCP342X_DEFAULT_ADDRESS = device
			except:
				pass
		if 'MCP342X_DEFAULT_ADDRESS' in globals():
			logger.debug("ADC found at Address: %s", hex(MCP342X_DEFAULT_ADDRESS))
			return MCP342X_DEFAULT_ADDRESS
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
	max_retries = 5  
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
			retry_count += 1
			error_msg = f"I2C error (attempt {retry_count}/{max_retries}): {e}"
			print(error_msg)
			logger.warning(error_msg)
			if retry_count < max_retries:
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
class SamplingSession:
	"""Class to maintain measurement state during a sampling session."""
	def __init__(self):
		self.i = 0                # Sample counter for all measurements
		self.j = 0                # Sample counter for airflow
		self.error_count = 0      # Track consecutive ADC errors
		self.max_errors = 5       # Maximum allowed consecutive errors
		self.sums = {
		    'light': [0, 0, 0],   # channel1, channel2, channel3
		    'dark': [0, 0, 0]     # channel1, channel2, channel3 
		}
		self.counts = {'light': 0, 'dark': 0}


def measure_channel(channel, rate, session):
	"""Measure voltage from a specific ADC channel with error handling."""
	initialise(channel, rate)
	voltage = getconvert(channel, rate)
	if voltage == -1:
		session.error_count += 1
		success = False
		if session.error_count > session.max_errors:
			logger.error(f"Too many consecutive ADC errors ({session.error_count})")
		return voltage, success
	session.error_count = 0
	return voltage, True


def measure_voltage(phase_duration, is_dark_phase, session, sample_time):
	"""Measure voltage readings during a phase (dark or light)."""
	sums = [0, 0]  # [sum_channel1, sum_channel2]
	sum_channel3 = 0
	samples_count = 0
	start_time = time()
	while (time() - start_time) < phase_duration:
		if not airflow_only:
			voltage_ch1, success = measure_channel(channel1, rate, session)
			if not success: continue
			voltage_ch2, success = measure_channel(channel2, rate, session)
			if not success: continue
			if debug:
				pass
				#print(f"{session.i} dark {is_dark_phase}, {voltage_ch1}, {voltage_ch2}")
			sums[0] += voltage_ch1
			sums[1] += voltage_ch2
			samples_count += 1
		sample_every_x_cycle = 5 if rate == rate_12bit else 3
		should_measure_airflow = (
			((airflow_sensor is True) or (airflow_only is True)) and 
			(session.i % sample_every_x_cycle == 0) and 
			(calibration is False)
		)
		if should_measure_airflow:
			current_airflow, airflow_voltage = calculate_airflow(sample_time)
			if airflow_voltage != -1 and current_airflow != -1:
				sum_channel3 += airflow_voltage
				if airflow_sensor is True:
					#print(f"Airflow in measure_voltage: {current_airflow}")
					check_airflow(current_airflow) 
				session.j += 1
				if airflow_only:
					cycle = (session.j % 20) + 1
					if cycle == 1:
						airflow_avg = 0
					airflow_avg += current_airflow
					if debug:
						print(f"{current_airflow} lpm, avg {round(airflow_avg/cycle,4)} lpm")
		session.i += 1
	return sums, sum_channel3, samples_count


def read_adc(MCP342X_DEFAULT_ADDRESS, sample_time):
	"""Read and process values from all ADC channels."""
	global airflow_only, airflow_sensor, airflow_channel, airflow_sensor_bias, calibration, is_ebcMeter, led_brightness
	average_channel1 = average_channel2 = average_channel3 = 0
	combined_main_bias = combined_ref_bias = 0
	session = SamplingSession()
	if airflow_type != 9 and not calibration:
		try:
			if airflow_sensor_bias == -1:
				airflow_bias_result = calibrate_airflow_sensor_bias()
				if airflow_bias_result is not None:
					average_channel3 = airflow_bias_result
					return average_channel1, average_channel2, average_channel3, combined_main_bias, combined_ref_bias
		except NameError:
			pass
	chunk_duration = 5 #seconds
	led_cool_down_time = 1.3
	led_turn_on_time = 0.1
	overhead_time = (chunk_duration-1) * (led_cool_down_time + led_turn_on_time)
	num_chunks = 2 if calibration else int((sample_time*0.85-overhead_time) / (chunk_duration * 2))
	if debug:
		print(f"{num_chunks} chunks each dark/light")
	for cycle in range(num_chunks):
		set_pwm_duty_cycle('infrared_led', 0)
		sleep(led_cool_down_time)
		dark_results = measure_voltage(chunk_duration, True, session, sample_time)
		session.sums['dark'][0] += dark_results[0][0]  # channel1
		session.sums['dark'][1] += dark_results[0][1]  # channel2
		session.sums['dark'][2] += dark_results[1]     # channel3
		session.counts['dark'] += dark_results[2]      # sample count
		set_pwm_duty_cycle('infrared_led', led_brightness)
		sleep(led_turn_on_time)
		light_results = measure_voltage(chunk_duration, False, session, sample_time)
		session.sums['light'][0] += light_results[0][0]  # channel1
		session.sums['light'][1] += light_results[0][1]  # channel2
		session.sums['light'][2] += light_results[1]     # channel3
		session.counts['light'] += light_results[2]      # For calibration we need the actual sample count
		if stop_event.is_set():
			break
	if session.counts['dark'] > 0:
		combined_main_bias = session.sums['dark'][0] / session.counts['dark']
		combined_ref_bias = session.sums['dark'][1] / session.counts['dark']
		if combined_main_bias > 0.05 or combined_ref_bias > 0.05:
			logger.debug(f"Higher dark voltage detected - possible light leak: Main={combined_main_bias:.6f}, Ref={combined_ref_bias:.6f}")
	if calibration:
		if session.counts['light'] > 0:
			average_channel1 = session.sums['light'][0] / session.counts['light']
			average_channel2 = session.sums['light'][1] / session.counts['light']
		if debug:
			print(f"Calibration raw values: sens={average_channel1}, ref={average_channel2}")
	else:
		if session.counts['light'] > 0:
			if session.j > 0 and airflow_sensor is True and calibration is False:
				average_channel3 = (session.sums['light'][2]+session.sums['dark'][2]) / session.j
			average_channel1 = session.sums['light'][0] / session.counts['light']
			average_channel2 = session.sums['light'][1] / session.counts['light']
	return average_channel1, average_channel2, average_channel3, combined_main_bias, combined_ref_bias


def calculate_airflow(sample_time):
	"""Calculate airflow based on sensor readings."""
	airflow_samples_to_take = 5 if sample_time < 20 else 20
	airflow_samples_to_take = 200 if airflow_only else airflow_samples_to_take
	if airflow_type < 9:
		initialise(airflow_channel, rate_12bit)
		airflow_sample_sum = 0
		airflow_sample_index = 1
		while airflow_sample_index <= airflow_samples_to_take:
			airflow_sample_voltage = getconvert(airflow_channel, rate_12bit)
			if airflow_sample_voltage == 2.047:
				airflow_sample_voltage = 5
			airflow_sample_sum += airflow_sample_voltage
			airflow_sample_index += 1
		avg_airflow_voltage = airflow_sample_sum / airflow_samples_to_take
		if avg_airflow_voltage >= 2.047:
			logger.debug("airflow over sensor limit")
		current_airflow = round(airflow_by_voltage(avg_airflow_voltage, af_sensor_type), 4)
		return current_airflow, avg_airflow_voltage
	elif airflow_type == 9:
		current_airflow = read_airflow_ml()
		return current_airflow, current_airflow  # Return the same value twice since we don't have voltage
	else:
		return -1, -1  # Error case


def calibrate_airflow_sensor_bias():
	"""Calculate the bias for the airflow sensor."""
	global airflow_sensor_bias
	sens_bias_samples_to_take = 100
	initialise(airflow_channel, rate_12bit)
	airflow_sample_sum = 0
	airflow_sample_index = 1
	try:
		while airflow_sample_index <= sens_bias_samples_to_take:
			airflow_sample_voltage = getconvert(airflow_channel, rate_12bit)
			airflow_sample_sum += airflow_sample_voltage
			airflow_sample_index += 1
		average_channel3 = airflow_sample_sum / sens_bias_samples_to_take
		airflow_sensor_bias = 0.5 - average_channel3
		if abs(airflow_sensor_bias) > 0.05:
			logger.error(f"Airflow Sensor Bias is too high ({airflow_sensor_bias}). Check Sensor")
			shutdown(f"Airflow Sensor Bias is too high ({airflow_sensor_bias}). Check Sensor.", 6)
		logger.debug(f"airflow_sensor_bias is set to {airflow_sensor_bias}")
		return average_channel3
	except Exception as e:
		print(f"Error calculating airflow sensor bias: {e}")
		airflow_sensor_bias = 0
		return None


def airflow_by_voltage(voltage,sensor_type):
	global airflow_sensor_bias
	if (airflow_only is True) or (debug is True):
		pass
	if (sensor_type == 0):
		table = {
			0.5: 0.000,
			2.5: 0.100
		}
	if (sensor_type == 1) :
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
	if voltage in table:
		return table[voltage]
	else:
		voltages = sorted(table.keys())
		if voltage < voltages[0]:
			return 0
		if voltage > voltages[-1]:	
			return 0.5 if sensor_type==1 else 0.15  # Voltage is outside the range of the table
		lower_voltage = max(v for v in voltages if v <= voltage)
		upper_voltage = min(v for v in voltages if v >= voltage)
		lower_value = table[lower_voltage]
		upper_value = table[upper_voltage]
		interpolated_value = lower_value + (voltage - lower_voltage) * (upper_value - lower_value) / (upper_voltage - lower_voltage)
		return interpolated_value#-airflow_sensor_bias


def get_sensor_values(MCP342X_DEFAULT_ADDRESS, sample_time):
	main_sensor_value = reference_sensor_value = airflow_sensor_value = 0
	main_sensor_bias = reference_sensor_bias = 0
	try:
		sensor_values = read_adc(MCP342X_DEFAULT_ADDRESS, sample_time)
	except Exception as e:
		print(f"Can't read from ADC: {e}")
		return -1, -1, -1, 0, 0
	if len(sensor_values) >= 5:  # If we get dark current bias values too
		main_sensor_value = sensor_values[0]
		reference_sensor_value = sensor_values[1]
		airflow_sensor_value = sensor_values[2]
		main_sensor_bias = sensor_values[3]
		reference_sensor_bias = sensor_values[4]
	else:
		main_sensor_value = sensor_values[0]
		reference_sensor_value = sensor_values[1]
		airflow_sensor_value = sensor_values[2]
		main_sensor_bias = 0
		reference_sensor_bias = 0
	return main_sensor_value, reference_sensor_value, airflow_sensor_value, main_sensor_bias, reference_sensor_bias


def set_pwm_duty_cycle(component, duty_cycle, stop_event=None):
	global config, pi
	reverse_dutycycle = config.get('reverse_dutycycle', False)
	if stop_event and stop_event.is_set():
		if debug:
			print(f"Exiting PWM thread for {component} immediately")
		return
	try:
		duty_cycle = int(duty_cycle)
		if component == 'pump':
			if 0 <= duty_cycle <= PUMP_PWM_RANGE:
				adjusted_duty = PUMP_PWM_RANGE - duty_cycle if reverse_dutycycle else duty_cycle
				try:
					if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
						pi.set_PWM_dutycycle(PUMP_PIN, adjusted_duty)
					else:
						if initialize_pwm_control():
							pi.set_PWM_dutycycle(PUMP_PIN, adjusted_duty)
				except Exception as e:
					logger.warning(f"PWM error for {component}: {e}")
		elif component == 'infrared_led':
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
		if component == 'pump':
			try:
				if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
					safe_duty = PUMP_PWM_RANGE if reverse_dutycycle else 0
					pi.set_PWM_dutycycle(PUMP_PIN, safe_duty)
			except:
				pass


def check_airflow(current_mlpm):
	global pump_dutycycle, reverse_dutycycle, zero_airflow, airflow_only, airflow_debug, config
	global temperature_current, temperature_to_keep, disable_pump_control, override_airflow
	global desired_airflow_in_lpm, set_PWM_dutycycle_thread
	threshold_airflow = 0.003  # liter per minute minimum; else pump might be defective
	if override_airflow is False:
		desired_airflow_in_lpm = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))
	if airflow_only is True:
		disable_pump_control = True
	if disable_pump_control is False:
		if current_mlpm < threshold_airflow and desired_airflow_in_lpm > 0:
			zero_airflow += 1
			if zero_airflow == 5 and not stop_event.is_set():
				print("resetting pump; no airflow?!")
				logger.debug("resetting pump... no airflow measured")
				pump_test()
				sleep(1)
				zero_airflow = 0
				return
		zero_airflow = 0 if current_mlpm > threshold_airflow and zero_airflow > 0 else zero_airflow
		if current_mlpm < desired_airflow_in_lpm and airflow_debug is False and automatic_airflow_control is False:
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
		if set_PWM_dutycycle_thread and set_PWM_dutycycle_thread.is_alive():
			set_PWM_dutycycle_thread.join(timeout=0.1)
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
	if debug:
		print(f"{round(current_mlpm*1000, 2)} ml/min, desired: {round(desired_airflow_in_lpm*1000, 2)} ml/min, pump_dutycycle: {pump_dutycycle}")
		pass


def adjust_airflow(current_mlpm):
	global pump_dutycycle, override_airflow, desired_airflow_in_lpm
	if current_mlpm < desired_airflow_in_lpm:
		override_airflow = True
		desired_airflow_in_lpm -= 0.01 
		logger.debug(f"Cannot reach airflow. Adjusting to {round(desired_airflow_in_lpm,3)}")
		print(f"Adjusting airflow to {desired_airflow_in_lpm}")
		sleep(1)
		if desired_airflow_in_lpm <= 0.03:
			logger.error("Minimum airflow of 30 ml not reached. Stopping the script.")
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
	intercept = -15358.619
	temperature_coefficient = 1918.009
	temperature_squared_coefficient = -54.284
	correction_factor = intercept + temperature_current * temperature_coefficient + temperature_current**2 * temperature_squared_coefficient
	corrected_BCngm3_unfiltered = BCngm3_unfiltered * correction_factor	
	return corrected_BCngm3_unfiltered


def bcmeter_main(stop_event):
	global housekeeping_thread, airflow_sensor, temperature_to_keep, airflow_sensor_bias, desired_airflow_in_lpm
	global session_running_since, sender_password, ds18b20, config, temperature_current
	global TWELVEVOLT_ENABLE, notice, override_airflow, automatic_airflow_control

	airflow_per_minute = float(str(config.get('airflow_per_minute', 0.250)).replace(',', '.'))

	desired_airflow_in_lpm = airflow_per_minute
	TWELVEVOLT_IS_ENABLED = False
	filter_status_threshold = 3
	compair_offline_logging = False
	if airflow_only:
		get_sensor_values(MCP342X_DEFAULT_ADDRESS, 86400*31)
		return
	last_email_time = time()
	samples_taken = 0
	reference_sensor_value_last_run = main_sensor_value_last_run = attenuation_last_run = bcm_temperature_last_run = 0
	filter_status = sht_humidity = delay = airflow_sensor_value = reference_sensor_value = 0
	reference_sensor_bias = main_sensor_bias = BCngm3 = BCngm3_unfiltered = BCngm3_ona = temperature_current = 0
	attenuation_coeff = absorption_coeff = 0
	notice = devicename
	volume_air_per_sample = absorb = main_sensor_value = attenuation = attenuation_current = 0.0
	today = datetime.now().strftime("%y-%m-%d")
	session_running_since = datetime.now()
	now = datetime.now().strftime("%H:%M:%S")
	bc_measurements = []  
	logFileName = f"{today}_{now.replace(':','')}.csv"

	if not debug:
		header = "bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BC{unit}m3_unfiltered;BC{unit}m3;BC{unit}m3_ona;Temperature;notice;main_sensor_bias;reference_sensor_bias;sampleDuration;sht_humidity;airflow"
		header = header.replace("{unit}", "ug" if is_ebcMeter else "ng")
		compair_offline_log_header = "timestamp,bcngm3,atn,bcmsen,bcmref,bcmtemperature,location,filter_status"
		new_log_message = f"Started log {today} {now} {bcMeter_version} {logFileName}"
		print(new_log_message)
		logger.debug(new_log_message)
		createLog(logFileName, header)
		manage_bcmeter_status(action='set', bcMeter_status=1)
		online = check_connection()
	if compair_upload:
		import compair_frost_upload
	if not airflow_only:
		housekeeping_thread = Thread(target=housekeeping, args=(stop_event,))
		housekeeping_thread.start()
	write_log = False
	while True:
		if stop_event.is_set():
			logger.debug("Main sampling thread received stop signal")
			return
		if TWELVEVOLT_ENABLE and not TWELVEVOLT_IS_ENABLED:
			pi.set_PWM_dutycycle(TWELVEVOLT_PIN, 0)
			sleep(2)
			for duty in range(0, 255, 25):  
				pi.set_PWM_dutycycle(TWELVEVOLT_PIN, duty)
				sleep(0.1)
			TWELVEVOLT_IS_ENABLED = True
			print("12V Power is on")
		get_location = config.get('get_location', False)
		location = config.get('location', [0, 0])
		device_specific_correction_factor = float(str(config.get('device_specific_correction_factor', 1)).replace(',', '.'))
		filter_scattering_factor = float(str(config.get('filter_scattering_factor', 1.39)).replace(',', '.'))
		mail_sending_interval = float(str(config.get('mail_sending_interval', 6)).replace(',', '.'))
		filter_status_mail = config.get('filter_status_mail', False)
		send_log_by_mail = config.get('send_log_by_mail', False)
		email_service_password = config.get('email_service_password', 'email_service_password')
		led_brightness = int(config.get('led_brightness', 100))
		sample_time = int(config.get('sample_time', 300))
		if is_ebcMeter and sample_time > 30:
			sample_time = 30
		sens_correction = float(str(config.get('sens_correction', 1)).replace(',', '.'))
		ref_correction = float(str(config.get('ref_correction', 1)).replace(',', '.'))
		sample_spot_diameter = float(str(config.get('sample_spot_diameter', 0.5)).replace(',', '.'))
		sender_password = str(config.get('sender_password'))
		set_pwm_duty_cycle('infrared_led', led_brightness)
		start = time()
		if samples_taken < 3 and sample_time > 60:
			sample_time = 60
		samples_taken += 1
		reference_sensor_value_last_run = reference_sensor_value
		if debug:
			print(f"=========== Sample nr {samples_taken} =============")
		sensor_values = get_sensor_values(MCP342X_DEFAULT_ADDRESS, sample_time)
		if sensor_values == [-1, -1, -1, 0, 0]:  # Check all expected return values
			continue
		main_sensor_value = sensor_values[0] * sens_correction
		reference_sensor_value = sensor_values[1] * ref_correction
		airflow_sensor_value = sensor_values[2]
		main_sensor_bias = sensor_values[3] * sens_correction
		reference_sensor_bias = sensor_values[4] * ref_correction
		if airflow_sensor:
			if airflow_type < 9:
				airflow_per_minute = round(airflow_by_voltage(airflow_sensor_value, af_sensor_type), 4)
			else:
				airflow_per_minute = read_airflow_ml()
			delay = time() - start
			volume_air_per_sample = (delay / 60) * airflow_per_minute
		else:
			airflow_per_minute = float(config.get('airflow_per_minute', 0.250).replace(',', '.'))
			volume_air_per_sample = (sample_time / 60) * airflow_per_minute
		main_sensor_value_current = main_sensor_value - main_sensor_bias
		reference_sensor_value_current = reference_sensor_value - reference_sensor_bias
		try:
			temperature_current = get_temperature()
		except:
			temperature_current = 1
		if reference_sensor_value_current == 0:
			reference_sensor_value_current = 1
		if main_sensor_value_current == 0:
			main_sensor_value_current = 1
		filter_status_quotient = main_sensor_value_current / reference_sensor_value_current
		for i, threshold in enumerate([0.8, 0.7, 0.6, 0.4, 0.2]):
			if filter_status_quotient > threshold:
				filter_status = 5 - i
				break
		manage_bcmeter_status(action='set', filter_status=filter_status)
		current_time = time()
		mail_sending_interval_in_seconds = mail_sending_interval * 60 * 60
		if (current_time - last_email_time >= mail_sending_interval_in_seconds) and (samples_taken > 1):
			email_config_valid = (send_log_by_mail and mail_logs_to != "your@email.address" and 
								 mail_logs_to is not None and sender_password != "email_service_password")
			if email_config_valid:
				if check_connection():
					if send_log_by_mail:
						send_email("Log")
					if filter_status_mail and filter_status < filter_status_threshold:
						send_email(f"Filter Status {filter_status}")
			else:
				logger.error("Contact jd@bcmeter.org for email service password. This is an antispam protection.")
				send_log_by_mail = filter_status_mail = False
			last_email_time = current_time
		if abs(bcm_temperature_last_run - temperature_current) > 0.5:
			notice += "tempChange-"
		attenuation_current = round((numpy.log(main_sensor_value_current / reference_sensor_value_current) * -100), 5)
		atn_peak = False
		if attenuation_last_run != 0 and samples_taken > 1 and attenuation_current != 0:
			peakdetection = 1 - abs((attenuation_last_run / attenuation_current))
			if peakdetection > 0.015 and abs(attenuation_current - attenuation_last_run) > 1.5:
				atn_peak = True
				notice += "PEAK"
		if attenuation_last_run == 0:
			attenuation_last_run = attenuation_current
		if airflow_per_minute < 0.005 and airflow_sensor and not disable_pump_control and samples_taken > 1:
			if mail_logs_to is not None and mail_logs_to != "your@email.address":
				online = check_connection()
				logger.error("PUMP MALFUNCTION - STOPPING")
				if online:
					send_email("Pump")
			if not disable_led:
				change_blinking_pattern.set()
				blinking_thread = Thread(target=blink_led, args=(555, change_blinking_pattern))
				blinking_thread.start()
			sleep(5)
			shutdown("PUMP MALFUNCTION", 6)
		attenuation_coeff = sample_spot_areasize * ((attenuation_current - attenuation_last_run) / 100) / volume_air_per_sample
		absorption_coeff = attenuation_coeff / filter_scattering_factor
		if is_ebcMeter:
			device_specific_correction_factor /= 1000
		try:
			BCngm3_unfiltered = int((absorption_coeff / sigma_air_880nm) * device_specific_correction_factor)
		except Exception as e:
			BCngm3_unfiltered = 1
			logger.error(f"Invalid value of BC: {e}")
			print(e)
		should_log = not airflow_only and (
			BCngm3_unfiltered >= 10 or 
			(datetime.now() - session_running_since).total_seconds() >= 15 * 60 or 
			write_log is True
		) and samples_taken >= 3
		if should_log:
			write_log = True
			with open(f"{base_dir}/logs/{logFileName}", "a") as log:
				BCugm3 = BCngm3_unfiltered / 1000 if is_ebcMeter else BCngm3_unfiltered
				BCugm3_ona = 0.0
				log_data = [
					datetime.now().strftime('%d-%m-%y'),
					datetime.now().strftime('%H:%M:%S'),
					reference_sensor_value_current,
					main_sensor_value_current,
					attenuation_current,
					attenuation_coeff,
					BCngm3_unfiltered,
					BCugm3,
					BCugm3_ona,
					round(temperature_current, 1),
					notice,
					main_sensor_bias,
					reference_sensor_bias,
					round(delay, 1),
					round(sht_humidity, 1),
					round(airflow_per_minute, 3)
				]
				logString = ";".join(map(str, log_data))
				log.write(logString + "\n")
			kernel = 3 if is_ebcMeter else 5
			kernel = min(kernel, samples_taken)
			try:
				filter_values_ona(f"{base_dir}/logs/{logFileName}", delta_atn_min=0.05)
			except Exception as e:
				logger.error(f"Error applying ONA filter: {e}")
			try:
				filter_values(f"{base_dir}/logs/{logFileName}", kernel)
			except Exception as e:
				logger.error(f"Error applying standard filter: {e}")
			
			# Get filtered BC values for display
			filtered_bc_value = None
			log_file_path = f"{base_dir}/logs/{logFileName}"
			bc_values = []
			
			with open(log_file_path, 'r') as log_file:
				reader = csv.reader(log_file, delimiter=';')
				for i, line in enumerate(reader):
					if i == 0:  # Skip header
						continue
					try:
						# Get filtered BC value (column 7) instead of unfiltered
						if len(line) >= 8:
							bc_value = float(line[7])  # Use filtered BC value
							bc_values.append(bc_value)
					except (ValueError, IndexError):
						pass
			
			filtered_bc_value = bc_values[-1] if bc_values else 0
					
			average = sum(bc_values[-12:]) / min(12, len(bc_values)) if bc_values else 0
			if samples_taken > 15:
				unit = "ug" if is_ebcMeter else "ng"
				show_display(f"{int(average)} {unit}m3/hr" if average > 0 else "Sampling...", False, 0)
			else:
				show_display("No AVG yet", False, 0)
			bc_for_airflow = filtered_bc_value if filtered_bc_value is not None else 0
			bc_measurements.append(bc_for_airflow)
			if len(bc_measurements) > 4: 
				bc_measurements.pop(0)

			if not airflow_only and not disable_pump_control and automatic_airflow_control is True:
				try:
					if not is_ebcMeter:
						if len(bc_measurements) >= 4:
							avg_bc = sum(bc_measurements[-4:]) / 4
							
							print(f"Using average of last 4 filtered BC measurements for airflow adjustment: {avg_bc}")
							
							override_airflow, new_airflow = apply_dynamic_airflow(
								avg_bc, config, override_airflow, logger, af_sensor_type
							)
							if new_airflow is not None:
								desired_airflow_in_lpm = new_airflow
								airflow_per_minute = new_airflow
						else:
							# Not enough samples for average, use the default airflow from config
							default_airflow = float(str(config.get('airflow_per_minute', 0.250)).replace(',', '.'))
							if debug:
								print(f"Not enough BC samples for average. Using default airflow: {default_airflow}")
							desired_airflow_in_lpm = default_airflow
							airflow_per_minute = default_airflow
				except Exception as e:
					logger.error(f"Error adjusting airflow: {e}")
		notice = ""
		main_sensor_value_last_run = main_sensor_value_current
		reference_sensor_value_last_run = reference_sensor_value
		attenuation_last_run = attenuation_current
		bcm_temperature_last_run = temperature_current
		atn_peak = False
		online = False
		if run_once == "true":
			logger.debug(f"Cycle of {sample_time} took {round(delay, 2)} seconds")
			GPIO.output(INFRARED_LED_PIN, 0)
			shutdown("RUN ONCE")
		if not debug and reference_sensor_value_current != 0 and main_sensor_value != 0 and output_to_terminal:
			os.system('clear')
			logger.debug(f"{today} {now} {bcMeter_version} {logFileName}")
			headers = []
			with open('logs/log_current.csv', 'r') as csv_file:
				csv_reader = list(csv.reader(csv_file, delimiter=';'))
				print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
				print("Exit script with ctrl+c")
		delay = time() - start
		if stop_event.is_set():
			logger.debug("Main sampling thread received stop signal")
			return
		if debug:
			print("Main loop took", delay)
		if sample_time - delay >= 0:
			if debug:
				print("Sleeping", sample_time - delay)
			sleep(sample_time - delay)

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
		last_valid_temperature = temperature_current
		temperature_error_count = 0
		return temperature_current
	except Exception as e:
		error_message = f"Temperature sensor error: {str(e)}"
		logger.warning(error_message)
		if 'temperature_error_count' not in globals():
			temperature_error_count = 0
		temperature_error_count += 1
		if temperature_error_count > 3:
			notice += f"TempErr({temperature_error_count})-"
		return last_valid_temperature if 'last_valid_temperature' in globals() else 1


def housekeeping(stop_event):
	global temperature_to_keep, session_running_since, ds18b20, airflow_debug, config, temperature_current, TWELVEVOLT_ENABLE, notice, automatic_airflow_control
	pump_initialized = False
	while (True):
		config = config_json_handler()
		TWELVEVOLT_ENABLE = config.get('TWELVEVOLT_ENABLE')
		automatic_airflow_control = config.get('automatic_airflow_control', False)
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
				if not pump_initialized:
					if debug:
						print("Initializing pump with PWM ramp")
					show_display("Starting pump...", 2, False)
					start_duty = 0
					for duty in range(start_duty, pump_dutycycle + 1, 5):
						set_pwm_duty_cycle('pump', duty)
						sleep(0.1)
					pump_initialized = True
					if debug:
						print(f"Pump initialized at duty cycle: {pump_dutycycle}")
				elif (pump_dutycycle >= 0) and (pump_dutycycle <= PUMP_PWM_RANGE):
					set_pwm_duty_cycle('pump', pump_dutycycle)
				else:
					logger.error(f"wrong pump_dutycycle {pump_dutycycle}")
					set_pwm_duty_cycle('pump', 50)
			except Exception as e:
				logger.error(f"Pump control error: {e}")
				print(e)
			except Exception as e:
				print(e)
		try:
			temperature_current = get_temperature()
		except Exception as e:
			logger.error(f"Unexpected error in temperature handling: {str(e)}")
			temperature_current = temperature_current if 'temperature_current' in locals() else 1
			notice += "TempFail-"
		skipheat = False
		skipheat = True if temperature_current == 1 else skipheat
		heating = config.get('heating', False)
		led_brightness = config.get('led_brightness',100)
		if (cooling is True):
			GPIO.output(23,True)
		if (heating is True) and (skipheat is False) and (cooling is False):
			if ((temperature_to_keep - temperature_current) > 10):
				if (temperature_to_keep > 10):
					temperature_to_keep = temperature_current - 5
				GPIO.output(1,True)
				GPIO.output(23,True)
			elif temperature_current < (temperature_to_keep):
				GPIO.output(1,GPIO.HIGH)
				GPIO.output(23,GPIO.HIGH)
			elif (temperature_current > temperature_to_keep+0.2):
				if (temperature_to_keep <= 40):
					temperature_to_keep = round(temperature_current+0.5,1)
					GPIO.output(1,True)
					GPIO.output(23,True)
				else:
					GPIO.output(1,False)
					GPIO.output(23,False)
			elif ((temperature_to_keep - temperature_current)<0):
				GPIO.output(1,False)
				GPIO.output(23,False)
		sleep(2)


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
		find_mcp_address()
		if not initialize_pwm_control():
			logger.error("Failed to initialize PWM control for calibration")
			shutdown("PWM initialization failed", 6)
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
		find_mcp_address()
		airflow_sensor_bias = -1
		read_airflow_sensor_bias = read_adc(MCP342X_DEFAULT_ADDRESS,1)
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
