import socket
import subprocess
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
import RPi.GPIO as GPIO
from board import SCL, SDA, I2C
import busio, smbus
from sys import argv
from threading import Thread, Event

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1)

ctrl_lp_ver="0.9.54 2025-05-16"
subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()
devicename = socket.gethostname()

time_synced = False
driver_error_count = 0
service_restart_count = {}
last_state_transition = time.time()
wifi_recovery_attempts = 0
in_happy_state = False
last_happy_state_check = 0
internet_wait_start_time = 0
internet_wait_timeout = 120  
connection_retries = 0


logger = setup_logging('ap_control_loop')
logger.debug(f"bcMeter Network Handler started for {devicename} (v{ctrl_lp_ver})")
logger.debug(get_pi_revision())

base_dir = '/home/bcmeter' if os.path.isdir('/home/bcmeter') else '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

class ServiceManager:
	def __init__(self):
		self.max_retries = 3
		self.service_timeouts = {'hostapd': 15, 'dnsmasq': 10, 'dhcpcd': 10, 'wpa_supplicant': 10, 'bcMeter': 20}
		
	def check_running(self, service_name, wait_for_state=None, timeout=None):
		timeout = timeout or self.service_timeouts.get(service_name, 10)
		
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
					return True
			except subprocess.CalledProcessError:
				if wait_for_state == 'inactive':
					return True
			time.sleep(0.5)
		return False
	
	def stop_service(self, service_name):
		if not self.check_running(service_name):
			return True
			
		for attempt in range(self.max_retries):
			run_command(f"sudo systemctl stop {service_name}")
			if self.check_running(service_name, wait_for_state="inactive"):
				return True
			if attempt < self.max_retries - 1:
				run_command(f"sudo killall {service_name}")
				time.sleep(1)
		return False
	
	def start_service(self, service_name):
		if self.check_running(service_name):
			return True
			
		for attempt in range(self.max_retries):
			run_command(f"sudo systemctl start {service_name}")
			if self.check_running(service_name, wait_for_state="active"):
				return True
			time.sleep(2)
		return False
	
	def restart_service(self, service_name):
		self.stop_service(service_name)
		time.sleep(1)
		return self.start_service(service_name)


class WifiManager:
	def __init__(self, service_manager):
		self.service_manager = service_manager
		self.credentials_file = base_dir + '/bcMeter_wifi.json'
		self.hostapd_conf = "/etc/hostapd/hostapd.conf"
		self.wpa_conf = "/etc/wpa_supplicant/wpa_supplicant.conf"
		self.max_connection_retries = 3
		
	def validate_credentials(self, ssid, pwd):
		if ssid is None or pwd is None:
			return False
		if not (1 <= len(ssid) <= 32):
			return False
		if not (8 <= len(pwd) <= 63):
			return False
		if not all(32 <= ord(char) <= 126 for char in pwd):
			return False
		return True
	
	def get_credentials(self):
		try:
			with open(self.credentials_file) as wifi_file:
				data = json.load(wifi_file)
				if not self.validate_credentials(data['wifi_ssid'], data['wifi_pwd']):
					raise ValueError("Invalid WiFi credentials")
				return data['wifi_ssid'], data['wifi_pwd']
		except (FileNotFoundError, ValueError, KeyError):
			return None, None
	
	def delete_credentials(self):
		with open(self.credentials_file, 'w') as f:
			f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(self.credentials_file, 0o777)
		logger.debug("Reset WiFi Configs")
	
	def create_wpa_supplicant(self, wifi_ssid, wifi_pwd):
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
		
		with open(self.wpa_conf, "w") as file:
			file.write("\n".join(config))
	
	def get_current_network(self):
		try:
			ssid = subprocess.check_output(['iwgetid', '-r']).decode('utf-8').strip()
			return ssid if ssid else None
		except Exception:
			return None
	
	def is_ssid_in_range(self, wifi_name):
		max_scan_attempts = 3
		for attempt in range(max_scan_attempts):
			try:
				for _ in range(5):
					result = subprocess.run(['iwlist', 'wlan0', 'scan'], 
										  capture_output=True, text=True)
					if wifi_name in result.stdout:
						logger.debug(f"Found known WiFi {wifi_name} in range!")
						return True
					time.sleep(2)
				return False
			except Exception as e:
				logger.error(f"Scan attempt {attempt+1} failed: {e}")
				if attempt < max_scan_attempts - 1:
					self.reset_interface()
					time.sleep(3)
		return False
	
	def reset_interface(self):
		try:
			logger.debug("Resetting wlan0 interface")
			run_command("sudo ifconfig wlan0 down")
			time.sleep(3)
			run_command("sudo ifconfig wlan0 up")
			time.sleep(5)
			return True
		except Exception as e:
			logger.error(f"Interface reset failed: {e}")
			return False
	
	def check_connection_quality(self, ssid=None):
		try:
			iwconfig = subprocess.run(['iwconfig', 'wlan0'], 
									capture_output=True, text=True).stdout
			if "Not-Associated" in iwconfig:
				return None
				
			connected_ssid = re.search(r'ESSID:"([^"]+)"', iwconfig)
			signal_level = re.search(r'Signal level=(-\d+) dBm', iwconfig)
			
			if ssid and (not connected_ssid or connected_ssid.group(1) != ssid):
				return None
				
			result = {
				'ssid': connected_ssid.group(1) if connected_ssid else None,
				'signal': int(signal_level.group(1)) if signal_level else None,
				'is_stable': False
			}
			
			if result['signal']:
				quality_percent = (result['signal'] + 110) * 10 / 7
				result['is_stable'] = quality_percent > 30
				
			return result
		except Exception as e:
			logger.error(f"Error checking WiFi quality: {e}")
			return None

def force_wlan0_reset(checkpoint=None):
	try:
		logger.debug(f"Starting WLAN reset procedure {checkpoint}")
		service_manager = ServiceManager()
		wifi_manager = WifiManager(service_manager)
		
		for service in ["wpa_supplicant", "dhcpcd", "hostapd"]:
			service_manager.stop_service(service)
		time.sleep(1)
		
		wifi_manager.reset_interface()
		
		iwconfig_output = subprocess.run(['iwconfig', 'wlan0'], capture_output=True, text=True)
		if 'no wireless extensions' in iwconfig_output.stdout.lower():
			logger.error("WiFi interface failed to come up properly - reloading driver")
			if not reload_wifi_driver():
				return False
			wifi_manager.reset_interface()
			
		return True
	except Exception as e:
		logger.error(f"WLAN reset failed: {str(e)}")
		return False

def setup_access_point():
	service_manager = ServiceManager()
	max_retries = 3
	
	for attempt in range(max_retries):
		if not stop_access_point("setup AP"):
			if attempt < max_retries - 1:
				force_wlan0_reset()
				time.sleep(8)
				continue
			else:
				logger.error("Critical: Cannot stop existing AP after retries")
				return False
		
		device_name = socket.gethostname()
		prepare_dhcpcd_conf(1)
		run_command("sudo systemctl daemon-reload")
		time.sleep(2)
		
		if not service_manager.restart_service("dhcpcd"):
			if attempt < max_retries - 1:
				force_wlan0_reset()
				time.sleep(8)
				continue
			else:
				return False
		
		run_command("sudo systemctl enable dnsmasq")
		if not service_manager.start_service("dnsmasq"):
			if attempt < max_retries - 1:
				force_wlan0_reset()
				time.sleep(8)
				continue
			else:
				return False
		
		if not service_manager.start_service("hostapd"):
			if attempt < max_retries - 1:
				force_wlan0_reset()
				time.sleep(8)
				continue
			else:
				return False
		
		logger.debug(f"AP setup complete with SSID: {device_name}")
		show_display("Hotspot", False, 0)
		show_display("Go to Interface", False, 1)
		return True
	
	logger.error("Failed to setup access point after all retries")
	return False


def get_default_gateway():
	"""Get the default gateway IP address"""
	try:
		# Run route command to get default gateway
		route_output = subprocess.run(['ip', 'route', 'show', 'default'], 
									 capture_output=True, text=True).stdout
		
		# Parse the output to extract gateway IP
		gateway_match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', route_output)
		if gateway_match:
			return gateway_match.group(1)
			
		# If no match found via the first method, try alternate method
		route_output = subprocess.run(['route', '-n'], 
									 capture_output=True, text=True).stdout
		for line in route_output.splitlines():
			if '0.0.0.0' in line:
				parts = line.split()
				if len(parts) >= 2:
					return parts[1]
					
		return None
	except Exception as e:
		logger.error(f"Failed to get default gateway: {e}")
		return None

def ping_router(timeout=2, count=3):
	"""Ping the router/gateway and check connectivity"""
	gateway_ip = get_default_gateway()
	if not gateway_ip:
		logger.error("Could not determine gateway IP for ping test")
		return False
		
	try:
		logger.debug(f"Pinging gateway {gateway_ip}")
		result = subprocess.run(
			['ping', '-c', str(count), '-W', str(timeout), gateway_ip],
			capture_output=True,
			text=True
		)
		success = result.returncode == 0
		
		if success:
			# Extract ping statistics
			time_pattern = r'time=(\d+\.?\d*) ms'
			times = re.findall(time_pattern, result.stdout)
			if times:
				avg_time = sum(float(t) for t in times) / len(times)
				logger.debug(f"Gateway ping successful: avg time={avg_time:.1f}ms")
			else:
				logger.debug("Gateway ping successful but couldn't parse timing")
		else:
			logger.warning(f"Gateway ping failed: {gateway_ip}")
			
		return success
	except Exception as e:
		logger.error(f"Error during ping test: {e}")
		return False

def handle_exit_signal(signum, frame):
	signal_name = {
		signal.SIGINT: "SIGINT",
		signal.SIGTERM: "SIGTERM",
		signal.SIGHUP: "SIGHUP"
	}.get(signum, f"Signal {signum}")
	
	logger.info(f"Received {signal_name} signal - shutting down bcMeter Network Handler")
	show_display("Shutting down", True, 0)
	show_display("Please wait...", False, 1)
	
	try:
		if 'stop_time_sync_thread' in globals():
			stop_time_sync_thread.set()
		if 'time_sync_thread' in globals() and time_sync_thread.is_alive():
			time_sync_thread.join(timeout=2)
		
		service_manager = ServiceManager()
		services = ["hostapd", "dnsmasq", "bcMeter"]
		for service in services:
			service_manager.stop_service(service)
		
		logger.info("bcMeter Network Handler shutdown complete")
	except Exception as e:
		logger.error(f"Error during shutdown: {e}")
	
	os._exit(0)

signal.signal(signal.SIGINT, handle_exit_signal)
signal.signal(signal.SIGTERM, handle_exit_signal)
signal.signal(signal.SIGHUP, handle_exit_signal)

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
	sys.exit()

show_display(f"Init WiFi", True, 0)
show_display(f"Ctrl Loop {ctrl_lp_ver}", False, 1)

keep_hotspot_alive_without_successful_connection = 3600

def check_service_running(service_name, wait_for_state=None, timeout=10):
	service_manager = ServiceManager()
	return service_manager.check_running(service_name, wait_for_state, timeout)

def activate_dnsmasq_service():
	service_manager = ServiceManager()
	service_manager.stop_service("dnsmasq")
	return service_manager.start_service("dnsmasq")

def deactivate_dnsmasq_service():
	service_manager = ServiceManager()
	if service_manager.stop_service("dnsmasq"):
		run_command("sudo systemctl disable dnsmasq")
		logger.debug("Dnsmasq service stopped/deactivated")
		return True
	return True

def stop_access_point(checkpoint=None):
	logger.debug(f"Stopping Hotspot ({checkpoint})")
	service_manager = ServiceManager()
	
	for service in ["hostapd", "dnsmasq"]:
		service_manager.stop_service(service)
	
	try:
		prepare_dhcpcd_conf(0)
	except Exception as e:
		logger.error(f"Failed to prepare dhcpcd config: {e}")
		return False
	
	if not force_wlan0_reset(checkpoint):
		logger.error("Failed to reset wlan0 interface")
		return False
		
	return True

def stop_bcMeter_service(checkpoint = None):
	service_manager = ServiceManager()
	if service_manager.check_running("bcMeter"):
		manage_bcmeter_status(action='set', bcMeter_status=5)
		return service_manager.stop_service("bcMeter")
	return True

def run_bcMeter_service(checkpoint = None):
	logger.debug(f"Starting bcMeter ({checkpoint})")
	service_manager = ServiceManager()
	return service_manager.start_service("bcMeter")



def reload_wifi_driver():
	global driver_error_count
	driver_error_count += 1
	
	if driver_error_count > 5:
		logger.critical("Too many driver reload attempts - system needs reboot")
		return False
	
	logger.debug("Reloading WiFi driver")
	run_command("sudo rmmod brcmfmac brcmutil")
	time.sleep(3)
	run_command("sudo modprobe brcmfmac")
	time.sleep(5)
	
	if is_wifi_driver_loaded():
		driver_error_count = 0
		return True
	return False

def is_wifi_driver_loaded():
	try:
		result = subprocess.run(['sudo', 'iw', 'dev'], capture_output=True, text=True)
		return "Interface" in result.stdout
	except Exception:
		return False

def get_uptime():
	return time.time() - current_datetime_timestamp

def prepare_dhcpcd_conf(option):
	with open('/etc/dhcpcd.conf', 'r+') as file:
		data = file.readlines()
		pos = 0
		for line in data:
			pos += len(line)
			if line == '#bcMeterConfig\n':
				file.seek(pos, os.SEEK_SET)
				file.truncate()
				break
	
	if option == 0:
		logger.debug("edited dhcpcd for use in client mode")
	elif option == 1:
		with open("/etc/dhcpcd.conf", "a") as file:
			file.write("#bcMeterConfig\n")
			file.write("interface wlan0\n")
			file.write("  static ip_address=192.168.18.8/24\n")
			file.write("  nohook wpa_supplicant")
		logger.debug("edited dhcpcd for AP")

def check_time_sync():
	try:
		result = subprocess.run(['timedatectl', 'status'], capture_output=True, text=True)
		return 'System clock synchronized: yes' in result.stdout
	except Exception:
		return False

def time_sync_check_loop(stop_event):
	global time_synced
	while not stop_event.is_set():
		time_synced = check_time_sync()
		if time_synced:
			logger.debug("Time sync achieved, stopping time sync thread.")
			stop_event.set()
		else:
			time.sleep(30)

def wait_for_wifi_connection(timeout):
	start_time = time.time()
	while time.time() - start_time < timeout:
		if check_connection():
			return True
		time.sleep(2)
	return False

def verify_dhcp_lease():
	try:
		cmd_result = subprocess.run(['ip', 'addr', 'show', 'wlan0'], 
									capture_output=True, text=True).stdout
		ip_matches = re.findall(r'inet (\d+\.\d+\.\d+\.\d+)', cmd_result)
		for ip in ip_matches:
			if not ip.startswith('169.254.'):
				logger.debug(f"Valid DHCP lease found: {ip}")
				return True
		return False
	except Exception as e:
		logger.error(f"Error checking DHCP lease: {e}")
		return False

def check_for_psk_errors():
	try:
		result = subprocess.run(['tail', '-n', '50', '/var/log/syslog'], 
								capture_output=True, text=True)
		error_patterns = [
			'WPA: 4-Way Handshake failed',
			'authentication with .* timed out',
			'CTRL-EVENT-DISCONNECTED .* reason=3',
			'CTRL-EVENT-SSID-TEMP-DISABLED.*auth_failures'
		]
		
		recent_entries = []
		current_time = time.time()
		for line in result.stdout.split('\n'):
			for pattern in error_patterns:
				if re.search(pattern, line):
					recent_entries.append(line)
		
		if recent_entries:
			logger.error("Detected possible WiFi authentication failures")
			return True
		return False
	except Exception:
		return False

def check_happy_state(wifi_ssid):
	if not wifi_ssid:
		return False
	
	service_manager = ServiceManager()
	wifi_manager = WifiManager(service_manager)
	
	current_network = wifi_manager.get_current_network()
	if current_network != wifi_ssid:
		return False
	
	is_online = check_connection()
	if not is_online:
		# Check gateway connectivity when no internet but connected to WiFi
		if ping_router():
			logger.debug("Router is reachable but no internet connectivity")
			return True  # Consider it a partial happy state if router is reachable
		return False
	
	if service_manager.check_running("hostapd"):
		return False
	
	return True

def evaluate_wifi_quality(signal_dbm):
	"""Evaluate WiFi quality on a scale from 0-4 based on dBm signal strength"""
	if not signal_dbm:
		return 0
	
	# Convert dBm to approximate quality level (0-4)
	if signal_dbm >= -55:
		quality = 4  # Very good
	elif signal_dbm >= -65:
		quality = 3  # Good
	elif signal_dbm >= -75:
		quality = 2  # Fair
	elif signal_dbm >= -85:
		quality = 1  # Poor
	else:
		quality = 0  # Very poor
		
	quality_labels = ["Very poor", "Poor", "Fair", "Good", "Very good"]
	logger.debug(f"WiFi signal: {signal_dbm} dBm - Quality: {quality_labels[quality]} ({quality}/4)")
	return quality

def handle_exit_from_happy_state(wifi_ssid):
	global in_happy_state, internet_wait_start_time
	
	logger.info("HAPPY STATE DISTURBED - analyzing situation")
	in_happy_state = False
	
	service_manager = ServiceManager()
	wifi_manager = WifiManager(service_manager)
	
	if not is_wifi_driver_loaded():
		logger.error("WiFi driver not loaded")
		if not reload_wifi_driver():
			setup_access_point()
		return
	
	current_network = wifi_manager.get_current_network()
	is_online = check_connection()
	
	if current_network == wifi_ssid and not is_online:
		logger.debug("Connected to correct network but no internet")
		
		router_reachable = ping_router()
		if router_reachable:
			logger.debug("Router is reachable but internet is down - possible ISP issue")
			show_display("WiFi OK", False, 0)
			show_display("No Internet", False, 1)
			internet_wait_start_time = time.time()
			return
			
		logger.warning("Router is unreachable - likely WiFi connection issue")
		
		current_time = time.time()
		if internet_wait_start_time == 0:
			internet_wait_start_time = current_time
			logger.debug(f"Started waiting for connectivity to return (timeout: {internet_wait_timeout}s)")
		elif current_time - internet_wait_start_time > internet_wait_timeout:
			logger.warning(f"Connectivity wait timeout exceeded after {internet_wait_timeout}s - forcing reconnection")
			internet_wait_start_time = 0
			manage_wifi("connectivity_timeout")
			return
			
		wifi_quality = wifi_manager.check_connection_quality(wifi_ssid)
		if wifi_quality and wifi_quality.get('signal'):
			signal_quality = evaluate_wifi_quality(wifi_quality['signal'])
			if signal_quality <= 1:
				logger.warning("Very poor signal quality - forcing immediate reconnection")
				internet_wait_start_time = 0
				manage_wifi("poor_signal_force")
				return
		
		logger.debug("Waiting for connectivity to return")
	elif current_network != wifi_ssid:
		internet_wait_start_time = 0
		logger.debug(f"Wrong network or disconnected (current: {current_network})")
		manage_wifi("network_change")
	else:
		internet_wait_start_time = 0
		logger.debug("Unknown disturbance - resetting")
		manage_wifi("unknown_issue")

def manage_wifi(checkpoint=None):
	global wifi_recovery_attempts, in_happy_state, connection_retries
	config = config_json_handler()
	is_ebcMeter = config.get('is_ebcMeter', False)
	service_manager = ServiceManager()
	wifi_manager = WifiManager(service_manager)

	wifi_ssid, wifi_pwd = wifi_manager.get_credentials()
	bcMeter_running = service_manager.check_running("bcMeter")

	logger.debug(f"manage_wifi checkpoint {checkpoint}")

	if (not wifi_ssid or not wifi_pwd) or run_hotspot:
		if not service_manager.check_running("hostapd"):
			logger.debug("Setting up Hotspot - no credentials or forced mode")
			if not setup_access_point():
				force_wlan0_reset()
				time.sleep(5)
				setup_access_point()
		return

	current_network = wifi_manager.get_current_network()
	is_online = check_connection()

	if current_network == wifi_ssid and not is_online:
		logger.debug("Connected to network but no internet - checking router connectivity")
		if ping_router():
			logger.debug("Router is reachable - likely an ISP issue, not a WiFi problem")
			connection_retries = 0
			wifi_recovery_attempts = 0
			if service_manager.check_running("hostapd"):
				stop_access_point("router ok -> stop AP")
			show_display("WiFi OK", False, 0)
			show_display("No Internet", False, 1)
			logger.debug("Entering partial happy state (router ok)")
			in_happy_state = True
			return
		else:
			logger.warning("Router unreachable - WiFi connection likely faulty")

	if current_network == wifi_ssid and (is_online or ping_router()):
		connection_retries = 0
		wifi_recovery_attempts = 0
		if service_manager.check_running("hostapd"):
			stop_access_point("already connected -> stop AP")
		if not bcMeter_running and manage_bcmeter_status(action='get', parameter='bcMeter_status') not in (5, 6):
			if manage_bcmeter_status(action='get', parameter='filter_status') > 3 and not is_ebcMeter:
				run_bcMeter_service("Already online -> bcMeter start")
				show_display("Conn OK", False, 0)
				show_display("Starting up", False, 1)
		logger.debug("Entering happy state")
		in_happy_state = True
		return

	logger.debug(f"Not connected to desired network. Current: {current_network}")

	if wifi_manager.is_ssid_in_range(wifi_ssid):
		logger.debug(f"WiFi {wifi_ssid} in range, attempting connection")
		show_display("Connecting to WiFi", False, 0)
		show_display(f"{wifi_ssid}", False, 1)

		wifi_manager.create_wpa_supplicant(wifi_ssid, wifi_pwd)

		if service_manager.check_running("hostapd"):
			logger.debug("Stopping hostapd before connection attempt")
			if not stop_access_point("stop AP -> station mode"):
				logger.error("Failed to stop access point - forcing reset")
				force_wlan0_reset()
				setup_access_point()
				return

		logger.debug("Restarting network services for WiFi connection")
		run_command("sudo systemctl daemon-reload")
		time.sleep(2)

		if not service_manager.restart_service("dhcpcd"):
			logger.error("Failed to restart dhcpcd - falling back to hotspot")
			setup_access_point()
			return

		if not service_manager.start_service("wpa_supplicant"):
			logger.error("Failed to start wpa_supplicant - falling back to hotspot")
			setup_access_point()
			return

		logger.debug("Waiting for WiFi association...")
		time.sleep(10)

		connected = False
		for attempt in range(5):
			current_net = wifi_manager.get_current_network()
			logger.debug(f"Connection attempt {attempt+1}/5: current network = {current_net}")
			if current_net == wifi_ssid:
				connected = True
				logger.debug(f"Successfully associated with {wifi_ssid}")
				break
			time.sleep(8)

		if not connected:
			logger.error(f"Failed to associate with {wifi_ssid} after 5 attempts")
			connection_retries += 1
			wifi_recovery_attempts += 1

			if check_for_psk_errors():
				logger.error(f"Authentication failed for {wifi_ssid} - invalid password")
				show_display("WiFi Error", False, 0)
				show_display("Invalid Password", False, 1)
				wifi_manager.delete_credentials()
				setup_access_point()
				return

			if connection_retries >= wifi_manager.max_connection_retries:
				logger.error(f"Exceeded max connection retries ({wifi_manager.max_connection_retries}) - starting hotspot")
				connection_retries = 0
				setup_access_point()
				return

			logger.debug(f"Connection failed, retry count: {connection_retries}")
			return

		logger.debug("Checking for DHCP lease...")
		if not verify_dhcp_lease():
			logger.error("Connected but failed to obtain DHCP lease")
			connection_retries += 1
			if connection_retries >= wifi_manager.max_connection_retries:
				logger.error("Too many DHCP failures - starting hotspot")
				connection_retries = 0
				setup_access_point()
			return

		wifi_quality = wifi_manager.check_connection_quality(wifi_ssid)
		if wifi_quality and wifi_quality['is_stable']:
			logger.debug(f"Connected to {wifi_ssid} with signal {wifi_quality['signal']}!")

			logger.debug("Testing internet connectivity...")
			has_internet = wait_for_wifi_connection(10)
			has_router = ping_router() if not has_internet else True

			if has_internet or has_router:
				connection_retries = 0
				wifi_recovery_attempts = 0

				if has_internet:
					logger.debug("Internet connection confirmed")
					show_display("Conn OK", False, 0)
				else:
					logger.debug("Router reachable but no internet")
					show_display("WiFi OK", False, 0)
					show_display("No Internet", False, 1)

				if not service_manager.check_running('bcMeter') and \
				   manage_bcmeter_status(action='get', parameter='bcMeter_status') not in (5, 6):
					if manage_bcmeter_status(action='get', parameter='filter_status') > 3:
						run_bcMeter_service("Connected after wait")
						if has_internet:
							show_display("Conn OK", False, 0)
							show_display("Starting up", False, 1)

				logger.debug("Entering happy state")
				in_happy_state = True
				return
			else:
				logger.error("Connected to AP but neither router nor internet is reachable")
		else:
			logger.error(f"Connected but signal quality is poor: {wifi_quality}")

		connection_retries += 1
		wifi_recovery_attempts += 1

		if connection_retries < wifi_manager.max_connection_retries:
			logger.debug(f"Poor connection quality - attempting reconnection {connection_retries}/{wifi_manager.max_connection_retries}")
			force_wlan0_reset("poor_quality_reconnect")
			time.sleep(3)
			return
		else:
			logger.error(f"Cannot establish stable connection after {connection_retries} tries - starting hotspot")
			connection_retries = 0
			setup_access_point()

	else:
		connection_retries += 1
		logger.debug(f"WiFi {wifi_ssid} not in range. Retry count: {connection_retries}")

		if connection_retries < wifi_manager.max_connection_retries:
			logger.debug(f"SSID not in range - retry {connection_retries}/{wifi_manager.max_connection_retries}, forcing interface reset")
			force_wlan0_reset("ssid_not_in_range")
			time.sleep(5)
			return
		else:
			logger.debug("Starting hotspot after repeated failure to see SSID")
			connection_retries = 0
			if not setup_access_point():
				force_wlan0_reset()
				time.sleep(5)
				setup_access_point()
				time.sleep(2)

def ap_control_loop():
	global time_synced, stop_time_sync_thread, in_happy_state, last_happy_state_check, time_sync_thread, internet_wait_start_time
	
	service_manager = ServiceManager()
	wifi_manager = WifiManager(service_manager)
	
	if manage_bcmeter_status(action='get', parameter='bcMeter_status') not in (5, 6):
		manage_bcmeter_status(action='set', bcMeter_status=4)
	
	config = config_json_handler()
	scan_interval = 10
	happy_state_check_interval = 30
	router_check_interval = 60
	last_router_check = 0
	run_hotspot = config.get('run_hotspot', False)
	is_ebcMeter = config.get('is_ebcMeter', False)
	was_offline = True
	router_reachable = False
	
	wifi_ssid, _ = wifi_manager.get_credentials()
	if not wifi_ssid or not wifi_manager.is_ssid_in_range(wifi_ssid):
		logger.debug("Initial check: No WiFi available, starting hotspot")
		if not setup_access_point():
			force_wlan0_reset()
			time.sleep(5)
			setup_access_point()
	else:
		manage_wifi(1)
	
	stop_time_sync_thread = Event()
	time_sync_thread = Thread(target=time_sync_check_loop, args=(stop_time_sync_thread,))
	time_sync_thread.start()
	calibration_time = manage_bcmeter_status(action='get', parameter='calibration_time')
	
	try:
		while True:
			try:
				config = config_json_handler()
				run_hotspot = config.get('run_hotspot', False)
				is_online = check_connection()
				bcMeter_running = service_manager.check_running("bcMeter")
				hostapd_running = service_manager.check_running("hostapd")
				is_ebcMeter = config.get('is_ebcMeter', False)

				current_network = wifi_manager.get_current_network()
				wifi_ssid, _ = wifi_manager.get_credentials()
				
				current_time = time.time()
				
				if current_network and not is_online and not hostapd_running and internet_wait_start_time > 0:
					if current_time - internet_wait_start_time > internet_wait_timeout:
						logger.warning("Main loop detected connectivity timeout - forcing reconnection")
						internet_wait_start_time = 0
						manage_wifi("main_loop_timeout")
						continue
				
				if current_network and not is_online and not hostapd_running:
					if current_time - last_router_check > router_check_interval:
						last_router_check = current_time
						router_reachable = ping_router()
						if router_reachable:
							logger.debug("Router is reachable but no internet connectivity")
							show_display("WiFi OK", False, 0)
							show_display("No Internet", False, 1)
						else:
							logger.warning("Router unreachable despite WiFi connection")
							wifi_quality = wifi_manager.check_connection_quality(wifi_ssid)
							if wifi_quality and wifi_quality.get('signal'):
								signal_quality = evaluate_wifi_quality(wifi_quality['signal'])
								if signal_quality <= 1:
									logger.warning("Very poor signal detected - forcing reconnection")
									manage_wifi("poor_signal_detected")
									continue
							if not in_happy_state and internet_wait_start_time == 0:
								manage_wifi("router_unreachable")
				
				if in_happy_state:
					if current_time - last_happy_state_check > happy_state_check_interval:
						last_happy_state_check = current_time
						if not check_happy_state(wifi_ssid):
							handle_exit_from_happy_state(wifi_ssid)
					else:
						time.sleep(scan_interval)
						continue
				
				if not is_wifi_driver_loaded():
					logger.error("WiFi driver not loaded - attempting recovery")
					if not reload_wifi_driver():
						setup_access_point()
					continue
				
				if current_network != wifi_ssid and wifi_ssid and not hostapd_running:
					manage_wifi(2)
				
				current_status = manage_bcmeter_status(action='get', parameter='bcMeter_status')
				
				if run_hotspot or hostapd_running:
					current_status = 3 if bcMeter_running else 4
				elif is_online:
					if bcMeter_running:
						current_status = 2
					else:
						if (manage_bcmeter_status(action='get', parameter='filter_status') > 3) and calibration_time is not None and not is_ebcMeter and current_status not in (5,6):
							print("Calibration time ", calibration_time)
							run_bcMeter_service("Starting with status ", current_status)
							current_status = 2
						else:
							current_status = 0
				elif not is_online and hostapd_running:
					current_status = 4
				else:
					current_status = 0
				
				in_hotspot = run_hotspot or hostapd_running
				
				manage_bcmeter_status(
					action='set',
					bcMeter_status=current_status,
					in_hotspot=in_hotspot
				)
				
				if is_online:
					if was_offline:
						try:
							send_email("Onboarding")
						except Exception as e:
							logger.error(f"Failed to send onboarding email: {e}")
						was_offline = False
				else:
					was_offline = True
				
				if not is_online and not run_hotspot:
					uptime = get_uptime() if time_synced else keep_hotspot_alive_without_successful_connection - 1
					if uptime >= keep_hotspot_alive_without_successful_connection:
						if not (is_ebcMeter or bcMeter_running):
							logger.debug("Still No Configuration")
							show_display("No Config", False, 0)
							if not hostapd_running:
								logger.debug("No connection and no hotspot - setting up hotspot")
								setup_access_point()
				
				if hostapd_running and wifi_ssid:
					if scan_interval * (time.time() // scan_interval) % 60 < scan_interval:
						if wifi_manager.is_ssid_in_range(wifi_ssid):
							logger.debug(f"Saved network {wifi_ssid} detected - attempting to reconnect")
							manage_wifi("periodic_reconnect_attempt")
				
				time.sleep(scan_interval)
				
			except Exception as e:
				logger.error(f"Loop iteration error: {e}")
				time.sleep(5)
				continue
				
	except Exception as e:
		logger.error(f"Control loop exception: {e}")
		handle_exit_signal(signal.SIGTERM, None)

if not is_wifi_driver_loaded():
	logger.error("WiFi driver not loaded at startup")
	if not reload_wifi_driver():
		logger.critical("Cannot load WiFi driver - exiting")
		sys.exit(1)

if not debug:
	ap_control_loop()
else:
	logger.debug("HAPPY DEBUGGING")
	while True:
		time.sleep(1)