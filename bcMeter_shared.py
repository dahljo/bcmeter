
import json, socket, os, busio, logging, subprocess, re
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

def setup_logging(log_entity):
	# Create the log folder if it doesn't exist
	log_folder = '/home/pi/maintenance_logs/'
	os.makedirs(log_folder, exist_ok=True)

	# Create a logger
	logger = logging.getLogger(f'{log_entity}_log')
	logger.setLevel(logging.DEBUG)  # Set the logging level to DEBUG

	# Clear the handlers to avoid duplicate log messages
	logger.handlers.clear()

	# Configure the log file with a generic name
	log_file_generic = os.path.join(log_folder, f'{log_entity}.log')
	if os.path.exists(log_file_generic):
		os.remove(log_file_generic)
	handler_generic = logging.FileHandler(log_file_generic)
	handler_generic.setLevel(logging.DEBUG)
	formatter_generic = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
	handler_generic.setFormatter(formatter_generic)

	# Configure the log file with a timestamp in its filename
	current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
	log_file_timestamped = os.path.join(log_folder, f'{log_entity}_{current_datetime}.log')
	handler_timestamped = logging.FileHandler(log_file_timestamped)
	handler_timestamped.setLevel(logging.DEBUG)
	formatter_timestamped = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
	handler_timestamped.setFormatter(formatter_timestamped)

	# Add both handlers to the logger
	logger.addHandler(handler_generic)
	logger.addHandler(handler_timestamped)

	# Maintain only a fixed number of log files (e.g., last 10)
	log_file_prefix = f'{log_entity}_'
	log_files = [f for f in os.listdir(log_folder) if f.startswith(log_file_prefix) and f.endswith('.log')]
	log_files.sort()
	if len(log_files) > 10:
		files_to_remove = log_files[:len(log_files) - 10]
		for file_to_remove in files_to_remove:
			os.remove(os.path.join(log_folder, file_to_remove))

	logger.debug(f"Logging setup complete for {log_entity}")

	return logger


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


def modify_parameter_type(json_file, modifications):
	with open(json_file, 'r') as file:
		data = json.load(file)	
	for variable, new_parameter in modifications:
		if variable in data:
			if (data[variable]['parameter'] != new_parameter):
				data[variable]['parameter'] = new_parameter
		else:
			pass
	with open(json_file, 'w') as file:
		json.dump(data, file, indent=4)




def load_config_from_json():
	modifications = [
		("compair_upload", "compair"),
		("get_location", "compair"),
		("location", "compair"),
		("send_log_by_mail", "email"),
		("mail_logs_to", "email"),
		("filter_status_mail", "email"),
		("mail_sending_interval", "email"),
		("email_service_password", "email"),
		("run_hotspot", "session"),
		("heating", "session"),

	]

	#try:
	#	modify_parameter_type("/home/pi/bcMeter_config.json", modifications)
	#except Exception as e:
	#	print(f"Cannot modify bcMeter_config.json: {e}")

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
except Exception as e:
	print(f"Error while loading config: {e}")


def save_config_to_json(key, value=None, description=None, parameter_type=None, parameter_category=None):
	"""Saves or updates a configuration parameter in the JSON file."""
	# Load the existing configuration
	full_config = load_config_from_json()
	
	# If the key exists, update the entry based on provided parameters
	if key in full_config:
		if value is not None:
			full_config[key]['value'] = value
		if description is not None:
			full_config[key]['description'] = description
		if parameter_type is not None:
			full_config[key]['type'] = parameter_type
		if parameter_category is not None:
			full_config[key]['parameter'] = parameter_category
	else:
		# If the key does not exist, create a new entry with default placeholders if parameters are not provided
		full_config[key] = {
			'value': value,
			'description': description or "No description provided",
			'type': parameter_type or "undefined",
			'parameter': parameter_category or "general"
		}
	
	# Write the updated configuration back to the JSON file
	with open('/home/pi/bcMeter_config.json', 'w') as json_file:
		json.dump(full_config, json_file, indent=4)

		


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



# Shorthanded revision table with grouped models, keys in lowercase
revision_table = {
	"0002": "Model B Rev 1",
	"0003": "Model B Rev 1 ECN0001 (no fuses, D14 removed)",
	"0004": "Model B Rev 2", "0005": "Model B Rev 2", "0006": "Model B Rev 2",
	"0007": "Model A", "0008": "Model A", "0009": "Model A",
	"000d": "Model B Rev 2 512MB", "000e": "Model B Rev 2 512MB", "000f": "Model B Rev 2 512MB",
	"0010": "Model B+", "0013": "Model B+", "900032": "Model B+",
	"0011": "Compute Module", "0014": "Compute Module (Embest, China)",
	"0012": "Model A+ 256MB", "0015": "Model A+ 256MB/512MB (Embest, China)",
	"a01041": "Pi 2 Model B v1.1 (Sony, UK)", "a21041": "Pi 2 Model B v1.1 (Embest, China)",
	"a22042": "Pi 2 Model B v1.2",
	"900092": "Pi Zero v1.2", "900093": "Pi Zero v1.3", "9000c1": "Pi Zero W",  # Lowercase "c"
	"a02082": "Pi 3 Model B 1.2 (Sony, UK)", "a22082": "Pi 3 Model B 1.2 (Embest, China)",
	"a020d3": "Pi 3 Model B+ 1.3 (Sony, UK)",
	"a03111": "Pi 4 1GB 1.1 (Sony, UK)", "b03111": "Pi 4 2GB 1.1 (Sony, UK)",
	"b03112": "Pi 4 2GB 1.2 (Sony, UK)", "b03114": "Pi 4 2GB 1.4 (Sony, UK)",
	"c03111": "Pi 4 4GB 1.1 (Sony, UK)", "c03112": "Pi 4 4GB 1.2 (Sony, UK)",
	"c03114": "Pi 4 4GB 1.4 (Sony, UK)", "d03114": "Pi 4 8GB 1.4 (Sony, UK)",
	"c03130": "Pi 400 4GB 1.0 (Sony, UK)", "902120": "Pi Zero 2 W 1GB 1.0 (Sony, UK)"
}

# Function to execute the pinout command and capture the output
def get_pinout_info():
	try:
		result = subprocess.run(['pinout'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
		if result.returncode != 0:
			print(f"Error running pinout command: {result.stderr}")
			return None
		return result.stdout
	except Exception as e:
		print(f"An error occurred: {e}")
		return None

# Function to find and print the model number based on the revision code
def find_model_number(pinout_output):
	# Search for the Revision line in the output
	match = re.search(r'Revision\s+:\s+(\w+)', pinout_output)
	if match:
		revision_code = match.group(1).lower()  # Convert to lowercase for consistency
		model = revision_table.get(revision_code)
		if model:
			return f"Revision code: {revision_code} - Model: {model}"
		else:
			return f"Revision code: {revision_code} not found in the table."
	else:
		return "No revision code found in the pinout output."


