
import json, socket, os, busio, logging, subprocess, re, time 
from board import I2C, SCL, SDA
from datetime import datetime
import RPi.GPIO as GPIO 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import platform
import os
import shutil

bcMeter_shared_version = "0.1 2025-04-04"

i2c = busio.I2C(SCL, SDA)
base_dir = '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'
hostname = socket.gethostname()

CONNECTION_PRIMARY = {"host": "www.google.com", "port": 80}
CONNECTION_TIMEOUT = 3
CONNECTION_TRIES = 3
CONNECTION_RETRY_SLEEP = 2

def check_connection():
	result = subprocess.run(['ip', 'route'], capture_output=True, text=True)
	if "default" not in result.stdout:
		return False
	for attempt in range(CONNECTION_TRIES):
		try:
			start_time = time.time()
			s = socket.create_connection((CONNECTION_PRIMARY["host"], CONNECTION_PRIMARY["port"]), 
										timeout=CONNECTION_TIMEOUT)
			response_time = (time.time() - start_time) * 1000  # Convert to ms
			s.close()
			#logger.debug(f"{CONNECTION_PRIMARY['host']} pinged in {response_time:.2f} ms")
			return True
		except Exception:
			if attempt < CONNECTION_TRIES - 1:
				time.sleep(CONNECTION_RETRY_SLEEP)

			
	return False



def setup_logging(log_entity):
	# Create the log folder if it doesn't exist
	log_folder = base_dir + '/maintenance_logs/'
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

logger = setup_logging('bcMeter_shared')


def run_command(command):
	try:
		result = subprocess.run(command.split(), capture_output=True, text=True)
		if result.returncode != 0:
			logger.error(f"Error in {command}: {result.stderr}")
			return None
		return result.stdout.strip()
	except Exception as e:
		logger.error(f"Exception running command '{command}': {e}")
		return None

def get_network_name():
	"""Gets the active network SSID using platform-specific commands."""
	try:
		system = platform.system()
		if system == "Windows":
			cmd = "netsh wlan show interfaces"
			output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
			for line in output.split('\n'):
				if "SSID" in line and ":" in line:
					return line.split(":")[1].strip()
		elif system == "Darwin": # macOS
			cmd = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I"
			output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
			for line in output.split('\n'):
				if "SSID" in line and ":" in line:
					return line.split(":")[1].strip()
		elif system == "Linux":
			cmd = "iwgetid -r"
			output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
			return output.strip()
	except (subprocess.CalledProcessError, FileNotFoundError):
		return 'Could not determine'
	return 'Could not determine'

def get_basic_info(base_dir='.'):
	"""Gather useful system information using only standard library."""
	try:
		hostname = socket.gethostname()
		
		lan_ip = '127.0.0.1'
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect(("8.8.8.8", 80))
				lan_ip = s.getsockname()[0]
		except OSError:
			pass

		total, used, free = shutil.disk_usage("/")
		
		log_dir = os.path.join(base_dir, 'logs/')
		os.makedirs(log_dir, exist_ok=True)
		log_size = sum(
			os.path.getsize(os.path.join(log_dir, f))
			for f in os.listdir(log_dir)
			if os.path.isfile(os.path.join(log_dir, f))
		)

		info = {
			'hostname': hostname,
			'ip_address': lan_ip,
			'platform': platform.platform(),
			'python_version': platform.python_version(),
			'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
			'disk_total': f"{total // (2**30)} GB",
			'disk_free': f"{free // (2**30)} GB",
			'disk_used': f"{(used / total) * 100:.1f}%",
			'log_dir_size': f"{log_size / (2**20):.1f} MB"
		}
		return info
	except Exception as e:
		return {'error': str(e)}

def convert_config_to_json():
	config_variables = {}
	with open(base_dir + '/bcMeterConf.py', 'r') as file:
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

	with open(base_dir + '/bcMeter_config.json', 'w') as json_file:
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


def config_json_handler():
	with open(base_dir + '/bcMeter_config.json', 'r') as json_file:
		full_config = json.load(json_file)
		flattened_config = {key: value['value'] for key, value in full_config.items()}
		return flattened_config

def update_config(*, variable, value=None, description=None, type=None, parameter=None):
	with open(base_dir + '/bcMeter_config.json', 'r+') as json_file:
		config = json.load(json_file)
		
		is_new_variable = variable not in config
		
		if is_new_variable:
			if any(field is None for field in [value, description, type, parameter]):
				logger.error(f"Creating new variable '{variable}' requires all fields: value, description, type, and parameter")
				raise ValueError(f"Missing required fields for new variable '{variable}'")
				
			config[variable] = {
				'value': value,
				'description': description,
				'type': type,
				'parameter': parameter
			}
		else:
			if value is not None:
				config[variable]['value'] = value
			if description is not None:
				config[variable]['description'] = description
			if type is not None:
				config[variable]['type'] = type
			if parameter is not None:
				config[variable]['parameter'] = parameter
		
		json_file.seek(0)
		json.dump(config, json_file, indent=4)
		json_file.truncate()

# Usage:
try:
	config = config_json_handler()
except FileNotFoundError:
	config = convert_config_to_json()
	config = config_json_handler()
except Exception as e:
	print(f"Error while loading config: {e}")
	
sender_password = config.get('email_service_password', 'email_service_password')
mail_logs_to = config.get('mail_logs_to',"your@email.address")

def send_email(payload):
	"""
	Send email notifications based on payload type.
	
	Args:
		payload (str): Type of email to send ("Filter", "Log", "Pump", or "Onboarding")
	"""
	# Email configuration

	if sender_password=="email_service_password" or sender_password =="" or mail_logs_to.split(",")[0] == "your@email.address":
		logger.error("No mailing password or receiver set")
		return

	smtp_server = "live.smtp.mailtrap.io"
	smtp_port = 587
	sender_email = f"{hostname} Status <mailtrap@bcmeter.org>"
	email_receiver_list = mail_logs_to.split(",")
	subject_prefix = "bcMeter Status Mail: "

	# Prepare email content based on payload type
	templates = {
		"Filter": {
			"subject": "Change filter!",
			"body": "Hello dear human, please consider changing the filter paper the next time you're around, thank you!",
			"needs_attachment": False,
			"log_message": "Filter Change Mail sent"
		},
		"Log": {
			"subject": "Log file",
			"body": "Hello dear human, please find attached the log file",
			"needs_attachment": True,
			"log_message": "Log Mail sent"
		},
		"Pump": {
			"subject": "Pump Malfunction",
			"body": "I do not register any airflow. Please check the connections and if the pump is working",
			"needs_attachment": True,
			"log_message": "Error mail (Pump Malfunction) sent"
		},
		"Onboarding": {
			"subject": "Device Information",
			"body": None,  # Will be set dynamically
			"needs_attachment": False,
			"log_message": "Onboarding information sent"
		}
	}

	if payload not in templates:
		logger.error(f"Unknown payload type: {payload}")
		return

	template = templates[payload]
	
	# Create message
	message = MIMEMultipart()
	message["From"] = sender_email
	message["Subject"] = subject_prefix + template["subject"]

	# Special handling for onboarding payload
	if payload == "Onboarding":
		body = "bcMeter Device Information:\n\n"
		try:
			info = get_basic_info()

			if 'error' in info:
				raise Exception(info['error'])

			body += f"Network: {info['network_name']}\n"
			body += f"- Hostname: {info['hostname']}\n"
			body += f"- Access interface in LAN by: http://{info['ip_address']}\n\n"
			
			body += "System:\n"
			body += f"- Platform: {info['platform']}\n"
			body += f"- Python Version: {info['python_version']}\n"
			body += f"- Time: {info['time']}\n\n"
			
			body += "Storage:\n"
			body += f"- Total Disk Space: {info['disk_total']}\n"
			body += f"- Free Disk Space: {info['disk_free']}\n"
			if info['disk_free'] == "0 GB":
				body += f"-- Use the UPDATE function to expand partition! \n"
			body += f"- Disk Usage: {info['disk_used']}\n"
			body += f"- Log Directory Size: {info['log_dir_size']}\n"
		except Exception as e:
			# logger.error(f"Failed to gather system information: {str(e)}")
			body += f"Failed to gather system information: {e}"
	else:
		body = template["body"]

	message.attach(MIMEText(body, "plain"))

	# Add attachment if needed
	if template["needs_attachment"]:
		try:
			file_path = base_dir + "/logs/log_current.csv"
			current_time = datetime.now().strftime("%y%m%d_%H%M")
			send_file_as = f"{hostname}_{current_time}.csv"
			
			with open(file_path, "rb") as file:
				attachment = MIMEApplication(file.read(), Name=send_file_as)
				attachment["Content-Disposition"] = f"attachment; filename={send_file_as}"
				message.attach(attachment)
		except Exception as e:
			logger.error(f"Failed to attach file: {str(e)}")
			return

	# Log based on payload type
	if payload == "Pump":
		logger.error(template["log_message"])
	else:
		logger.debug(template["log_message"])

	# Send email to each recipient
	for receiver in email_receiver_list:
		message["To"] = receiver
		try:
			with smtplib.SMTP(smtp_server, smtp_port) as server:
				server.starttls()
				server.login("api", sender_password)
				server.sendmail(sender_email, receiver, message.as_string())
			logger.debug(f"Email sent successfully to {receiver}")
		except Exception as e:
			logger.error(f"Failed to send email to {receiver}: {str(e)}")



airflow_type = config.get('af_sensor_type', 1)
if config.get('airflow_sensor'):
	print(f"Using Airflow sensor type {airflow_type}")

def save_config_to_json(key, value=None, description=None, parameter_type=None, parameter_category=None):
	"""Saves or updates a configuration parameter in the JSON file."""
	# Load the existing configuration
	full_config = config_json_handler()
	
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
	with open(base_dir + '/bcMeter_config.json', 'w') as json_file:
		json.dump(full_config, json_file, indent=4)

		
def update_ssid_in_hostapd_conf(revert=False):
	with open('/etc/hostapd/hostapd.conf', 'r') as file:
		lines = file.readlines()

	updated_lines = []
	ssid_changed = False
	target_ssid = "ebcMeter" if not revert else "bcMeter"
	original_ssid = "bcMeter" if not revert else "ebcMeter"

	for line in lines:
		if line.startswith("ssid=") and line.split('=')[1].strip() == original_ssid:
			updated_lines.append(f"ssid={target_ssid}\n")
			ssid_changed = True
		else:
			updated_lines.append(line)

	if ssid_changed:
		try:
			with open('/etc/hostapd/hostapd.conf', 'w') as file:
				file.writelines(updated_lines)
		except Exception as e:
			print("SSID not changed, permission error")


is_ebcMeter = config.get('is_ebcMeter', False)

if (is_ebcMeter):
	update_ssid_in_hostapd_conf()
else:
	update_ssid_in_hostapd_conf(revert=True)


def get_bcmeter_start_time():
	try:
		# Run the systemctl command to get the status of the bcMeter service
		result = subprocess.run(['systemctl', 'show', 'bcMeter', '--property=ActiveEnterTimestamp'], 
								stdout=subprocess.PIPE, text=True, check=True)
		output = result.stdout.strip()
		
		# Parse the timestamp from the output
		if "ActiveEnterTimestamp" in output:
			timestamp_str = output.split('=')[1].strip()
			# Convert to datetime object
			bcmeter_start_time = datetime.strptime(timestamp_str, '%a %Y-%m-%d %H:%M:%S %Z')
			return bcmeter_start_time.strftime("%y%m%d_%H%M%S")
		else:
			return None
	except (subprocess.CalledProcessError, ValueError):
		return None



def manage_bcmeter_status(
	parameter=None,
	action='get',
	bcMeter_status=None,
	calibration_time=None,
	log_creation_time=None,
	hostname=None,  
	filter_status=None,
	in_hotspot=None
):
	"""
	Manage BCMeter status parameters including calibration time.
	
	Args:
		parameter (str, optional): Specific parameter to get. If None, returns full status.
		action (str): 'get' or 'set' to retrieve or update status.
		bcMeter_status (int, optional): Status code (0=stopped, 1=initializing, 2=running/online,
			3=running in hotspot, 4=hotspot only, 5=stopped by user, 6=stopped by script because of error)
		calibration_time (str, optional): Timestamp of last calibration in format "YYMMDD_HHMMSS"
		log_creation_time (str, optional): Log creation timestamp
		hostname (str, optional): Deprecated - hostname is now automatically set
		filter_status (int, optional): Filter status code (0-5)
		in_hotspot (boolean, optional):  true or false
	
	Returns:
		dict or any: Retrieved parameter(s) for 'get', None for 'set'
	
	Raises:
		ValueError: If invalid parameter requested or invalid action specified
	"""
	if_status_folder = base_dir + "/tmp/"
	file_path = if_status_folder + 'BCMETER_WEB_STATUS'
	log_file_path = base_dir + "/logs/log_current.csv"
	
	# Ensure default structure exists
	default_parameters = {
		'bcMeter_status': 0,
		'calibration_time': None,
		'log_creation_time': None,
		'hostname': socket.gethostname(),
		'filter_status': 0,
		'in_hotspot': False
	}
	
	try:
		if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
			with open(file_path, 'r') as file:
				parameters = json.load(file)
		else:
			parameters = {}
	except (FileNotFoundError, json.JSONDecodeError):
		parameters = {}
	
	# Ensure all default keys exist
	for key, value in default_parameters.items():
		if key not in parameters or parameters[key] is None:
			parameters[key] = value
	
	valid_params = list(default_parameters.keys())
	
	if action == 'get':
		if parameter and parameter not in valid_params:
			raise ValueError(f"Invalid parameter. Choose from: {valid_params}")
		parameters['hostname'] = socket.gethostname()
		return parameters if parameter is None else parameters.get(parameter, default_parameters.get(parameter))
		
	elif action == 'set':
		if log_creation_time is None:
			log_creation_time = get_bcmeter_start_time() if 'get_bcmeter_start_time' in globals() else None
			if log_creation_time is None:
				try:
					file_stat = os.stat(log_file_path)
					log_creation_time = datetime.fromtimestamp(file_stat.st_ctime).strftime("%y%m%d_%H%M%S")
				except FileNotFoundError:
					log_creation_time = None
		
		# Handle filter status
		if filter_status is not None:
			filter_status = min(max(0, filter_status), 5)
		
		update_dict = {
			k: v for k, v in {
				'bcMeter_status': bcMeter_status,
				'calibration_time': calibration_time,
				'log_creation_time': log_creation_time,
				'hostname': socket.gethostname(), 
				'filter_status': filter_status,
				'in_hotspot': in_hotspot
			}.items() if v is not None
		}
		
		parameters.update(update_dict)
		
		os.makedirs(if_status_folder, exist_ok=True)
		with open(file_path, 'w') as file:
			json.dump(parameters, file)
	else:
		raise ValueError("Invalid action. Use 'get' or 'set'")

		
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


def get_pi_revision():
	try:
		with open('/proc/cpuinfo', 'r') as f:
			for line in f:
				if line.startswith('Revision'):
					rev_code_str = line.split(':')[1].strip()
					rev_code = int(rev_code_str, 16)

					# The 'new_flag' bit (bit 23) tells us if it's the new-style code.
					new_flag = (rev_code >> 23) & 0x1
					if not new_flag:
						# Here you might want to handle old/legacy revision codes more fully,
						# but for illustration:
						return f"Legacy revision code (0x{rev_code:x})"

					# Bits 4-11 give the model
					model = (rev_code >> 4) & 0xFF
					# Bits 20-22 give the RAM size
					memory = (rev_code >> 20) & 0x7

					# This dictionary includes most Pi boards, including Pi 3, Zero 2 W, etc.
					models = {
						0x00: "A",
						0x01: "B",
						0x02: "A+",
						0x03: "B+",
						0x04: "2B",
						0x05: "Alpha (early prototype)",
						0x06: "Compute Module 1",
						0x08: "3B",
						0x09: "Zero",
						0x0a: "Compute Module 3",
						0x0c: "Zero W",
						0x0d: "3B+",
						0x0e: "3A+",
						0x10: "Compute Module 3+",
						0x11: "4B",
						0x13: "400",
						0x14: "Compute Module 4",
						0x15: "Zero 2 W",
						0x17: "5",
						0x18: "Compute Module 5",
						0x19: "500 (Pi 5 in keyboard form)",
						0x1a: "Compute Module 5 Lite",
					}

					# Bits 20-22 for memory size:
					#   0 => 256MB, 1 => 512MB, 2 => 1GB, 3 => 2GB,
					#   4 => 4GB,   5 => 8GB,   6 => 16GB, ...
					memory_map = {
						0: "256MB",
						1: "512MB",
						2: "1GB",
						3: "2GB",
						4: "4GB",
						5: "8GB",
						6: "16GB"
					}

					model_name  = models.get(model, "Unknown model")
					memory_size = memory_map.get(memory, "unknown RAM size")

					return f"Raspberry Pi {model_name} with {memory_size} RAM"

		return "No revision code found"
	except Exception as e:
		return f"Error reading revision: {str(e)}"

	   

def button_callback(channel):	
	global button_press_count, last_press_time
	current_time = time.time()
	if (last_press_time == 0):
		last_press_time = current_time
	if current_time - last_press_time >5:
		button_press_count=0
		last_press_time = current_time
	button_press_count += 1
	print(button_press_count, current_time-last_press_time)
	if button_press_count >5:
		print("invalid presses")
		button_press_count=0

	if (current_time - last_press_time < 3):
		if button_press_count >= 2:
			if not check_service_running('bcMeter'):
				print("Starting bcMeter by button")
				run_bcMeter_service()
			else:
				print("Stopping bcMeter by button")
				stop_bcMeter_service()		# Add your action here

		elif button_press_count == 5:
			# Action for triple press
			print("5 press detected")
			# Add your action here
	if current_time - last_press_time > 3:
		button_press_count = 0
		last_press_time = current_time
	time.sleep(0.5)



def button_thread():
	GPIO.add_event_detect(bcMeter_button_gpio, GPIO.FALLING, callback=button_callback)
	while True:
		time.sleep(1)  # Polling interval

# Start the button detection thread
#button_thread = Thread(target=button_thread)
#button_thread.daemon = True
#button_thread.start()

if int(airflow_type) == 9:
	from smbus2 import SMBus
	print("initializing honeywell")

	def read_airflow_ml(flow_range=750.0, sensor_address=0x49, smbus_ch=1, env_temp_c=20.0, env_pressure=1024.0, samples=200):
		"""
		Read airflow from Honeywell Zephyr sensor and return flow rate in ml/min.
		
		Args:
			flow_range (float): Sensor's full scale flow range in SCCM (default 750.0)
			sensor_address (int): I2C address of sensor (default 0x49)
			smbus_ch (int): I2C bus channel (default 1)
			env_temp_c (float): Environmental temperature in Celsius (default 20.0)
			env_pressure (float): Environmental pressure in hPa (default 1024.0)
			samples (int): Number of samples to average (default 500)
		
		Returns:
			float: Compensated flow rate in ml/min
			
		Raises:
			ValueError: If sensor not supported or invalid data received
		"""
		# Constants
		STD_TEMP_K = 273.15    # Standard temperature in Kelvin
		STD_PRESSURE = 1023.38 # Standard pressure in hPa
		
		# Validate sensor configuration
		supported_ranges = [50.0, 100.0, 200.0, 400.0, 750.0]
		supported_addresses = [0x49, 0x59, 0x69, 0x79]
		
		if flow_range not in supported_ranges or sensor_address not in supported_addresses:
			raise ValueError(f"Unsupported sensor configuration. Valid ranges: {supported_ranges}, "f"Valid addresses: [0x{x:02x} for x in {supported_addresses}]")

		# Initialize sensor
		with SMBus(smbus_ch) as bus:
			time.sleep(0.02)  # Startup time + safety
			bus.read_byte(sensor_address)
			time.sleep(0.035)  # Warm-up time + safety
			bus.read_byte(sensor_address)

		# Read and average flow measurements
		flow_sum = 0
		with SMBus(smbus_ch) as bus:
			for _ in range(samples):
				# Read 2 bytes of data
				raw_data = bus.read_i2c_block_data(sensor_address, 0, 2)
				digital_output = (raw_data[0] << 8) | raw_data[1]
				
				# Validate data (check if first two bits are 00)
				if digital_output & 0xc000:
					raise ValueError(f"Invalid sensor data: {hex(digital_output)}")
				
				# Convert to flow rate: Flow = FS_Flow * ((Digital_Output/16384) - 0.5)/0.4
				flow_rate = flow_range * ((digital_output/16384) - 0.5) / 0.4
				flow_sum += flow_rate
				time.sleep(0.001)  # Sensor update period

		# Calculate average flow rate
		avg_flow_sccm = flow_sum / samples / 1000
		
		# Temperature compensation
		env_temp_k = 273.15 + env_temp_c
		compensated_flow = avg_flow_sccm * (STD_PRESSURE * env_temp_k) / (env_pressure * STD_TEMP_K)
		
		# Convert SCCM to ml/min (they are equivalent units)
		return compensated_flow




import numpy as np
try:
	import pandas as pd
except:
	pass

def ona_filter(data_path, delta_atn_min=0.05, delimiter=';'):
	"""
	Implements the Optimized Noise-reduction Averaging (ONA) algorithm for reducing noise
	in Aethalometer black carbon data while preserving time resolution.
	
	This algorithm is based on the work by Hagler et al. (2011), which showed that
	using a minimum attenuation change (ΔATNmin) of 0.05 provided optimal noise reduction
	while preserving significant trends in the data.
	
	Simplified implementation for single-spot devices.
	
	Parameters:
	-----------
	data_path : str
		Path to the CSV file containing the data
	delta_atn_min : float, optional
		Minimum change in attenuation (ATN) required for averaging (default: 0.05)
	delimiter : str, optional
		Delimiter used in the CSV file (default: ';')
		
	Returns:
	--------
	None - File is processed in place with added ONA-filtered BC values
	"""
	# Load data
	try:
		df = pd.read_csv(data_path, delimiter=delimiter)
	except Exception as e:
		print(f"Error reading file: {e}")
		return
	
	df_original = df.copy()
	required_columns = ['bcmTime', 'bcmATN']
	
	bc_column = None
	for col_name in ['BCngm3_unfiltered', 'BCugm3_unfiltered']:
		if col_name in df.columns:
			bc_column = col_name
			break
			
	if bc_column is None:
		print("No BC concentration column found in the data")
		return
		
	if bc_column == 'BCngm3_unfiltered':
		output_column = 'BCngm3_ona'
	else:
		output_column = 'BCugm3_ona'
		
	for col in required_columns:
		if col not in df.columns:
			print(f"Required column '{col}' not found in the data")
			return
	
	n_rows = len(df)
	processed_values = np.zeros(n_rows)
	window_sizes = np.zeros(n_rows)
	
	if n_rows < 2:
		df[output_column] = df[bc_column].values
		df['ONA_window_size'] = 1
		df.to_csv(data_path, sep=delimiter, index=False)
		return
	
	i = 0
	while i < n_rows:
		start_idx = i
		start_atn = df['bcmATN'].iloc[i]
		end_idx = i + 1
		while end_idx < n_rows and df['bcmATN'].iloc[end_idx] - start_atn < delta_atn_min:
			end_idx += 1
		if end_idx >= n_rows:
			end_idx = n_rows - 1
		end_atn = df['bcmATN'].iloc[end_idx]
		last_valid_idx = end_idx
		for j in range(end_idx + 1, n_rows):
			if df['bcmATN'].iloc[j] <= end_atn:
				last_valid_idx = j
		window = df.iloc[start_idx:last_valid_idx + 1]
		avg_bc = window[bc_column].mean()
		window_size = len(window)
		for j in range(start_idx, last_valid_idx + 1):
			processed_values[j] = avg_bc
			window_sizes[j] = window_size
		
		i = last_valid_idx + 1
	
	df[output_column] = processed_values
	df['ONA_window_size'] = window_sizes
	df.to_csv(data_path, sep=delimiter, index=False)
'''	
	original_noise = calculate_noise(df_original[bc_column])
	processed_noise = calculate_noise(df[output_column])

	print(f"ONA Processing Summary:")
	print(f"  Original noise: {original_noise:.2f}")
	print(f"  Processed noise: {processed_noise:.2f}")
	print(f"  Noise reduction: {original_noise/processed_noise:.1f}x")
	print(f"  Avg window size: {window_sizes.mean():.1f} samples")
	print(f"  Max window size: {window_sizes.max():.0f} samples")

	neg_before = 100 * (df_original[bc_column] < 0).sum() / len(df_original)
	neg_after = 100 * (df[output_column] < 0).sum() / len(df)
'''	
def calculate_noise(data):
	return np.abs(np.diff(data)).mean()

def filter_values_ona(log, delta_atn_min=0.05):
	ona_filter(log, delta_atn_min=delta_atn_min, delimiter=';')



def adjust_airflow_dynamically(bc_concentration, af_sensor_type):
	if af_sensor_type == 0:
		MIN_AIRFLOW, MAX_AIRFLOW = 0.07, 0.075
	else:
		MIN_AIRFLOW, MAX_AIRFLOW = 0.1, 0.42

	if bc_concentration >= 2000:
		target_airflow = MIN_AIRFLOW
	elif bc_concentration >= 1000:
		target_airflow = MIN_AIRFLOW + (MAX_AIRFLOW - MIN_AIRFLOW) * 0.25
	elif bc_concentration >= 600:
		target_airflow = MIN_AIRFLOW + (MAX_AIRFLOW - MIN_AIRFLOW) * 0.5
	elif bc_concentration >= 200:
		target_airflow = MIN_AIRFLOW + (MAX_AIRFLOW - MIN_AIRFLOW) * 0.75
	else:
		target_airflow = MAX_AIRFLOW
	print(f"{target_airflow} target airflow")
	return round(target_airflow, 3)


def apply_dynamic_airflow(bc_concentration, config, override_airflow_flag, logger, af_sensor_type=1):

	if bc_concentration <= 0:
		return override_airflow_flag, None
	is_ebcMeter = config.get('is_ebcMeter', False)
	if is_ebcMeter:
		return override_airflow_flag, None
	if not hasattr(apply_dynamic_airflow, 'samples'):
		apply_dynamic_airflow.samples = []
	apply_dynamic_airflow.samples.append(bc_concentration)
	apply_dynamic_airflow.samples = apply_dynamic_airflow.samples[-4:]  # Keep last 4 samples
	avg_bc = sum(apply_dynamic_airflow.samples) / len(apply_dynamic_airflow.samples)
	try:
		current_airflow = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))
	except (ValueError, TypeError):
		logger.warning("Invalid airflow_per_minute value in config")
		current_airflow = 0.25
	target_airflow = adjust_airflow_dynamically(avg_bc, af_sensor_type)
	logger.info(f"Airflow adjusted: {current_airflow:.3f} → {target_airflow:.3f} L/min (BC={avg_bc} ng/m³)")
	return True, target_airflow