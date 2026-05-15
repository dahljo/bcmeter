import json, socket, os, busio, logging, subprocess, re, time, csv
from board import I2C, SCL, SDA
from datetime import datetime
import RPi.GPIO as GPIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import platform
import shutil
import numpy as np

bcMeter_shared_version = "1.4.1 2026-05-15"

i2c = busio.I2C(SCL, SDA)
base_dir = '/home/bcmeter' if os.path.isdir('/home/bcmeter') else '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

hostname = socket.gethostname()

CONNECTION_PRIMARY = {"host": "www.google.com", "port": 80}
CONNECTION_TIMEOUT = 3
CONNECTION_TRIES = 3
CONNECTION_RETRY_SLEEP = 2

def check_connection(wifi_only=True):
	result = subprocess.run(['ip', 'route'], capture_output=True, text=True)
	if "default" not in result.stdout:
		return False
	if wifi_only:
		if "wlan0" not in result.stdout and "wlan1" not in result.stdout:
			return False
	for attempt in range(CONNECTION_TRIES):
		try:
			s = socket.create_connection((CONNECTION_PRIMARY["host"], CONNECTION_PRIMARY["port"]), timeout=CONNECTION_TIMEOUT)
			s.close()
			return True
		except Exception:
			if attempt < CONNECTION_TRIES - 1:
				time.sleep(CONNECTION_RETRY_SLEEP)
	return False

def setup_logging(log_entity):
	log_folder = base_dir + '/maintenance_logs/'
	os.makedirs(log_folder, exist_ok=True)
	logger = logging.getLogger(f'{log_entity}_log')
	logger.setLevel(logging.DEBUG)
	logger.handlers.clear()
	log_file_generic = os.path.join(log_folder, f'{log_entity}.log')
	if os.path.exists(log_file_generic):
		os.remove(log_file_generic)
	handler_generic = logging.FileHandler(log_file_generic)
	handler_generic.setLevel(logging.DEBUG)
	formatter_generic = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
	handler_generic.setFormatter(formatter_generic)
	current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
	log_file_timestamped = os.path.join(log_folder, f'{log_entity}_{current_datetime}.log')
	handler_timestamped = logging.FileHandler(log_file_timestamped)
	handler_timestamped.setLevel(logging.DEBUG)
	formatter_timestamped = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
	handler_timestamped.setFormatter(formatter_timestamped)
	logger.addHandler(handler_generic)
	logger.addHandler(handler_timestamped)
	prefix_to_match = f"{log_entity}_"
	log_files = []
	for f in os.listdir(log_folder):
		if not f.endswith('.log'):
			continue
		if not f.startswith(prefix_to_match):
			continue
		remainder = f[len(prefix_to_match):]
		if len(remainder) > 0 and remainder[0].isdigit():
			log_files.append(f)
	log_files.sort()
	if len(log_files) > 10:
		for file_to_remove in log_files[:len(log_files) - 10]:
			try:
				os.remove(os.path.join(log_folder, file_to_remove))
			except OSError:
				pass
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
	try:
		result = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			for line in result.stdout.splitlines():
				parts = line.split(":", 1)
				if len(parts) == 2 and parts[0] == "yes":
					return parts[1] or "Not connected"
	except Exception:
		pass
	try:
		ssid = subprocess.check_output("iwgetid -r", shell=True, text=True, stderr=subprocess.DEVNULL).strip()
		return ssid if ssid else "Not connected"
	except Exception:
		return "Could not determine"

def get_basic_info(base_dir_param='.'):
	try:
		hn = socket.gethostname()
		lan_ip = '127.0.0.1'
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect(("8.8.8.8", 80))
				lan_ip = s.getsockname()[0]
		except OSError:
			pass
		total, used, free = shutil.disk_usage("/")
		log_dir = os.path.join(base_dir_param, 'logs/')
		os.makedirs(log_dir, exist_ok=True)
		log_size = sum(os.path.getsize(os.path.join(log_dir, f)) for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f)))
		info = {
			'hostname': hn,
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
			if '=' not in line or line.startswith('#'):
				continue
			parts = line.split('#', 2)
			key_value_part = parts[0].strip()
			key, value_str = key_value_part.split('=', 1)
			key = key.strip()
			value = eval(value_str.strip())
			description = parts[1].strip() if len(parts) > 1 else ""
			param_type = parts[2].strip() if len(parts) > 2 else "unknown"
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
			config_variables[key] = {"value": value, "description": description, "type": js_type, "parameter": param_type}
	with open(base_dir + '/bcMeter_config.json', 'w') as json_file:
		json.dump(config_variables, json_file, indent=4)
	return config_variables

def modify_parameter_type(json_file, modifications):
	with open(json_file, 'r') as file:
		data = json.load(file)
	for variable, new_parameter in modifications:
		if variable in data:
			if data[variable]['parameter'] != new_parameter:
				data[variable]['parameter'] = new_parameter
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
				logger.error(f"Creating new variable '{variable}' requires all fields")
				raise ValueError(f"Missing required fields for new variable '{variable}'")
			config[variable] = {'value': value, 'description': description, 'type': type, 'parameter': parameter}
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

try:
	config = config_json_handler()
except FileNotFoundError:
	config = convert_config_to_json()
	config = config_json_handler()
except Exception as e:
	print(f"Error while loading config: {e}")
	config = {}

sender_password = config.get('email_service_password', 'email_service_password')
mail_logs_to = config.get('mail_logs_to', "your@email.address")

MAIL_COOLDOWN_DIR = "/dev/shm/bcmeter/mail_state/"

def get_last_mail_time(mail_type):
	path = f"{MAIL_COOLDOWN_DIR}last_{mail_type}"
	try:
		with open(path) as f:
			return float(f.read().strip())
	except:
		return 0

def set_last_mail_time(mail_type):
	os.makedirs(MAIL_COOLDOWN_DIR, exist_ok=True)
	with open(f"{MAIL_COOLDOWN_DIR}last_{mail_type}", 'w') as f:
		f.write(str(time.time()))

def can_send_mail(mail_type, min_interval_seconds):
	elapsed = time.time() - get_last_mail_time(mail_type)
	return elapsed >= min_interval_seconds

def get_session_flag(flag_name):
	path = f"{MAIL_COOLDOWN_DIR}{flag_name}"
	return os.path.exists(path)

def set_session_flag(flag_name):
	os.makedirs(MAIL_COOLDOWN_DIR, exist_ok=True)
	with open(f"{MAIL_COOLDOWN_DIR}{flag_name}", 'w') as f:
		f.write("1")

def _is_iot_available():
	try:
		from bcMeter_iot import is_iot_available
		return is_iot_available()
	except ImportError:
		return False

def _send_via_iot(payload, data=None):
	try:
		from bcMeter_iot import IoTUploader, get_recipients
		uploader = IoTUploader()
		recipients = get_recipients()

		if payload in ("Log", "Pump"):
			file_path = base_dir + "/logs/log_current.csv"
			if os.path.exists(file_path) and os.path.getsize(file_path) >= 500:
				result = uploader.upload_file(file_path, recipients)
			else:
				logger.warning(f"IoT fallback: log file too small or missing")
				result = False
		else:
			info = get_basic_info(base_dir)

			if payload == "Onboarding":
				sim_info = uploader.get_sim_info()
				notification = {
					'type': 'notification',
					'notification_type': 'Onboarding',
					'hostname': hostname,
					'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
					'connection': 'cellular',
					'operator': sim_info.get('operator', ''),
					'signal': sim_info.get('signal', 0),
					'ip': sim_info.get('ip', ''),
					'disk_free': info.get('disk_free', ''),
					'imsi': sim_info.get('imsi', ''),
					'iccid': sim_info.get('iccid', ''),
				}
			elif payload == "Filter":
				notification = {
					'type': 'notification',
					'notification_type': 'Filter',
					'hostname': hostname,
					'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
				}
			elif payload == "Status":
				notification = {
					'type': 'notification',
					'notification_type': 'Status',
					'hostname': hostname,
					'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
					'data': data or {}
				}
			else:
				notification = {
					'type': 'notification',
					'notification_type': payload,
					'hostname': hostname,
					'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
					'data': data or {}
				}

			result = uploader.send_notification(notification, recipients)

		uploader.disconnect()
		if result:
			set_last_mail_time(payload)
			logger.info(f"IoT fallback: '{payload}' sent successfully")
		return result
	except Exception as e:
		logger.error(f"IoT fallback failed: {e}")
		return False

def send_email(payload, data=None):
	config = config_json_handler()
	sender_password = config.get('email_service_password', 'email_service_password')
	mail_logs_to = config.get('mail_logs_to', "your@email.address")

	if sender_password == "email_service_password" or sender_password == "" or mail_logs_to.split(",")[0] == "your@email.address":
		logger.debug("No email credentials, trying IoT fallback")
		return _send_via_iot(payload, data) if _is_iot_available() else False

	COOLDOWNS = {"Filter": 7200, "Log": 3600, "Pump": 3600, "Onboarding": 86400, "Status": 300}
	min_interval = COOLDOWNS.get(payload, 3600)

	if not can_send_mail(payload, min_interval):
		elapsed = time.time() - get_last_mail_time(payload)
		logger.debug(f"Mail '{payload}' suppressed, cooldown {int(min_interval - elapsed)}s remaining")
		return False

	if not check_connection():
		logger.info(f"Offline, trying IoT fallback for '{payload}'")
		return _send_via_iot(payload, data) if _is_iot_available() else False

	smtp_server = "live.smtp.mailtrap.io"
	smtp_port = 587
	sender_email = f"{hostname} Status <mailtrap@bcmeter.org>"
	email_receiver_list = mail_logs_to.split(",")
	subject_prefix = "bcMeter Status Mail: "
	templates = {
		"Filter": {"subject": "Change filter!", "body": "Hello dear human, please consider changing the filter paper the next time you're around, thank you!", "needs_attachment": False},
		"Log": {"subject": "Log file", "body": "Hello dear human, please find attached the log file", "needs_attachment": True},
		"Pump": {"subject": "Pump Malfunction", "body": "I do not register any airflow. Please check the connections and if the pump is working", "needs_attachment": True},
		"Onboarding": {"subject": "Device Information", "body": None, "needs_attachment": False},
		"Status": {"subject": "System Status", "body": None, "needs_attachment": False}
	}
	if payload not in templates:
		logger.error(f"Unknown payload type: {payload}")
		return False
	template = templates[payload]
	message = MIMEMultipart()
	message["From"] = sender_email
	message["Subject"] = subject_prefix + template["subject"]

	if payload == "Onboarding":
		message["Subject"] = f"bcMeter {hostname} is Online"
		try:
			info = get_basic_info()
			info['network_name'] = get_network_name()
			body = f"Your bcMeter '{info['hostname']}' is online and ready to log.\n\n"
			body += f"Access: http://{info['ip_address']} or http://{info['hostname']}.local\n"
			body += f"Network: {info['network_name']}\n"
			body += f"Storage: {info['disk_free']} free\n"
		except Exception as e:
			body = f"Your bcMeter '{hostname}' is online and ready to log."
	elif payload == "Status":
		message["Subject"] = f"bcMeter {hostname} Status & Test"
		body = "bcMeter System Status Report\n\n"
		if data:
			for key, value in data.items():
				body += f"{key}: {value}\n"
		else:
			body += "No data provided."
	else:
		body = template["body"]

	message.attach(MIMEText(body, "plain"))

	if template["needs_attachment"]:
		file_path = base_dir + "/logs/log_current.csv"
		try:
			file_size = os.path.getsize(file_path)
			if file_size < 500:
				logger.warning(f"Log file too small ({file_size}B), skipping mail")
				return False
		except OSError:
			logger.error("Log file not accessible")
			return False
		try:
			current_time = datetime.now().strftime("%y%m%d_%H%M")
			send_file_as = f"{hostname}_{current_time}.csv"
			with open(file_path, "rb") as file:
				attachment = MIMEApplication(file.read(), Name=send_file_as)
				attachment["Content-Disposition"] = f"attachment; filename={send_file_as}"
				message.attach(attachment)
		except Exception as e:
			logger.error(f"Failed to attach file: {str(e)}")
			return False

	success = False
	for receiver in email_receiver_list:
		message["To"] = receiver
		try:
			with smtplib.SMTP(smtp_server, smtp_port) as server:
				server.starttls()
				server.login("api", sender_password)
				server.sendmail(sender_email, receiver, message.as_string())
			logger.debug(f"Email '{payload}' sent to {receiver}")
			success = True
		except Exception as e:
			logger.error(f"Failed to send email to {receiver}: {str(e)}")

	if success:
		set_last_mail_time(payload)
		if payload == "Pump":
			logger.error("Error mail (Pump Malfunction) sent")
		else:
			logger.debug(f"{payload} mail sent")
		return True

	logger.warning(f"Email failed for '{payload}', trying IoT fallback")
	return _send_via_iot(payload, data) if _is_iot_available() else False

airflow_type = config.get('af_sensor_type', 1)
if config.get('airflow_sensor'):
	print(f"Using Airflow sensor type {airflow_type}")

def save_config_to_json(key, value=None, description=None, parameter_type=None, parameter_category=None):
	full_config = config_json_handler()
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
		full_config[key] = {'value': value, 'description': description or "No description", 'type': parameter_type or "undefined", 'parameter': parameter_category or "general"}
	with open(base_dir + '/bcMeter_config.json', 'w') as json_file:
		json.dump(full_config, json_file, indent=4)

def update_ssid_in_hostapd_conf(revert=False):
	target_ssid = "ebcMeter" if not revert else "bcMeter"
	if shutil.which("nmcli"):
		try:
			subprocess.run(["nmcli", "con", "modify", "bcMeter-ap", "wifi.ssid", target_ssid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		except Exception:
			pass

is_ebcMeter = config.get('is_ebcMeter', False)
if is_ebcMeter:
	update_ssid_in_hostapd_conf()
else:
	update_ssid_in_hostapd_conf(revert=True)

def get_bcmeter_start_time():
	try:
		result = subprocess.run(['systemctl', 'show', 'bcMeter', '--property=ActiveEnterTimestamp'], stdout=subprocess.PIPE, text=True, check=True)
		output = result.stdout.strip()
		if "ActiveEnterTimestamp" in output:
			timestamp_str = output.split('=')[1].strip()
			bcmeter_start_time = datetime.strptime(timestamp_str, '%a %Y-%m-%d %H:%M:%S %Z')
			return bcmeter_start_time.strftime("%y%m%d_%H%M%S")
		return None
	except Exception:
		return None

def manage_bcmeter_status(parameter=None, action='get', bcMeter_status=None, calibration_time=None, log_creation_time=None, hostname=None, filter_status=None, in_hotspot=None):
	volatile_folder = "/dev/shm/bcmeter/"
	volatile_file = volatile_folder + 'BCMETER_WEB_STATUS'
	persistent_file = base_dir + "/calibration_data.json"
	legacy_status_dir = base_dir + "/tmp/"
	legacy_status_file = legacy_status_dir + "BCMETER_WEB_STATUS"
	log_file_path = base_dir + "/logs/log_current.csv"

	persistent_keys = {'calibration_time', 'filter_status'}
	default_parameters = {'bcMeter_status': 5, 'calibration_time': None, 'log_creation_time': None, 'hostname': socket.gethostname(), 'filter_status': 0, 'in_hotspot': True}

	def load_json(path):
		try:
			if os.path.exists(path) and os.path.getsize(path) > 0:
				with open(path, 'r') as f:
					return json.load(f)
		except Exception:
			pass
		return {}

	def write_merged_volatile():
		merged = {**default_parameters, **persistent_params, **volatile_params}
		os.makedirs(volatile_folder, exist_ok=True)
		with open(volatile_file, 'w') as f:
			json.dump(merged, f)

	volatile_params = load_json(volatile_file)
	persistent_params = load_json(persistent_file)

	for pk in persistent_keys:
		if pk in volatile_params:
			del volatile_params[pk]

	parameters = {**default_parameters, **persistent_params, **volatile_params}

	valid_params = list(default_parameters.keys())

	if action == 'get':
		if parameter and parameter not in valid_params:
			raise ValueError(f"Invalid parameter. Choose from: {valid_params}")
		parameters['hostname'] = socket.gethostname()
		if persistent_params and not os.path.exists(volatile_file):
			write_merged_volatile()
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
		if filter_status is not None:
			filter_status = min(max(0, filter_status), 5)

		update_dict = {k: v for k, v in {'bcMeter_status': bcMeter_status, 'calibration_time': calibration_time, 'log_creation_time': log_creation_time, 'hostname': socket.gethostname(), 'filter_status': filter_status, 'in_hotspot': in_hotspot}.items() if v is not None}

		persistent_updates = {k: v for k, v in update_dict.items() if k in persistent_keys}
		volatile_updates = {k: v for k, v in update_dict.items() if k not in persistent_keys}

		if persistent_updates:
			persistent_params.update(persistent_updates)
			with open(persistent_file, 'w') as f:
				json.dump(persistent_params, f)

		volatile_params.update(volatile_updates)
		write_merged_volatile()

		if not os.path.exists(legacy_status_dir):
			try:
				os.makedirs(legacy_status_dir, exist_ok=True)
				os.chmod(legacy_status_dir, 0o777)
			except OSError:
				pass
		if not os.path.islink(legacy_status_file):
			try:
				if os.path.exists(legacy_status_file):
					os.remove(legacy_status_file)
				os.symlink(volatile_file, legacy_status_file)
			except OSError:
				pass
	else:
		raise ValueError("Invalid action. Use 'get' or 'set'")

use_display = config.get('use_display', False)
display_i2c_address = 0x3c
try:
	for device in range(128):
		try:
			i2c.writeto(device, b'')
			if hex(device) == display_i2c_address:
				use_display = True
		except OSError:
			pass
	if use_display:
		from oled_text import OledText, Layout64, BigLine, SmallLine
		oled = OledText(i2c, 128, 64)
		oled.layout = {1: BigLine(5, 0, font="Arimo.ttf", size=20), 2: SmallLine(5, 25, font="Arimo.ttf", size=14), 3: SmallLine(5, 40, font="Arimo.ttf", size=14)}
except Exception as e:
	print("Display error:", e)

def show_display(message, clear, line):
	if use_display is True:
		if clear is True:
			oled.clear()
		oled.text(str(message), line + 1)

def get_pi_revision():
	try:
		with open('/proc/cpuinfo', 'r') as f:
			for line in f:
				if line.startswith('Revision'):
					rev_code_str = line.split(':')[1].strip()
					rev_code = int(rev_code_str, 16)
					new_flag = (rev_code >> 23) & 0x1
					if not new_flag:
						return f"Legacy revision code (0x{rev_code:x})"
					model = (rev_code >> 4) & 0xFF
					memory = (rev_code >> 20) & 0x7
					models = {0x00: "A", 0x01: "B", 0x02: "A+", 0x03: "B+", 0x04: "2B", 0x05: "Alpha", 0x06: "CM1", 0x08: "3B", 0x09: "Zero", 0x0a: "CM3", 0x0c: "Zero W", 0x0d: "3B+", 0x0e: "3A+", 0x10: "CM3+", 0x11: "4B", 0x13: "400", 0x14: "CM4", 0x15: "Zero 2 W", 0x17: "5", 0x18: "CM5", 0x19: "500", 0x1a: "CM5 Lite"}
					memory_map = {0: "256MB", 1: "512MB", 2: "1GB", 3: "2GB", 4: "4GB", 5: "8GB", 6: "16GB"}
					model_name = models.get(model, "Unknown model")
					memory_size = memory_map.get(memory, "unknown RAM")
					return f"Raspberry Pi {model_name} with {memory_size} RAM"
		return "No revision code found"
	except Exception as e:
		return f"Error reading revision: {str(e)}"

if int(airflow_type) == 9:
	from smbus2 import SMBus
	print("initializing honeywell")
	def read_airflow_ml(flow_range=750.0, sensor_address=0x49, smbus_ch=1, env_temp_c=20.0, env_pressure=1024.0, samples=200):
		STD_TEMP_K = 273.15
		STD_PRESSURE = 1023.38
		supported_ranges = [50.0, 100.0, 200.0, 400.0, 750.0]
		supported_addresses = [0x49, 0x59, 0x69, 0x79]
		if flow_range not in supported_ranges or sensor_address not in supported_addresses:
			raise ValueError("Unsupported sensor configuration.")
		with SMBus(smbus_ch) as bus:
			time.sleep(0.02)
			bus.read_byte(sensor_address)
			time.sleep(0.035)
			bus.read_byte(sensor_address)
		flow_sum = 0
		with SMBus(smbus_ch) as bus:
			for _ in range(samples):
				raw_data = bus.read_i2c_block_data(sensor_address, 0, 2)
				digital_output = (raw_data[0] << 8) | raw_data[1]
				if digital_output & 0xc000:
					raise ValueError(f"Invalid sensor data: {hex(digital_output)}")
				flow_rate = flow_range * ((digital_output / 16384) - 0.5) / 0.4
				flow_sum += flow_rate
				time.sleep(0.001)
		avg_flow_sccm = flow_sum / samples / 1000
		env_temp_k = 273.15 + env_temp_c
		compensated_flow = avg_flow_sccm * (STD_PRESSURE * env_temp_k) / (env_pressure * STD_TEMP_K)
		return compensated_flow

def ona_filter(data_path, delta_atn_min=0.05, delimiter=';'):
	try:
		with open(data_path, 'r', newline='') as f:
			reader = csv.DictReader(f, delimiter=delimiter)
			fieldnames = reader.fieldnames
			data = list(reader)
	except Exception as e:
		print(f"Error reading file: {e}")
		return
	if not data:
		return
	required_columns = ['bcmTime', 'bcmATN']
	bc_column = None
	output_column = None
	if 'BCngm3_unfiltered' in fieldnames:
		bc_column = 'BCngm3_unfiltered'
		output_column = 'BCngm3_ona'
	elif 'BCugm3_unfiltered' in fieldnames:
		bc_column = 'BCugm3_unfiltered'
		output_column = 'BCugm3_ona'
	if bc_column is None:
		return
	for col in required_columns:
		if col not in fieldnames:
			return
	n_rows = len(data)
	try:
		atn_values = np.array([float(row['bcmATN']) for row in data])
		bc_values = np.array([float(row[bc_column]) for row in data])
	except ValueError:
		return
	processed_values = np.zeros(n_rows)
	window_sizes = np.zeros(n_rows, dtype=int)
	if n_rows < 2:
		processed_values[:] = bc_values
		window_sizes[:] = 1
	else:
		i = 0
		while i < n_rows:
			start_idx = i
			start_atn = atn_values[i]
			end_idx = i + 1
			while end_idx < n_rows and (atn_values[end_idx] - start_atn) < delta_atn_min:
				end_idx += 1
			if end_idx >= n_rows:
				end_idx = n_rows - 1
			end_atn = atn_values[end_idx]
			last_valid_idx = end_idx
			for j in range(end_idx + 1, n_rows):
				if atn_values[j] <= end_atn:
					last_valid_idx = j
			window_slice = bc_values[start_idx:last_valid_idx + 1]
			avg_bc = np.mean(window_slice)
			window_size = len(window_slice)
			processed_values[start_idx:last_valid_idx + 1] = avg_bc
			window_sizes[start_idx:last_valid_idx + 1] = window_size
			i = last_valid_idx + 1
	if output_column not in fieldnames:
		fieldnames.append(output_column)
	if 'ONA_window_size' not in fieldnames:
		fieldnames.append('ONA_window_size')
	for idx, row in enumerate(data):
		row[output_column] = processed_values[idx]
		row['ONA_window_size'] = window_sizes[idx]
	try:
		with open(data_path, 'w', newline='') as f:
			writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
			writer.writeheader()
			writer.writerows(data)
	except Exception as e:
		print(f"Error writing file: {e}")

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
	apply_dynamic_airflow.samples = apply_dynamic_airflow.samples[-4:]
	avg_bc = sum(apply_dynamic_airflow.samples) / len(apply_dynamic_airflow.samples)
	try:
		current_airflow = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))
	except (ValueError, TypeError):
		logger.warning("Invalid airflow_per_minute value in config")
		current_airflow = 0.25
	target_airflow = adjust_airflow_dynamically(avg_bc, af_sensor_type)
	logger.info(f"Airflow adjusted: {current_airflow:.3f} -> {target_airflow:.3f} L/min (BC={avg_bc} ng/m3)")
	return True, target_airflow

if not os.path.exists(base_dir + "/tmp/BCMETER_WEB_STATUS"):
	manage_bcmeter_status(action='set')
