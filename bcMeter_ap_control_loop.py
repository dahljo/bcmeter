
#heavily adapted telraams work 

import socket
import subprocess
import signal
import os
import time
import re
import signal
import requests
import uuid
import json
from bcMeter_shared import config_json_handler, check_connection, manage_bcmeter_status, show_display, config, setup_logging, get_pi_revision, run_command, send_email
import importlib
from datetime import datetime
import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
from board import SCL, SDA, I2C
import busio, smbus
from sys import argv
from threading import Thread, Event

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1

ctrl_lp_ver="0.9.53 2025-03-06"
subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()
devicename = socket.gethostname()

time_synced = False

logger = setup_logging('ap_control_loop')


logger.debug(f"bcMeter Network Handler started for {devicename} (v{ctrl_lp_ver})")

logger.debug(get_pi_revision())

base_dir = '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

try:
	if os.path.exists(base_dir + '/bcMeter_config.json'):
		config = config_json_handler()
	else:
		config = convert_config_to_json()
		config = {key: value['value'] for key, value in config.items()}
		logger.debug("json conversion of config complete")
except Exception as e:
	logger.error(f"Config load error {e}")


debug = True if (len(argv) > 1) and (argv[1] == "debug") else False

enable_wifi = config.get('enable_wifi', True)
is_ebcMeter = config.get('is_ebcMeter', False)
use_display = config.get('use_display', False)
run_hotspot = config.get('run_hotspot', False)

bcMeter_started = str(datetime.now().strftime("%y%m%d_%H%M%S"))
current_datetime_timestamp = time.time()


if (enable_wifi is False):
	import sys
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "down"])
	p.communicate()
	stop_access_point()
	sys.exit()




show_display(f"Init WiFi", True, 0)
show_display(f"Ctrl Loop {ctrl_lp_ver}", False, 1)


#wifi credentials file
WIFI_CREDENTIALS_FILE=base_dir + '/bcMeter_wifi.json'
HOSTAPD_CONF, WPA_CONF = "/etc/hostapd/hostapd.conf", "/etc/wpa_supplicant/wpa_supplicant.conf"
#stop hotspot from being active after a while (can be overridden by parameter run_hotspot=True)
keep_hotspot_alive_without_successful_connection = 3600


def check_service_running(service_name, wait_for_state=None, timeout=10):
	"""Check systemd service state with optional wait for target state."""
	if wait_for_state is None:
		try:
			result = subprocess.run(['systemctl', 'is-active', service_name], 
								check=True, stdout=subprocess.PIPE)
			return result.stdout.decode().strip() == 'active'
		except subprocess.CalledProcessError:
			return False

	start = time.time()
	while time.time() - start < timeout:
		try:
			current = subprocess.run(['systemctl', 'is-active', service_name], 
								 capture_output=True, text=True).stdout.strip()
			if (wait_for_state == 'active' and current == 'active') or \
			  (wait_for_state == 'inactive' and current != 'active'):
				logger.debug(f"{service_name} now {wait_for_state}")
				return True
		except subprocess.CalledProcessError:
			if wait_for_state == 'inactive':
				return True
		time.sleep(0.5)
	return False

def activate_dnsmasq_service():
	try:
		if check_service_running("dnsmasq"):
			run_command("sudo systemctl stop dnsmasq")
			if not check_service_running("dnsmasq", wait_for_state="inactive"):
				logger.error("Failed to stop dnsmasq service before restart")
				return False
				
		run_command("sudo systemctl start dnsmasq")
		if not check_service_running("dnsmasq", wait_for_state="active"):
			logger.error("Failed to start dnsmasq service")
			return False
			
		logger.debug("Dnsmasq service started successfully")
		return True
		
	except Exception as e:
		logger.error(f"Error activating dnsmasq: {e}")
		return False

def deactivate_dnsmasq_service():
	if check_service_running("dnsmasq"):
		run_command("sudo systemctl stop dnsmasq")
		if not check_service_running("dnsmasq", wait_for_state="inactive"):
			logger.error("Failed to stop dnsmasq service")
			return False
			
		run_command("sudo systemctl disable dnsmasq")
		logger.debug("Dnsmasq service stopped/deactivated")
		return True
	return True
	
def stop_access_point(checkpoint = None):
	force_wlan0_reset(checkpoint)
	logger.debug(f"Stopping Hotspot ({checkpoint})")
	prepare_dhcpcd_conf(0)
	for service in ["dnsmasq", "hostapd"]:
		if check_service_running(service):
			run_command(f"sudo systemctl stop {service}")
			if not check_service_running(service, wait_for_state="inactive"):
				logger.error(f"Failed to stop {service}")
				return False
	return True


def stop_bcMeter_service(checkpoint = None):
	if check_service_running("bcMeter"):
		manage_bcmeter_status(action='set', bcMeter_status=5)
		run_command("sudo systemctl stop bcMeter")
		if not check_service_running("bcMeter", wait_for_state="inactive"):
			logger.error(f"Failed to stop bcMeter service ({checkpoint})")
			return False
		logger.debug(f"bcMeter service stopped ({checkpoint})")
		return True
	return True

def run_bcMeter_service(checkpoint = None):
	logger.debug(f"Starting bcMeter ({checkpoint})")
	if not check_service_running("bcMeter"):
		run_command("sudo systemctl start bcMeter")
		if not check_service_running("bcMeter", wait_for_state="active"):
			logger.error(f"Failed to start bcMeter service ({checkpoint})")
			return False
		logger.debug(f"bcMeter service started ({checkpoint})")
		return True
	return True

def force_wlan0_reset(checkpoint=None):
	try:
		logger.debug(f"Starting WLAN reset procedure {checkpoint}")
		for service in ["wpa_supplicant", "dhcpcd"]:
			run_command(f"sudo systemctl stop {service}")
			if not check_service_running(service, wait_for_state="inactive"):
				logger.error(f"Failed to stop {service}")
				return False

		run_command("sudo ifconfig wlan0 down")
		time.sleep(1)

		run_command("sudo ifconfig wlan0 up")
		time.sleep(1)
		return True

	except Exception as e:
		logger.error(f"WLAN reset failed: {str(e)}")
		return False

def get_uptime():
	uptime = time.time()-current_datetime_timestamp
	return uptime


def delete_wifi_credentials():
	with open(WIFI_CREDENTIALS_FILE, 'w') as f:
		f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	
	logger.debug("Reset WiFi Configs")


def setup_access_point():
	if not stop_access_point("setup AP"):
		logger.error("Failed to stop existing AP")
		return False

	device_name = socket.gethostname()
	try:
		with open(HOSTAPD_CONF, 'r') as f:
			config_data = f.read()
		# Replace existing 'ssid=...' line with 'ssid=<device_name>'
		new_data = re.sub(r'^ssid=.*$', f'ssid={device_name}', config_data, flags=re.M)
		if new_data != config_data:
			with open(HOSTAPD_CONF, 'w') as f:
				f.write(new_data)
			os.chmod(HOSTAPD_CONF, 0o600)
	except Exception as e:
		logger.error(f"SSID update failed: {e}")

	prepare_dhcpcd_conf(1)
	run_command("sudo systemctl daemon-reload")
	run_command("sudo systemctl restart dhcpcd")
	if not check_service_running("dhcpcd", wait_for_state="active"):
		logger.error("Failed to start dhcpcd service")
		return False

	run_command("sudo systemctl enable dnsmasq")  # optional if you want it enabled on boot
	run_command("sudo systemctl start dnsmasq")
	if not check_service_running("dnsmasq", wait_for_state="active"):
		logger.error("Failed to start dnsmasq service")
		return False
	run_command("sudo systemctl start hostapd")
	if not check_service_running("hostapd", wait_for_state="active"):
		logger.error("Failed to start hostapd service")
		return False

	logger.debug(f"AP setup complete with SSID: {device_name}")
	show_display("Hotspot", False, 0)
	show_display("Go to Interface", False, 1)
	return True



def validate_wifi_credentials(ssid, pwd):
	if ssid is None or pwd is None:
		return False
	if not (1 <= len(ssid) <= 32):
		return False
	if not (8 <= len(pwd) <= 63):
		return False
	if not all(32 <= ord(char) <= 126 for char in pwd):
		return False
	return True


def get_wifi_credentials():
	try:
		with open(WIFI_CREDENTIALS_FILE) as wifi_file:
			data = json.load(wifi_file)
			if not validate_wifi_credentials(data['wifi_ssid'], data['wifi_pwd']):
				raise ValueError("Invalid WiFi credentials")
			return data['wifi_ssid'], data['wifi_pwd']
	except FileNotFoundError as e:
		logger.error('FileNotFoundError:\n{}'.format(e))
		with open(WIFI_CREDENTIALS_FILE, 'w') as f:
			f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	except (ValueError, KeyError) as e:
		pass
		#logger.error(f'Credentials error: {e}')
	#logger.debug("no file/ssid/pwd!")
	return None, None



def is_wifi_driver_loaded():
	try:
		result = subprocess.run(['sudo', 'iw', 'dev'], capture_output=True, text=True)
		output = result.stdout.strip()

		if "Interface" in output:
			logger.debug("WiFi adapter found")
			return True
		else:
			logger.error("NO WIFI ADAPTER FOUND!")
			return False
	except FileNotFoundError:
		return False

# Loop until Wi-Fi driver is loaded
for _ in range(3):
	if is_wifi_driver_loaded():
		logger.debug("Wi-Fi driver is enabled and loaded.")
		break
	else:
		logger.debug("Wi-Fi driver is not enabled or loaded. Retrying...")
		time.sleep(2)  


def create_wpa_supplicant(wifi_ssid, wifi_pwd):
	config = [
		"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev",
		"update_config=1",
		"country=DE",
		"network={",
		f'\tssid="{wifi_ssid}"',
		f'\tpsk="{wifi_pwd}"',
		"\tscan_ssid=1",
		"\tkey_mgmt=WPA-PSK",
		"\tproto=RSN WPA",
		"\tpairwise=CCMP",
		"}"
	]
	
	with open("/etc/wpa_supplicant/wpa_supplicant.conf", "w") as file:
		file.write("\n".join(config))

def is_wifi_in_range(wifi_name):
	retries = 10
	attempts = 1
	max_attempts = 3
	while attempts <= max_attempts:
		try:
			for _ in range(retries):
				scan_process = subprocess.Popen(['iwlist', 'wlan0', 'scan'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
				stdout, stderr = scan_process.communicate()  # Get stdout and stderr
				wifi_name = str(wifi_name)
				if wifi_name in stdout.decode('utf-8'):
					logger.debug(f"Found known WiFi {wifi_name} in range!")
					return True
				time.sleep(3)

			return False

		except Exception as e:
			logger.error(f"Attempt {attempts}: An error occurred: {str(e)}. Trying again in 3 seconds...")
			time.sleep(3)  # Wait for 3 seconds before retrying the entire function
			logger.debug("Resetting wlan0")
		
		attempts += 1  # Increment the attempt counter

	logger.error("Failed to execute WiFi Scan after multiple attempts. Giving up.")


	return False



def prepare_dhcpcd_conf(option):
	# remove the static IP  (last 3 lines of dhcpcd.conf file)
	file = open('/etc/dhcpcd.conf', 'r+')
	data = file.readlines()
	pos = 0
	for line in data:
		pos += len(line)
		if line == '#bcMeterConfig\n':
			file.seek(pos, os.SEEK_SET)
			file.truncate()
			break
	file.close()	
	if (option == 0):
		logger.debug("edited dhcpcd for use in client mode")

	elif (option == 1):
		# and then add our hotspot dhcp config (always after #bcMeterConfig)
		file = open("/etc/dhcpcd.conf", "a")
		file.write("#bcMeterConfig\n")  
		file.write("interface wlan0\n")
		file.write("  static ip_address=192.168.18.8/24\n")
		file.write("  nohook wpa_supplicant")
		file.close()

		logger.debug("edited dhcpcd for AP")




def get_wifi_network():
	try:
		# Run the iwgetid command to get the SSID of the connected network
		ssid = subprocess.check_output(['iwgetid', '-r']).decode('utf-8').strip()
		if ssid:
			return ssid
		else:
			return 0
	except subprocess.CalledProcessError:
		# Handle errors if the command fails
		return -1

def check_time_sync():
	try:
		result = subprocess.run(['timedatectl', 'status'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
		output = result.stdout

		if 'System clock synchronized: yes' in output:
			return True
		elif 'System clock synchronized: no' in output:
			return False
		else:
			logger.debug("Could not determine synchronization status.")
			return False
		
	except Exception as e:
		logger.error(f"Error occurred: {e}")
		return False

def time_sync_check_loop(stop_event):
	global time_synced
	while not stop_event.is_set():
		#time_synced = check_time_sync()
		if time_synced:
			logger.debug("Time sync achieved, stopping time sync thread.")
			stop_event.set()  # Stop the thread
		else:
			#logger.debug("Time not synced yet, checking again in 30 seconds.")
			time.sleep(30)


wifi_connection_retries = 0


def wait_for_wifi_connection(timeout):  
	start_time = time.time()
	while time.time() - start_time < timeout:
		if check_connection():
			return True
		time.sleep(2)
	return False


def manage_wifi(checkpoint=None):
	global wifi_connection_retries
	wifi_ssid, wifi_pwd = get_wifi_credentials()
	bcMeter_running = check_service_running("bcMeter")
	
	if (not wifi_ssid or not wifi_pwd) or run_hotspot:
		if not check_service_running("hostapd"):
			logger.debug("Setting up Hotspot - no credentials or forced mode")
			run_command("sudo systemctl daemon-reload")
			setup_access_point()
		return
	
	current_network = get_wifi_network()
	if current_network == wifi_ssid and check_connection():
		wifi_connection_retries = 0
		if check_service_running("hostapd"):
			stop_access_point("already connected -> stop AP")
		if not bcMeter_running and manage_bcmeter_status(action='get', parameter='bcMeter_status') not in (5, 6):
			if manage_bcmeter_status(action='get', parameter='filter_status') > 3:
				run_bcMeter_service("Already online -> bcMeter start")
				show_display("Conn OK", False, 0)
				show_display("Starting up", False, 1)
		return
	
	logger.debug(f"Not connected to desired network. Current: {current_network}")
	
	if is_wifi_in_range(wifi_ssid):
		logger.debug(f"WiFi {wifi_ssid} in range, attempting connection")
		show_display("Connecting to WiFi", False, 0)
		show_display(f"{wifi_ssid}", False, 1)

		create_wpa_supplicant(wifi_ssid, wifi_pwd)

		if check_service_running("hostapd"):
			stop_access_point("stop AP -> station mode")
		
		run_command("sudo systemctl daemon-reload")
		run_command("sudo systemctl restart dhcpcd")
		if not check_service_running("dhcpcd", wait_for_state="active"):
			logger.error("dhcpcd failed to become active for station mode")
			return
		
		run_command("sudo systemctl start wpa_supplicant")
		if not check_service_running("wpa_supplicant", wait_for_state="active"):
			logger.error("wpa_supplicant failed to become active for station mode")
			return
		
		if wait_for_wifi_connection(20):
			wifi_connection_retries = 0
			if not check_service_running('bcMeter') and \
				manage_bcmeter_status(action='get', parameter='bcMeter_status') not in (5, 6):
				if manage_bcmeter_status(action='get', parameter='filter_status') > 3:
					run_bcMeter_service("Connected after wait")
					show_display("Conn OK", False, 0)
					show_display("Starting up", False, 1)
		else:
			logger.error(f"Failed to connect to {wifi_ssid} within 15s.")
			wifi_connection_retries += 1

			if wifi_connection_retries >= 3:
				logger.error(f"Cannot connect to {wifi_ssid} after multiple tries.")
				wifi_connection_retries = 0
				delete_wifi_credentials()
				if not check_service_running("hostapd"):
					setup_access_point()
	else:
		wifi_connection_retries += 1
		logger.debug(f"WiFi {wifi_ssid} not in range. Retry count: {wifi_connection_retries}")
		if wifi_connection_retries >= 3 and not check_service_running("hostapd"):
			logger.debug("Starting hotspot after repeated failure to see SSID")
			setup_access_point()



def check_wifi_errors_in_syslog(last_seen_errors=set()):
	"""
	Check syslog for specific WiFi-related errors.
	Returns a list of new detected error messages.
	
	Args:
		last_seen_errors (set): Set of previously detected error messages
	
	Returns:
		tuple: (new_errors list, updated_seen_errors set)
	"""
	try:
		result = subprocess.run(['tail', '-n', '100', '/var/log/syslog'], capture_output=True, text=True)
		log_entries = result.stdout.split('\n')
		
		error_patterns = [
			r'brcmf_cfg80211_stop_ap:.*failed.*-\d+',
			r'ieee80211 phy0:.*failed',
			r'brcmfmac:.*error',
			r'wlan0:.*error'
		]
		
		new_errors = []
		current_errors = set()
		
		for line in log_entries:
			for pattern in error_patterns:
				if re.search(pattern, line, re.IGNORECASE):
					try:
						timestamp = line.split()[0]
						error_msg = line.split('] ')[-1].strip() if ']' in line else line.strip()
						full_error = f"{timestamp} - {error_msg}"
						current_errors.add(full_error)
						if full_error not in last_seen_errors:
							new_errors.append(full_error)
					except IndexError:
						continue
						
		return new_errors, current_errors
		
	except Exception as e:
		logger.error(f"Error checking syslog: {e}")
		return [], last_seen_errors



def ap_control_loop():
	global time_synced
	seen_wifi_errors = set()
	if (manage_bcmeter_status(action='get',parameter='bcMeter_status') not in (5, 6)):
		manage_bcmeter_status(action='set', bcMeter_status=4)
	config = config_json_handler()
	keep_running = we_got_correct_time = is_online = False
	scan_interval = 10
	run_hotspot = config.get('run_hotspot', False)
	is_ebcMeter = config.get('is_ebcMeter', False)
	prev_log_creation_time = None
	was_offline = True
	in_hotspot = False
	wifi_ssid, _ = get_wifi_credentials()
	if not wifi_ssid or not is_wifi_in_range(wifi_ssid):
		logger.debug("Initial check: No WiFi available, starting hotspot")
		setup_access_point()
	else:
		manage_wifi(1)
	stop_time_sync_thread = Event()
	time_sync_thread = Thread(target=time_sync_check_loop, args=(stop_time_sync_thread,))
	time_sync_thread.start()

	while True:
		config = config_json_handler()
		run_hotspot = config.get('run_hotspot', False)
		is_online = check_connection()
		bcMeter_running = check_service_running("bcMeter")

		# Check network state
		current_network = get_wifi_network()
		wifi_ssid, _ = get_wifi_credentials()
		if current_network != wifi_ssid:
			manage_wifi(2)

		current_status = manage_bcmeter_status(action='get',parameter='bcMeter_status')
		if (current_status not in (5, 6)):
			if run_hotspot or check_service_running("hostapd"):
				current_status = 3 if bcMeter_running else 4
			elif is_online:
				current_status = 2
				if not bcMeter_running:
					run_bcMeter_service("3")
			elif not is_online and check_service_running("hostapd"):
				current_status = 4
			else:
				current_status = 0

		if run_hotspot or check_service_running("hostapd"):
			in_hotspot = True
		else:
			in_hotspot = False
		manage_bcmeter_status(
			 action='set',
			 bcMeter_status=current_status,
			 in_hotspot=in_hotspot,
			 log_creation_time=prev_log_creation_time
		)


		if is_online:
			if was_offline:
				try:
					logger.debug("Device connected, sending onboarding email")
					send_email("Onboarding")
				except Exception as e:
					logger.error(f"Failed to send onboarding email: {e}")
				was_offline = False
			if time_synced and not we_got_correct_time:
				uptime = get_uptime()
				we_got_correct_time = True
		else:
			was_offline = True
		if not is_online and not run_hotspot:
			uptime = get_uptime() if time_synced else keep_hotspot_alive_without_successful_connection-1
			if uptime >= keep_hotspot_alive_without_successful_connection:
				if not (is_ebcMeter or bcMeter_running or keep_running):
					logger.debug("Still No Configuration")                            
					show_display("No Config", False, 0)
					#run_command("sudo shutdown now")
					keep_running = True 
		new_wifi_errors, seen_wifi_errors = check_wifi_errors_in_syslog(seen_wifi_errors)
		if new_wifi_errors:
			for error in new_wifi_errors:
				logger.debug(f"WiFi Message: {error}")
					
		time.sleep(scan_interval)


if not debug:
	ap_control_loop()
else:
	logger.debug("HAPPY DEBUGGING")
	while True:
		time.sleep(1)

