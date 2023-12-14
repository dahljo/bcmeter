#!/usr/bin/env python3

import subprocess, sys

cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
my_pid, err = process.communicate()
if len(my_pid.splitlines()) > 1:
	sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
	sys.exit(1)


from board import SCL, SDA, I2C
import RPi.GPIO as GPIO
import busio, smbus
import bcMeterConf
import logging
import os
from datetime import datetime




bcMeter_version = "0.9.898 2024-02-07"

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

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1



disable_pump_control = getattr(bcMeterConf, 'disable_pump_control', False) 
compair_upload = getattr(bcMeterConf, 'compair_upload', False) 
get_location = getattr(bcMeterConf, 'get_location', False) 
heating = getattr(bcMeterConf, 'heating', False)
pump_pwm_freq = getattr(bcMeterConf, 'pwm_freq', 20)
af_sensor_type = getattr(bcMeterConf, 'af_sensor_type', 1)
use_rgb_led = getattr(bcMeterConf, 'use_rgb_led', 0)
use_display = getattr(bcMeterConf, 'use_display', False)
led_brightness = getattr(bcMeterConf, 'led_brightness', 100)
airflow_sensor=getattr(bcMeterConf, 'airflow_sensor', False)	
pump_dutycycle = getattr(bcMeterConf,'pump_dutycycle', 20)
reverse_dutycycle = getattr(bcMeterConf,'reverse_dutycycle', False) 
sample_spot_diameter = getattr(bcMeterConf, 'sample_spot_diameter', 0.5)
is_ebcMeter= getattr(bcMeterConf,'is_ebcMeter', False) 
mail_logs_to= getattr(bcMeterConf,'mail_logs_to',"")
send_log_by_mail= getattr(bcMeterConf,'send_log_by_mail',False)
filter_status_mail= getattr(bcMeterConf,'filter_status_mail',False)

sender_password = getattr(bcMeterConf,'email_service_password','email_service_password')


sigma_air_880nm = 0.0000000777
run_once = "false"

#pwm for pump:
#GPIO.setup(12,GPIO.OUT)           # initialize as an output.

debug = False 
sht40_i2c = None
online = False
output_to_terminal = False 
ds18b20 = False

zero_airflow = 0




if (use_display is True):
	try:
		from oled_text import OledText, Layout64, BigLine, SmallLine
		oled = OledText(i2c, 128, 64)

		oled.layout = {
			1: BigLine(5, 0, font="Arimo.ttf", size=20),
			2: SmallLine(5, 25, font="Arimo.ttf", size=14),
			3: SmallLine(5, 40, font="Arimo.ttf", size=14)

		}
		logger.debug("Display found")
		
	except ImportError:
		logger.error("No display driver installed, update the device")

	def show_display(message, line, clear):
		if (use_display is True):
			if clear is True:
				oled.clear()
			oled.text(str(message),line+1)



if (use_display is True):
	show_display(f"Initializing", False, 0)


import traceback, numpy, os, csv, typing, re, glob, signal, socket, importlib, smtplib
from tabulate import tabulate
from pathlib import Path
from time import sleep, strftime, time
from threading import Thread
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
GPIO.setmode(GPIO.BCM)

devicename = socket.gethostname()

sample_spot_areasize=numpy.pi*(sample_spot_diameter/2)**2 #area of spot in cm2 from bcmeter, diameter 0.50cm



os.chdir('/home/pi')





debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "debug") else False

if (use_rgb_led == 1):
	# Set up GPIO pins
	R_PIN = 6
	G_PIN = 7
	B_PIN = 8
	GPIO.setmode(GPIO.BCM)
	GPIO.setup(R_PIN, GPIO.OUT)
	GPIO.setup(G_PIN, GPIO.OUT)
	GPIO.setup(B_PIN, GPIO.OUT)

	GPIO.output(R_PIN, 1)
	GPIO.output(G_PIN, 1)
	GPIO.output(B_PIN, 1)

infrared_led_control = 26
BUTTONPIN = 16

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

mode = MCP342X_CONF_MODE_ONESHOT
rate_12bit = MCP342X_CONF_SIZE_12BIT
rate_14bit = MCP342X_CONF_SIZE_14BIT
rate_16bit = MCP342X_CONF_SIZE_16BIT 
gain = MCP342X_CONF_GAIN_1X
rate = rate_14bit
VRef = 2.048

airflow_only = True if (len(sys.argv) > 1) and (sys.argv[1] == "airflow") else False
airflow_channel = channel1 if airflow_only is True and sys.argv[1] == "1" else channel3

def remove_duplicate_lines(filename):
	# Read the content of the file into a list
	with open(filename, 'r') as file:
		lines = file.readlines()

	# Create a set to store unique lines
	unique_lines = set()

	# Filter out duplicate lines
	filtered_lines = []
	for line in lines:
		line = line.strip()  # Remove leading/trailing whitespace
		if line not in unique_lines:
			unique_lines.add(line)
			filtered_lines.append(line)

	# Write the filtered lines back to the same file
	with open(filename, 'w') as file:
		file.write('\n'.join(filtered_lines))

input_file_path = '/home/pi/bcMeterConf.py'
remove_duplicate_lines(input_file_path)

files = os.listdir("/home/pi")

for file in files:
	file_path = os.path.join("/home/pi", file)
	os.chmod(file_path, 0o777) #dont try this at home

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

online = check_connection()
logger.debug("We can ping Google: %s", online)





try:
	import adafruit_sht4x
except ImportError:
	if (online is True):
		logger.debug("installing sht4x interface")
		proc = subprocess.Popen(["pip3", "install", "adafruit-circuitpython-sht4x"])
		proc.communicate()
		import adafruit_sht4x
	else:
		logger.debug("need to be online to install sht library first!")

if (airflow_only is False):
	try:
		import pigpio
	except ImportError:
		if (online is True):
			logger.debug("installing pigpio")
			proc = subprocess.Popen(["sudo", "apt-get","-y", "install", "pigpio", "python3-pigpio"])
			proc.communicate()
			sleep(0.5)
			try:
			# Set system-wide environment variables
				with open('/etc/environment', 'a') as f:
					f.write('PIGPIO_ADDR=soft\n')
					f.write('PIGPIO_PORT=8888\n')

				logger.debug("System-wide environment variables set successfully.")
			except Exception as e:
				logger.error(f"Error setting system-wide environment variables: {str(e)}")

			import pigpio
		else:
			logger.error("need to be online to install pigpio first!")


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
	if (online is True):
		logger.debug("installing scipy")
		proc = subprocess.Popen(["sudo", "apt-get","-y", "install", "python3-scipy"])
		proc.communicate()
		sleep(0.5)
		import scipy
	else:
		logger.error("need to be online to install scipy first!")



try:
	sht = adafruit_sht4x.SHT4x(i2c)
	sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
	temperature, relative_humidity = sht.measurements
	logger.debug("Temperature: %0.1f C" % temperature)
	logger.debug("Humidity: %0.1f %%" % relative_humidity)

	sht40_i2c = True
except Exception as e:
	sht40_i2c = False
	logger.error("Error: %s", e)





def startUp():
	global MCP342X_DEFAULT_ADDRESS, debug, airflow_sensor_bias
	airflow_sensor_bias = -1
	read_airflow_sensor_bias = read_adc(MCP342X_DEFAULT_ADDRESS,1)
	print("AF sens bias ", airflow_sensor_bias)
	if (airflow_only is False):
		pi.set_PWM_dutycycle(infrared_led_control, led_brightness)
		GPIO.setup(infrared_led_control, GPIO.OUT)
		GPIO.setup(1,GPIO.OUT)
		GPIO.setup(23,GPIO.OUT)
		GPIO.setup(BUTTONPIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
		pump_test()


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

	logger.debug("ADC found at Address: %s", hex(MCP342X_DEFAULT_ADDRESS))
	return(MCP342X_DEFAULT_ADDRESS)


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
	sleep(mcp_sps*1.4) #overhead seem to be necessary sometimes! better sleep more than less else buffer is clogged and we get same values for different channels

	data = bus.read_i2c_block_data(MCP342X_DEFAULT_ADDRESS, channel, 2)

	voltage = ((data[0] << 8) | data[1])
	if voltage >= 32768:
		voltage = 65536 - voltage
	voltage = (2 * VRef * voltage) / (2 ** N)
	return round(voltage,5)


def read_adc(mcp_i2c_address, sample_time):
	global MCP342X_DEFAULT_ADDRESS, airflow_only, airflow_sensor, airflow_channel, airflow_sensor_bias
	MCP342X_DEFAULT_ADDRESS = mcp_i2c_address
	airflow_sample_voltage = voltage_channel1 = voltage_channel3 = voltage_channel2 = sum_channel1 = sum_channel2 = sum_channel3 = 0
	average_channel1 = average_channel2 = average_channel3 = airflow_avg = 0
	airflow_sample_index = 1
	i=j=0

	start = time()
	last_check_time = time()
	airflow_samples_to_take = 1	if airflow_only is False else 200
	check_interval = 1


	while ((time()-start)<sample_time-0.25):

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


			if (airflow_sensor_bias == -1):
				airflow_sensor_bias = 0.5-average_channel3
			if (average_channel3 >= 2.047):
				logger.debug("airflow over sensor limit")
			sum_channel3+=average_channel3
			current_airflow=round(airflow_by_voltage(average_channel3, af_sensor_type),4)
			
			#blink_led(235)
			if (airflow_sensor is True) and (airflow_sensor_bias != -1):
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
			print(f"{i}, {sum_channel1/i}, {sum_channel2/i}, {average_channel3}")
			pass
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
	if (airflow_only is True) or (debug is True):
		#print("\033c", end="", flush=True)
		#print(voltage, airflow_sensor_bias)
		pass
	airflow_sensor_bias = 0 #override
	# Define the table data (replace with your actual table) # valid for OMRON D6F P0001A1 with 100ml; due to limitations of ADC only 77ml max
	if (sensor_type == 0):
		table = {
			0.5: 0.000,
			2.5: 0.100
		}

	if (sensor_type == 1):
	# Define the table data (replace with your actual table) # valid for OMRON D6F P0010A2 with 1000ml; due to limitations of ADC only 473ml max
		table = {
			0.5-airflow_sensor_bias:0,
			0.695-airflow_sensor_bias:0.04,
			0.75-airflow_sensor_bias:0.05,
			0.86-airflow_sensor_bias:0.1,
			0.94-airflow_sensor_bias:0.13,
			1.21-airflow_sensor_bias:0.15,
			1.3-airflow_sensor_bias:0.26,
			1.45-airflow_sensor_bias:0.31,
			2.5-airflow_sensor_bias:1


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
			return 2.5  # Voltage is outside the range of the table
		
		lower_voltage = max(v for v in voltages if v <= voltage)
		upper_voltage = min(v for v in voltages if v >= voltage)
		
		# Linear interpolation formula
		lower_value = table[lower_voltage]
		upper_value = table[upper_voltage]
		interpolated_value = lower_value + (voltage - lower_voltage) * (upper_value - lower_value) / (upper_voltage - lower_voltage)
		#if ((airflow_sensor == 1) and (interpolated_value > 0.47)) or ((airflow_sensor == 0 and interpolated_value>0.075)):
		#	interpolated_value = 9999
		return interpolated_value



def get_sensor_values(MCP342X_DEFAULT_ADDRESS,sample_time):
	main_sensor_value = reference_sensor_value = airflow_sensor_value = 0
	sensor_values = read_adc(MCP342X_DEFAULT_ADDRESS, sample_time)
	main_sensor_value = sensor_values[0]
	reference_sensor_value = sensor_values[1]
	airflow_sensor_value = sensor_values[2]
	return main_sensor_value, reference_sensor_value, airflow_sensor_value

def set_pwm_dutycycle(pump_dutycycle):
    pi.set_PWM_dutycycle(12, pump_dutycycle)

def check_airflow(current_mlpm):
	global pump_dutycycle, reverse_dutycycle, zero_airflow, airflow_only
	desired_airflow_in_mlpm = bcMeterConf.airflow_per_minute
	disable_pump_control = True if airflow_only is True else False
	
	if(disable_pump_control is False):
		if (current_mlpm<0.002) and (desired_airflow_in_mlpm>0):
			zero_airflow+=1
			if (zero_airflow==10):
				logger.debug("resetting pump... no airflow measured")
				pump_test()
				sleep(1)
				zero_airflow=0
				return

		if (current_mlpm<desired_airflow_in_mlpm):
			if (reverse_dutycycle is True):
				pump_dutycycle-=1
			else:
				pump_dutycycle+=1

		if (current_mlpm>desired_airflow_in_mlpm):
			if (reverse_dutycycle is True):
				pump_dutycycle+=1
			else:
				pump_dutycycle-=1
		if (pump_dutycycle<=0): pump_dutycycle=0
		if (pump_dutycycle>=pump_PWM_range): pump_dutycycle=pump_PWM_range
		Thread(target=set_pwm_dutycycle, args=(pump_dutycycle,)).start()

		#pi.set_PWM_dutycycle(12, pump_dutycycle) #PUT INTO OWN THREAD - TIME BLOCKING !!!

	if (use_display is True):
		show_display(str(round(current_mlpm*1000)) + "ml/min",2,False)
	if (debug is True):
		if (use_display is True):
			show_display(str(round(current_mlpm*1000)) + "ml/min" + f" {pump_dutycycle} ",2,False)
		print("current_mlpm", round(current_mlpm*1000,2), "desired_airflow_in_mlpm", round(desired_airflow_in_mlpm*1000,2), "pump_dutycycle", pump_dutycycle)
		pass


def pump_test():
	#logger.debug("Reset Pump")
	if (reverse_dutycycle is True):
		for cyclepart in range(1,11):
			pi.set_PWM_dutycycle(12, pump_PWM_range/cyclepart)
			sleep(0.12)
	else:
		for cyclepart in range(1,11):
			try:
				pi.set_PWM_dutycycle(12, cyclepart*10*2.55)
				sleep(0.12)
			except Exception as e:
				logger.error(e)
'''	pi.set_PWM_dutycycle(12, 0)
	sleep(5)
	pi.set_PWM_dutycycle(12, pump_PWM_range/2)
	sleep(5)
'''



if sht40_i2c is False:
	class TemperatureSensor:
		RETRY_INTERVAL = 0.5
		RETRY_COUNT = 10
		device_file_name = None
		global ds18b20
		def __init__(self, channel: int):
			GPIO.setmode(GPIO.BCM)
			GPIO.setup(channel, GPIO.IN)
			GPIO.setup(1,GPIO.OUT)
			GPIO.setup(23,GPIO.OUT)
			
		#def __del__(self):
			#GPIO.cleanup()

		@staticmethod
		def read_device() -> typing.List[str]:
			try:
				device_file_name = glob.glob('/sys/bus/w1/devices/28*')[0] + '/w1_slave'
			except Exception as e:
				logger.error(f"Temperature Sensor Error {e}")
			if device_file_name is not None:
				with open(device_file_name, 'r') as fp:
					return [line.strip() for line in fp.readlines()]
				ds18b20 = True

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
			logger.error(f"Cannot read temperature (tried {self.RETRY_COUNT} times with an interval of {self.RETRY_INTERVAL})")
			


def get_location_from_ip():
	import json
	import requests 
	my_ip = requests.get('https://api.ipify.org').text
	my_loc = requests.get('https://ipinfo.io/'+my_ip).text
	my_loc = json.loads(my_loc)
	my_lat =  float(my_loc['loc'].split(',')[0])
	my_lon = float(my_loc['loc'].split(',')[1])
	return [my_lat,my_lon]



def button_pressed():
	input_state = GPIO.input(16)
	if input_state == False:
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
			row['BCngm3'] = str(filtered_bcngm3_values[i])  # Convert back to string for writing to CSV

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


def bcmeter_main():
	global airflow_sensor, temperature_to_keep, airflow_sensor_bias, session_running_since, sender_password
	compair_offline_logging = False
	if (airflow_only is True):
		get_sensor_values(MCP342X_DEFAULT_ADDRESS, 86400*31)
		return
	last_email_time = time()
	first_value = True
	filter_status = samples_taken = sht_humidity=delay=airflow_sensor_value=reference_sensor_value=reference_sensor_bias=main_sensor_bias=bcmRefFallback=bcmSenRef=reference_sensor_value_current=main_sensor_value_current=main_sensor_value_last_run=attenuation_last_run=BCngm3_unfiltered=BCngm3_unfilteredpos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=temperature_current=bcm_temperature_last_run=attenuation_coeff=absorption_coeff=0
	notice = devicename
	volume_air_per_sample = calibrated = absorb = main_sensor_value = attenuation = attenuation_current = 0.0000
	today = str(datetime.now().strftime("%y-%m-%d"))
	session_running_since = datetime.now()
	now = str(datetime.now().strftime("%H:%M:%S"))
	logFileName =(str(today) + "_" + str(now) + ".csv").replace(':','')
	header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3_unfiltered;BCngm3;Temperature;notice;main_sensor_bias;reference_sensor_bias;sampleDuration;sht_humidity;airflow"
	compair_offline_log_header="timestamp,bcngm3,atn,bcmsen,bcmref,bcmtemperature, location, filter_status"
	new_log_message="Started log " + str(today) + " " + str(now) + " " + str(bcMeter_version) + " " + str(logFileName)

	logger.debug(new_log_message)
	createLog(logFileName,header)
	logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3_unfiltered) + ";"+ str(BCngm3_unfiltered) + ";" + str(temperature_current) + ";" + str(notice) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(sht_humidity) + ";" + str(volume_air_per_sample) 
	online = check_connection()
	get_location = getattr(bcMeterConf, 'get_location', False) 
	location = getattr(bcMeterConf, 'location', False)
	if (online is True) and (get_location is True) and (location[0] == 0.00):
		location = get_location_from_ip()
		if not 'location' in open('bcMeterConf.py').read():
			with open('bcMeterConf.py', 'a') as f:
				f.write("location=" + str(location) + "#Location of the bcMeter. Keep syntax exactly like that [lat,lon]#session")
		else:
			with open('bcMeterConf.py', 'r') as f:
				lines = f.readlines()
			for i, line in enumerate(lines):
				if line.startswith('location'):
					lines[i] = "location=" + str(location) + "#Location of the bcMeter. Keep syntax exactly like that [lat,lon]#session"
			with open('bcMeterConf.py', 'w') as f:
				f.writelines(lines)
		logger.debug("using lat lon %s", location)
		
	if (compair_upload is True):
		import compair_frost_upload
	if debug is True:
		print("Airflow Sensor bias: ",  airflow_sensor_bias)

	y = 0
	while(True):
		importlib.reload(bcMeterConf)
		mail_sending_interval = getattr(bcMeterConf, 'mail_sending_interval', 6)
		#mail_sending_interval = 6 if mail_sending_interval < 6 else (24 if mail_sending_interval > 24 else mail_sending_interval)
		led_brightness = getattr(bcMeterConf, 'led_brightness', 100)
		sample_time = bcMeterConf.sample_time
		pi.set_PWM_dutycycle(infrared_led_control, led_brightness)
		start = time()
		if (samples_taken == 0) and (sample_time >60):
			sample_time=60
		samples_taken+=1
		sensor_values=get_sensor_values(MCP342X_DEFAULT_ADDRESS, sample_time)
		main_sensor_value = sensor_values[0]
		reference_sensor_value = sensor_values[1]
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
			airflow_per_minute = bcMeterConf.airflow_per_minute 
			volume_air_per_sample=(bcMeterConf.sample_time/60)*airflow_per_minute #liters of air between samples
		main_sensor_value_current=main_sensor_value#-main_sensor_bias
		reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
		if (ds18b20 is True):
			temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
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
		if (current_time - last_email_time >= mail_sending_interval*60*60) and (samples_taken>1):
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
			shutdown("PUMP MALFUNCTION")
			#delay = time() - start
			#volume_air_per_sample=bcMeterConf.airflow_per_minute*(delay/60)


		attenuation_coeff = sample_spot_areasize*((attenuation_current-attenuation_last_run)/100)/volume_air_per_sample	
		absorption_coeff = attenuation_coeff/bcMeterConf.filter_scattering_factor
		BCngm3_unfiltered = int((absorption_coeff / sigma_air_880nm)*bcMeterConf.device_specific_correction_factor) #bc nanograms per m3
		#logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3_unfiltered) + ";" + str(round(temperature_current,1)) + ";" + str(notice) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(round(sht_humidity,1))
		if (samples_taken>1) and (airflow_only is False):
			with open("/home/pi/logs/" + logFileName, "a") as log:
				logString = f"{datetime.now().strftime('%d-%m-%y')};{datetime.now().strftime('%H:%M:%S')};{reference_sensor_value_current};{main_sensor_value_current};{attenuation_current};{attenuation_coeff};{BCngm3_unfiltered};{BCngm3_unfiltered};{round(temperature_current, 1)};{notice};{main_sensor_bias};{reference_sensor_bias};{round(delay, 1)};{round(sht_humidity, 1)};{round(airflow_per_minute,3)}"
				log.write(logString+"\n")

			kernel = 5
			if (samples_taken<kernel):
				kernel = samples_taken

			filter_values("/home/pi/logs/" + logFileName, kernel)

			log_file_path = "/home/pi/logs/" + logFileName
			column_index = 7  
			last_six_values = []

			with open(log_file_path, 'r') as log_file:
				for line in log_file:
					columns = line.strip().split(';')
					try:
						value = float(columns[7])  # Index 7 corresponds to the "BCngm3" column
						last_six_values.append(value)
					except (ValueError, IndexError):
						pass

			average = sum(last_six_values[-12:]) / min(12, len(last_six_values))

			if (use_display is True):
				show_display(f"{int(average)} ngm3/hr", False, 0)
	

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
		
def housekeeping():		
	global temperature_to_keep, session_running_since
	temperature_to_keep = 35
	while (True):
		if (use_display is True):
			now = datetime.now()
			time_diff = now - session_running_since
			hours, remainder = divmod(time_diff.seconds, 3600)
			minutes, seconds = divmod(remainder, 60)
			hours = "0"+ str(hours) if hours<9 else hours
			minutes = "0"+str(minutes) if minutes<9 else minutes
			if (minutes != "00"):
				show_display("Running: "+ f"{hours}:{minutes}",1,False)
			else:
				show_display("Just started...", 1, False)
		importlib.reload(bcMeterConf)
		if (airflow_sensor is False):
			pump_dutycycle = getattr(bcMeterConf,'pump_dutycycle',20)
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
				if (ds18b20 is True):
					temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
				else:
					temperature_current = 1
					skipheat=True	
		if (ds18b20 is True):
			temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
		heating = getattr(bcMeterConf, 'heating', False)
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


def blink_led(airflow):
	airflow = 123

	GPIO.output(R_PIN, GPIO.HIGH)  # Change LOW to HIGH
	GPIO.output(G_PIN, GPIO.HIGH)  # Change LOW to HIGH
	GPIO.output(B_PIN, GPIO.HIGH)  # Change LOW to HIGH

	red_blinks = airflow // 100
	green_blinks = (airflow - (red_blinks * 100)) // 10
	blue_blinks = airflow - red_blinks * 100 - green_blinks * 10

	blink_duration = 0.5

	for _ in range(red_blinks):
		logger.debug("blink red %s", red_blinks)
		GPIO.output(R_PIN, GPIO.LOW)  # Change HIGH to LOW
		sleep(blink_duration)
		GPIO.output(R_PIN, GPIO.HIGH)  # Change LOW to HIGH
		sleep(blink_duration)

	sleep(blink_duration * 2)

	for _ in range(green_blinks):
		logger.debug("blink green %s", green_blinks)
		GPIO.output(G_PIN, GPIO.LOW)  # Change HIGH to LOW
		sleep(blink_duration)
		GPIO.output(G_PIN, GPIO.HIGH)  # Change LOW to HIGH
		sleep(blink_duration)

	sleep(blink_duration * 2)

	for _ in range(blue_blinks):
		logger.debug("blink blue %s", blue_blinks)
		GPIO.output(B_PIN, GPIO.LOW)  # Change HIGH to LOW
		sleep(blink_duration)
		GPIO.output(B_PIN, GPIO.HIGH)  # Change LOW to HIGH
		sleep(blink_duration)

	GPIO.output(R_PIN, GPIO.HIGH)  # Change LOW to HIGH
	GPIO.output(G_PIN, GPIO.HIGH)  # Change LOW to HIGH
	GPIO.output(B_PIN, GPIO.HIGH)  # Change LOW to HIGH




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



def shutdown(reason):
	global reverse_dutycycle

	print(reason)
	if (use_display is True):
		show_display("Goodbye",0,True)
		show_display(f"{reason}",1,True)
		show_display("",2,True)
	logger.debug(reason)
	if (reverse_dutycycle is False):
		pi.set_PWM_dutycycle(12, 0)
	else:
		pi.set_PWM_dutycycle(12, pump_PWM_range)

	#sleep(1)
	#pi.stop()
	if (airflow_only is False):
		subprocess.Popen(["sudo", "killall", "pigpiod"]).communicate
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


	print("\nWhen ready again, you may restart the script with 'python3 bcMeter.py' or just reboot the device itself")
	sys.exit(1)

'''
	service_name = "bcMeter.service"

	# Use subprocess to stop the service
	try:
		subprocess.run(["sudo", "systemctl", "stop", service_name], check=True)
		logger.debug(f"Service {service_name} stopped successfully.")
	except subprocess.CalledProcessError as e:
		logger.error(f"Failed to stop service {service_name}: {e}")
'''	



if __name__ == '__main__':

	if (use_display is True):
		show_display(f"Sampling...", False, 0)
	try:
		if debug is True:
			print("Init")

		find_mcp_adress()
		startUp()

		if debug:
			print("starting main thread")
		sampling_thread = Thread(target=bcmeter_main)
		sampling_thread.start()
		if (airflow_only is False):
			if debug:
				print("starting housekeeping thread")
			heating_thread = Thread(target=housekeeping)
			heating_thread.start()
		if debug:
			print("everything set up and running")



	except KeyboardInterrupt: 
		shutdown("CTRL+C")

