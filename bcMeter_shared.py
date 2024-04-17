
import json, socket, os, busio
from board import I2C, SCL, SDA
from datetime import datetime

# alternative check -- http/www on port 80 instead of dns on port 53
CONNECTION_TEST_HOST = "www.google.com" 
CONNECTION_TEST_PORT = 80
CONNECTION_TEST_TIMEOUT = 3     # socket timeout
CONNECTION_TEST_TRIES = 3       # number of attemps
CONNECTION_TEST_RETRY_SLEEP = 2 # in seconds
bcMeter_started = str(datetime.now().strftime("%y%m%d_%H%M%S"))
devicename = socket.gethostname()

i2c = busio.I2C(SCL, SDA)

def convert_config_to_json():
	config_variables = {}
	with open('/home/pi/bcMeterConf.py', 'r') as file:
		for line in file:
			# Ignore lines that do not contain variable assignments
			if '=' not in line or line.startswith('#'):
				continue

			# Extract the key, value, comment, and parameter type from each line
			parts = line.split('#', 2)
			key_value_part = parts[0].strip()
			key, value_str = key_value_part.split('=', 1)
			key = key.strip()
			value = eval(value_str.strip())  # Convert to appropriate Python type safely

			description = parts[1].strip() if len(parts) > 1 else ""
			param_type = parts[2].strip() if len(parts) > 2 else "unknown"

			# Evaluate the value to determine its type in JavaScript notation
			if isinstance(value, bool):
				js_type = "boolean"
			elif isinstance(value, int) or isinstance(value, float):
				js_type = "number"
			elif isinstance(value, str):
				js_type = "string"
			elif isinstance(value, list):
				js_type = "array"
			else:
				js_type = "unknown"

			# Structure the configuration data
			config_variables[key] = {
				"value": value,
				"description": description,
				"type": js_type, 
				"parameter": param_type
			}

	with open('/home/pi/bcMeter_config.json', 'w') as json_file:
		json.dump(config_variables, json_file, indent=4)

	return config_variables


def load_config_from_json():
	with open('/home/pi/bcMeter_config.json', 'r') as json_file:

		full_config = json.load(json_file)
		# Extract only the value for each setting, flattening the structure
		flattened_config = {key: value['value'] for key, value in full_config.items()}
		return flattened_config


try:
	config = load_config_from_json()
except FileNotFoundError:
	config = convert_config_to_json()
	config = load_config_from_json()



def check_connection():

	for _ in range(CONNECTION_TEST_TRIES):
		try:
			# Attempt to create a socket connection to the test host
			s=socket.create_connection((CONNECTION_TEST_HOST, CONNECTION_TEST_PORT), timeout=CONNECTION_TEST_TIMEOUT)
			s.close()
			return True			
		except Exception as e:
			if Exception is OSError:
				sleep(CONNECTION_TEST_RETRY_SLEEP)


	return False

def update_interface_status(status):
	# Define parameters
	'''
	0=stopped
	1=initializing 
	2=running and online
	3=running in hotspot
	4=hotspot only

	'''
	if_status_folder="/home/pi/tmp/"
	os.makedirs(if_status_folder, exist_ok=True)
	parameters = {
		"bcMeter_status": status,
		"log_creation_time": bcMeter_started,
		"hostname": devicename


	}
	# File path
	file_path = if_status_folder + 'BCMETER_WEB_STATUS'

	# Write parameters to JSON file
	with open(file_path, 'w') as file:
		json.dump(parameters, file)



use_display = config.get('use_display', False)

display_i2c_address = 0x3c
try:
	for device in range(128):
		try:
			# Attempt to read 1 byte from the device
			i2c.writeto(device, b'')
			# If successful, set the default address accordingly
			if hex(device) == display_i2c_address:
				use_display = True
		except OSError:
			pass
			

	if (use_display):
		from oled_text import OledText, Layout64, BigLine, SmallLine
		oled = OledText(i2c, 128, 64)

		oled.layout = {
			1: BigLine(5, 0, font="Arimo.ttf", size=20),
			2: SmallLine(5, 25, font="Arimo.ttf", size=14),
			3: SmallLine(5, 40, font="Arimo.ttf", size=14)
	}

except Exception as e:
	print("Display error:", e)

def show_display(message, line, clear):
	if (use_display is True):
		if clear is True:
			oled.clear()
		oled.text(str(message),line+1)
