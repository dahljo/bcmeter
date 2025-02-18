
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

ctrl_lp_ver="0.9.52 2025-02-04"
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


def check_service_running(service_name):
	try:
		result = subprocess.run(['systemctl', 'is-active', service_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		return result.stdout.decode().strip() == 'active'
	except subprocess.CalledProcessError:
		return False

def activate_dnsmasq_service():
	try:
		if check_service_running("dnsmasq"):
			run_command("sudo systemctl stop dnsmasq")
		run_command("sudo systemctl start dnsmasq")
		logger.debug("Dnsmasq service started successfully")
		return True
	except Exception as e:
		logger.error(f"Error activating dnsmasq: {e}")
		return False



def deactivate_dnsmasq_service():
	if check_service_running("dnsmasq"):
		p = subprocess.Popen(["sudo", "systemctl", "stop", "dnsmasq"]).communicate()
		p = subprocess.Popen(["sudo", "systemctl", "disable", "dnsmasq"]).communicate()
		logger.debug("Dnsmasq service stopped/deactivated.")

def stop_access_point(checkpoint = None):
	logger.debug(f"Stopping Hotspot ({checkpoint})")
	deactivate_dnsmasq_service()
	prepare_dhcpcd_conf(0)
	if check_service_running("hostapd"):
		run_command("sudo systemctl stop hostapd")


def stop_bcMeter_service(checkpoint = None):

	if check_service_running("bcMeter"):
		manage_bcmeter_status(action='set', bcMeter_status=5)
		subprocess.run(["sudo", "systemctl", "start", "bcMeter"])
		logger.debug("bcMeter service disabled.")



def run_bcMeter_service(checkpoint = None):
	logger.debug(f"Starting bcMeter ({checkpoint})")
	if check_service_running("bcMeter") is False:
		subprocess.run(["sudo", "systemctl", "start", "bcMeter"])
		logger.debug("bcMeter service started.")
		time.sleep(5)

def force_wlan0_reset(checkpoint=None):
	"""
	Force reset the WLAN interface with comprehensive hardware checks and logging.
	Returns:
		bool: True if reset was successful, False otherwise
	"""
	try:
		logger.debug(f"Starting WLAN reset procedure {checkpoint}")
		# Check if WiFi hardware is blocked
		rfkill_output = subprocess.run(['rfkill', 'list', 'wifi'], 
												capture_output=True, 
												text=True)
		if "blocked: yes" in rfkill_output.stdout:
			logger.warning("WiFi is blocked by rfkill - attempting to unblock")
			subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
			time.sleep(1)
		
		# Check for hardware presence
		if not os.path.exists('/sys/class/net/wlan0'):
			logger.error("WLAN interface not found in system")
			return False
				
		# Get initial device state
		iwconfig_output = subprocess.run(['iwconfig', 'wlan0'], 
													capture_output=True, 
													text=True)
		logger.debug(f"Initial WLAN state: {iwconfig_output.stdout.strip()}")
		
		# Check driver status
		driver_check = subprocess.run(['lsmod'], capture_output=True, text=True)
		if 'brcmfmac' not in driver_check.stdout:
			logger.error("WiFi driver not loaded - attempting to load")
			try:
				subprocess.run(["sudo", "modprobe", "brcmfmac"], check=True)
				time.sleep(2)
			except subprocess.CalledProcessError as e:
				logger.error(f"Failed to load WiFi driver: {e}")
				return False
		
		# Perform the reset sequence
		reset_sequence = [
				["sudo", "ip", "link", "set", "wlan0", "down"],
				["sudo", "ip", "addr", "flush", "dev", "wlan0"],
				["sudo", "systemctl", "restart", "wpa_supplicant"],
				["sudo", "ip", "link", "set", "wlan0", "up"]
		]
		
		for cmd in reset_sequence:
			try:
				result = subprocess.run(cmd, 
											capture_output=True, 
											text=True, 
											check=True)
				logger.debug(f"Executed {' '.join(cmd)}: {result.stdout.strip()}")
				time.sleep(1)  # Give system time to process each step
			except subprocess.CalledProcessError as e:
				logger.error(f"Command failed {' '.join(cmd)}: {e}")
				return False
		
		# Verify interface is up
		post_reset_check = subprocess.run(['ip', 'link', 'show', 'wlan0'], 
													capture_output=True, 
													text=True)
		if "state UP" not in post_reset_check.stdout:
			logger.error("WLAN interface failed to come up after reset")
			return False
			
		# Check for firmware errors
		dmesg_output = subprocess.run(['dmesg', '|', 'grep', 'brcmfmac'], 
												shell=True, 
												capture_output=True, 
												text=True)
		if "firmware error" in dmesg_output.stdout:
			logger.error("Firmware errors detected in system log")
			return False
			
		# Final connectivity check
		time.sleep(2)  # Wait for interface to fully initialize
		final_state = subprocess.run(['iwconfig', 'wlan0'], 
											capture_output=True, 
											text=True)
		logger.debug(f"Final WLAN state: {final_state.stdout.strip()}")
		
		return True
		
	except Exception as e:
		logger.error(f"Critical error during WLAN reset: {str(e)}")
		logger.debug("Error details:", exc_info=True)  # Log full traceback
		return False

def get_uptime():
	uptime = time.time()-current_datetime_timestamp
	return uptime


def delete_wifi_credentials():
	with open(WIFI_CREDENTIALS_FILE, 'w') as f:
		f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	
	logger.debug("Reset WiFi Configs")


def debug_dhcp_status():
	logger.debug("=== DHCP Debug Info ===")
	debug_commands = [
		["systemctl", "status", "dnsmasq"],
		"ps aux | grep dnsmasq",  # Shell command
		["ip", "addr", "show", "wlan0"],
		["cat", "/var/lib/misc/dnsmasq.leases"],
		["cat", "/etc/dnsmasq.conf"],
		["iptables", "-L", "-n", "-t", "nat"],
		["route", "-n"],
		["cat", "/proc/sys/net/ipv4/ip_forward"]
	]
	
	for cmd in debug_commands:
		try:
			if isinstance(cmd, str):  # Shell command with pipes
				output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
			else:  # List of command arguments
				output = subprocess.run(cmd, capture_output=True, text=True)
			logger.debug(f"\n=== {cmd if isinstance(cmd, str) else ' '.join(cmd)} ===\n{output.stdout}")
			if output.stderr:
				logger.error(f"Error in {cmd}: {output.stderr}")
		except Exception as e:
				logger.error(f"Failed to run {cmd}: {e}")

def setup_access_point():
	stop_access_point(1)
	time.sleep(1)
	force_wlan0_reset(1)
	time.sleep(1)
	restart_ap_loop = False
	try:
		# Configure hostapd
		device_name = socket.gethostname()
		try:
			with open(HOSTAPD_CONF, 'r') as f:
				config = f.read()
			ssid_match = re.search(r'^ssid=(.*)$', config, flags=re.MULTILINE)
			current_ssid = ssid_match.group(1) if ssid_match else None
			
			if current_ssid != device_name:
				new_config = re.sub(r'^ssid=.*$', f'ssid={device_name}', config, flags=re.MULTILINE)
				with open(HOSTAPD_CONF, 'w') as f:
					f.write(new_config)
				os.chmod(HOSTAPD_CONF, 0o600)
				restart_ap_loop = True
		except PermissionError:
				logger.debug("Permission denied to change SSID")
		except Exception as e:
				logger.debug(f"Error: {e}")
		# Configure wpa_supplicant
		with open(WPA_CONF, 'w') as f:
			f.write('\n'.join([
				"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev",
				"update_config=1",
				"country=DE"
			]))

		# Configure dhcpcd and services
		prepare_dhcpcd_conf(1)
		run_command("sudo systemctl daemon-reload")
		run_command("sudo service dhcpcd restart")
		time.sleep(2)
		
		if activate_dnsmasq_service():
			time.sleep(1)
			run_command("sudo systemctl restart hostapd")
			logger.debug(f"AP setup complete with SSID: {device_name}")
			show_display("Hotspot", False, 0)
			show_display("Go to Interface", False, 1)
			#debug_dhcp_status()
			return True
		return False

	except Exception as e:
		logger.error(f"Error in setup_access_point: {e}")
		return False


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


def manage_wifi(checkpoint = None):
	global wifi_connection_retries
	wifi_ssid, wifi_pwd = get_wifi_credentials()
	bcMeter_running = check_service_running("bcMeter")
	if (not wifi_ssid or not wifi_pwd) or run_hotspot:
		if not check_service_running("hostapd"):
			logger.debug("Setting up Hotspot - no credentials or forced mode")
			subprocess.Popen(["sudo", "systemctl", "daemon-reload"]).communicate()
			setup_access_point()
		return

	current_network = get_wifi_network()
	if current_network == wifi_ssid and check_connection():
		wifi_connection_retries = 0
		if check_service_running("hostapd"):
			stop_access_point(2)
		if not check_service_running('bcMeter') and manage_bcmeter_status(action='get',parameter='bcMeter_status') not in (5, 6):
			if manage_bcmeter_status(action='get', parameter='filter_status') > 3:

				run_bcMeter_service("1")
				show_display("Conn OK", False, 0)
				show_display("Starting up", False, 1)

		return

	# Not connected to desired network
	logger.debug(f"Not connected to desired network. Current: {current_network}")
	if is_wifi_in_range(wifi_ssid):
		logger.debug(f"WiFi {wifi_ssid} in range, attempting connection")
		show_display("Connecting to WiFi", False, 0)
		show_display(f"{wifi_ssid}", False, 1)
		create_wpa_supplicant(wifi_ssid, wifi_pwd)
		if check_service_running("hostapd"):
			stop_access_point(3)
		subprocess.Popen(["sudo", "systemctl", "daemon-reload"]).communicate()
		subprocess.Popen(["sudo", "service", "dhcpcd", "restart"]).communicate()
		
		for attempt in range(2):
			if check_connection():
				wifi_connection_retries = 0
				if not check_service_running('bcMeter') and manage_bcmeter_status(action='get',parameter='bcMeter_status') not in (5, 6):
					if manage_bcmeter_status(action='get', parameter='filter_status') > 3:
						run_bcMeter_service("2")
						show_display("Conn OK", False, 0)
						show_display("Starting up", False, 1)
				return
			force_wlan0_reset()
			time.sleep(2)
		
		wifi_connection_retries += 1
		if wifi_connection_retries >= 5:
			logger.error(f"Cannot connect to {wifi_ssid}")
			wifi_connection_retries = 0
			delete_wifi_credentials()
			if not check_service_running("hostapd"):
				setup_access_point()
	else:
		#logger.debug(f"WiFi {wifi_ssid} not in range. Retry: {wifi_connection_retries}")
		wifi_connection_retries += 1
		if wifi_connection_retries >= 3 and not check_service_running("hostapd"):
			logger.debug("Starting hotspot after failed attempts")
			setup_access_point()


def ap_control_loop():
	global time_synced
	if (manage_bcmeter_status(action='get',parameter='bcMeter_status') not in (5, 6)):
		manage_bcmeter_status(action='set', bcMeter_status=4)
	config = config_json_handler()
	keep_running = we_got_correct_time = is_online = False
	scan_interval = 10
	run_hotspot = config.get('run_hotspot', False)
	is_ebcMeter = config.get('is_ebcMeter', False)
	prev_log_creation_time = None
	was_offline = True

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



		if run_hotspot or check_service_running("hostapd"):
			current_status = 3 if bcMeter_running else 4
		elif is_online:
			current_status = 2
		elif not is_online and check_service_running("hostapd"):
			current_status = 4
		else:
			current_status = 0

		if (current_status in (3,4)):
			manage_bcmeter_status(action='set',in_hotspot=True)
		else:
			manage_bcmeter_status(action='set',in_hotspot=False)

		if (manage_bcmeter_status(action='get',parameter='bcMeter_status') not in (5, 6)):
			if is_online and not bcMeter_running:
				run_bcMeter_service("3")
			prev_log_creation_time = manage_bcmeter_status(action='set', bcMeter_status=current_status, log_creation_time=prev_log_creation_time)



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
					#run_commmand("sudo shotdown now")
					keep_running = True 
					
		time.sleep(scan_interval)


if not debug:
	ap_control_loop()
else:
	logger.debug("HAPPY DEBUGGING")
	while True:
		time.sleep(1)

