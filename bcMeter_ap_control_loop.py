
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
from bcMeter_shared import load_config_from_json, check_connection, update_interface_status, show_display, config, setup_logging
import importlib
from datetime import datetime
import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
from board import SCL, SDA, I2C
import busio, smbus
from sys import argv
from threading import Thread

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1

ctrl_lp_ver="0.9.45"
subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()
bcMeter_button_gpio = 16

current_datetime_timestamp = time.time() #script started

logger = setup_logging('ap_control_loop')


logger.debug(f"bcMeter Network Handler started (v{ctrl_lp_ver})")

try:
	if os.path.exists('/home/pi/bcMeter_config.json'):
		config = load_config_from_json()
	else:
		config = convert_config_to_json()
		config = {key: value['value'] for key, value in config.items()}
		print("json conversion of config complete")
except Exception as e:
	logger.error(f"Config load error {e}")


debug = True if (len(argv) > 1) and (argv[1] == "debug") else False

enable_wifi = config.get('enable_wifi', True)
is_ebcMeter = config.get('is_ebcMeter', False)
use_display = config.get('use_display', False)
bcMeter_started = str(datetime.now().strftime("%y%m%d_%H%M%S"))
devicename = socket.gethostname()



if (enable_wifi is False):
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "down"])
	p.communicate()
	stop_access_point()
	sys.exit()




show_display(f"Init WiFi", True, 0)
show_display(f"Ctrl Loop {ctrl_lp_ver}", False, 1)


#wifi credentials file
WIFI_CREDENTIALS_FILE='/home/pi/bcMeter_wifi.json'



#stop hotspot from being active after 10 Minutes of running (can be overridden by parameter run_hotspot=True)
keep_hotspot_alive_without_successful_connection = 600


def get_wifi_bssid(ssid):
	logger.debug('... Getting wifi bssid for ssid={}'.format(ssid))
	ap_list=[]
	out_newlines=None
	for i in range(5):              #try max 5 times
		logger.debug('\ttrying... {}'.format(i))
		scan_cmd='sudo iw dev wlan0 scan ap-force'
		process = subprocess.Popen([scan_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		out, err = process.communicate()
		if(len(err)==0):                                                #the command did not produce an error so e can process the list of access points
			out_newlines=str(out).replace('\\n', '\n')                  #because of the bytes to str conversion newlines are \\n instead of \n
			break
		else:
			logger.debug('\terror: {}'.format(err))
		time.sleep(2)                                                   #sleep before retrying
		
	if(not out_newlines):                                               #the command produced an error every time, return no bssid
		return None
		
	split_str=re.findall('BSS.*\n.*\n.*\n.*\n.*\n.*\n.*\n.*\n.*SSID.*\n', out_newlines, re.MULTILINE)

	for cell in split_str:     
		ap={}
		ap['bssid']=None
		ap['frequency']=None
		ap['signal']=None
		ap['ssid']=None
		
		m=re.search('BSS\s*([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})', cell)
		if(m):
			ap['bssid']=m.group(1)

		m=re.search('freq:\s*(\d+)', cell)
		if(m):
			ap['frequency']=int(m.group(1))
		
		m=re.search('signal:\s*(-?\d+\.\d+)\s*dBm', cell)
		if(m):
			ap['signal']=float(m.group(1))
		
		m=re.search('SSID:\s*(.+)', cell)
		if(m):
			ap['ssid']=m.group(1)
		
		ap_list.append(ap)

	ap_list=[x for x in ap_list if x['ssid']==ssid]                     #filter for ssid
	
	logger.debug('Access points found for ssid={}:'.format(ssid))
	for ap in ap_list:
		ap_list=[x for x in ap_list if x['frequency']<2500]                 #filter for 2.4 GHz wifi band -> freqs lower than 2500 MHz
		ap_list=sorted(ap_list, key=lambda x: x['signal'], reverse=True)    #sort on signal_level
	
	if(len(ap_list)>0):
		logger.debug('Using access point: {}'.format(ap_list[0]))
		return ap_list[0]['bssid']
	else:
		logger.debug('Did not find any access points')
		return None

def stop_access_point():
	deactivate_dnsmasq_service()
	if check_service_running("hostapd"):
		p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
		p.communicate()
		logger.debug("Stopped Accespoint")

def stop_bcMeter_service():
	if check_service_running("bcMeter"):
		p = subprocess.Popen(["sudo", "systemctl", "stop", "bcMeter"]).communicate()
		p = subprocess.Popen(["sudo", "systemctl", "disable", "bcMeter"]).communicate()
		logger.debug("bcMeter service disabled.")

def activate_dnsmasq_service():
	if check_service_running("dnsmasq") is False:
		#p = subprocess.Popen(["sudo", "systemctl", "enable", "dnsmasq"]).communicate()
		p = subprocess.Popen(["sudo", "systemctl", "start", "dnsmasq"]).communicate()
		logger.debug("Dnsmasq service started.")


def deactivate_dnsmasq_service():
	if check_service_running("dnsmasq"):
		p = subprocess.Popen(["sudo", "systemctl", "stop", "dnsmasq"]).communicate()
		p = subprocess.Popen(["sudo", "systemctl", "disable", "dnsmasq"]).communicate()
		logger.debug("Dnsmasq service stopped/deactivated.")

def run_bcMeter_service():
	if check_service_running("bcMeter") is False:
		#p = subprocess.call(["sudo", "systemctl", "enable", "bcMeter"])
		p = subprocess.Popen(["sudo", "systemctl", "start", "bcMeter"]).communicate()
		logger.debug("bcMeter service started.")

def force_wlan0_reset():
	logger.debug("forcing wlan0 reset")
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "down"])
	p.communicate()
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "up"])
	p.communicate()



def get_uptime():
	uptime = time.time()-current_datetime_timestamp
	return uptime


def setup_access_point():
	#deactivate_dnsmasq_service()
	p = subprocess.Popen(["sudo", "systemctl", "unmask","hostapd"])
	p.communicate()
	stop_access_point()
	#reset wpa_supplicant
	file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
	file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
	file.close()

	#reset our own wifi conf
	with open(WIFI_CREDENTIALS_FILE, 'w') as f:
		f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)

	logger.debug("Reset WiFi Configs")

	# reset the config file with a static IP
	# first delete anything that was written after #bcMeterConfig
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

	# and then add our hotspot dhcp config (always after #bcMeterConfig)
	file = open("/etc/dhcpcd.conf", "a")
	file.write("interface wlan0\n")
	file.write("  static ip_address=192.168.18.8/24\n")
	file.write("  nohook wpa_supplicant")
	file.close()

	logger.debug("edited dhcpcd")

	activate_dnsmasq_service()
	p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
	p.communicate()
	logger.debug("daemon reloaded")
	p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
	p.communicate()
	# restart the AP
	p = subprocess.Popen(["sudo", "systemctl", "start", "hostapd"])
	p.communicate()
	logger.debug("hostapd started")
	show_display("Hotspot", False, 0)
	show_display("Go to Interface", False, 1)



def get_wifi_credentials():
	#logger.debug('Getting wifi credentials from file')
	try:
		with open(WIFI_CREDENTIALS_FILE) as wifi_file:
			data=json.load(wifi_file)
			if (data['wifi_ssid'] == '') or (data['wifi_pwd'] == ''):
				return 0, 0
			return data['wifi_ssid'], data['wifi_pwd']
	except FileNotFoundError as e:
		logger.error('FileNotFoundError:\n{}'.format(e))
		with open(WIFI_CREDENTIALS_FILE, 'w') as f:
			f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	logger.debug("no file/ssid/pwd!")
	return 0, 0



def is_wifi_driver_loaded():
	try:
		result = subprocess.run(['sudo', 'iw', 'dev'], capture_output=True, text=True)
		output = result.stdout.strip()

		if "Interface" in output:
			return True
		else:
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
	# SSID is new, so replace the conf file
	file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
	file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
	file.write("\nnetwork={\n")
	file.write("\tssid=\"" + wifi_ssid + "\"\n")
	file.write("\tpsk=\"" + wifi_pwd + "\"\n")
	file.write("\tscan_ssid=1\n")
	file.write("}")
	file.close()


def is_wifi_in_range(wifi_name):
	retries = 3
	attempts=1
	max_attempts = 3
	while attempts <= max_attempts:
		try:
			# Running the command to list all available Wi-Fi networks
			for _ in range(retries):
				scan_output = subprocess.check_output(['iwlist', 'wlan0', 'scan'], stderr=subprocess.STDOUT).decode('utf-8')
				# Checking if the specified Wi-Fi name is in the output
				if wifi_name in scan_output:
					logger.debug("Found known WiFi in range!")
					return True
				time.sleep(2)  # Wait before retrying the scan
			logger.debug("Did not see my last WiFi :( So creating my own")
			return False
		except subprocess.CalledProcessError as e:
			logger.error(f"Attempt {attempts}: Command '{e.cmd}' returned non-zero exit status {e.returncode}. Trying again in 3 seconds...")
			time.sleep(3)  # Wait for 3 seconds before retrying the entire function

		attempts += 1  # Increment the attempt counter

	# After exhausting all attempts, log and return False
	logger.error("Failed to execute WiFi Scan after multiple attempts. Giving up.")
	return False

def connect_to_wifi(wifi_ssid, wifi_pwd, we_already_had_a_successful_connection):
	logger.debug("trying to establish connection to wifi %s ", wifi_ssid)
	show_display("Connecting to WiFi", False, 0)
	show_display(f"{wifi_ssid}", False, 1)

	#if (we_already_had_a_successful_connection is False):
	wifi_bssid = None
	create_wpa_supplicant(wifi_ssid, wifi_pwd)
	# stop the AP
	logger.debug("created wpa_supplicant.conf and stopping hostapd/accesspoint now")

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
	p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
	p.communicate()
	p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
	p.communicate()
	p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
	p.communicate()
	#force_wlan0_reset()
	#time.sleep(15)
	# wait until the wifi is connected
	logger.debug("dhcpcd is restarting and trying to connect to your WiFi")
	# check connection	
	retries=3
	for attempt in range(retries):
		logger.debug(f"Connection attempt {attempt+1}")
		if check_connection():
			stop_access_point()
			if not check_service_running('bcMeter'):
				run_bcMeter_service()

				show_display(f"Conn OK", False, 0)
				show_display(f"Starting up", False, 1)


			break
		elif attempt < retries:
			logger.debug("Connection not OK, retry" if attempt == 0 else "Still no connection, resetting interface")
			force_wlan0_reset()
			time.sleep(3)
	else:
		logger.error(f"Unable to establish a connection after {retries} retries. Check credentials")





def prime_control_loop():
	we_already_had_a_successful_connection = False
	is_online = False
	wifi_ssid, wifi_pwd=get_wifi_credentials()

	if (wifi_ssid and wifi_pwd) and (wifi_ssid != 0 and wifi_pwd != 0):
		logger.debug("checking for WiFi config")
		wifi_in_range=is_wifi_in_range(wifi_ssid) 
		if (wifi_in_range is False):
			logger.debug(f"last known wifi not in range , opening hotspot")
			setup_access_point()
		else:
			logger.debug(f"found data for {wifi_ssid}, trying to connect")
			print(f"found data for {wifi_ssid}, trying to connect")
			we_already_had_a_successful_connection = True
			connect_to_wifi(wifi_ssid,wifi_pwd, we_already_had_a_successful_connection)
			is_online = check_connection()
	else:
			logger.debug(f"no wifi config found, opening hotspot")
			setup_access_point()
	
	if (is_online is True):
		logger.debug("online at startup, starting bcMeter service")
		stop_access_point()
		run_bcMeter_service()

	return wifi_ssid, wifi_pwd, is_online, we_already_had_a_successful_connection


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

def check_service_running(service_name):
	try:
		result = subprocess.run(['systemctl', 'is-active', service_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		return result.stdout.decode().strip() == 'active'
	except subprocess.CalledProcessError:
		return False



def ap_control_loop():
	update_interface_status(4)
	wifi_ssid, wifi_pwd, is_online, we_already_had_a_successful_connection = prime_control_loop()
	logger.debug("Entering main loop")
	print("Entering main loop")
	keep_running = False
	try:
		while True:

			config = load_config_from_json()
			is_online = check_connection()
			uptime = get_uptime()
			is_ebcMeter = config.get('is_ebcMeter', False)
			run_hotspot = config.get('run_hotspot', False)
			run_hotspot = True if (is_ebcMeter) else run_hotspot
			bcMeter_running = check_service_running("bcMeter")
			bcMeter_flask_running = check_service_running("bcMeter_flask")

			if not bcMeter_running:
				update_interface_status(4 if not is_online else 0)

			if not bcMeter_flask_running:
				subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()

			if not is_online:
				if not run_hotspot:
					wifi_ssid, wifi_pwd = get_wifi_credentials()
					if uptime >= keep_hotspot_alive_without_successful_connection: 
						if not we_already_had_a_successful_connection and not keep_running:
							if bcMeter_running:
								print(f"bcMeter is running, so we keep measuring.")
								logger.debug("bcMeter is running, so we keep measuring.")
								update_interface_status(3)
								keep_running = True
								we_already_had_a_successful_connection = True
								logger.debug("we seem to have lost connection")
								connect_to_wifi(wifi_ssid, wifi_pwd, we_already_had_a_successful_connection)
							else:
								logger.debug("Shutting down because no configuration")
								stop_bcMeter_service()
								show_display("Shutting down", False, 0)
								show_display("No Config", False, 1)
								stop_access_point()
								os.system("shutdown now -h")
				if wifi_ssid and wifi_pwd:
					print(f"Reconnect to {wifi_ssid}")
					logger.debug(f"Try to reconnect to {wifi_ssid}")
					connect_to_wifi(wifi_ssid, wifi_pwd, we_already_had_a_successful_connection)

			if is_online and not run_hotspot:
				stop_access_point()
				we_already_had_a_successful_connection = True

			time.sleep(5)
	except Exception as e:
		logger.error(f"Exited AP Main loop: {e}")
		print(f"Exited AP Main loop: {e}")


GPIO.setwarnings(False) # Ignore warning for now
try:
	GPIO.setmode(GPIO.BCM) 
except:
	pass #was already set 
GPIO.setup(bcMeter_button_gpio, GPIO.IN, pull_up_down=GPIO.PUD_UP) # Set pin 10 to be an input pin and set initial value to be pulled low (off)

button_press_count = 0
last_press_time = 0

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
if not debug:
	ap_control_loop()
else:
	print("HAPPY DEBUGGING")
	while True:
		time.sleep(1)

