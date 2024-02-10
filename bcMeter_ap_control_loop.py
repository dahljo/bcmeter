
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
import bcMeterConf
import importlib
import logging
from datetime import datetime

from board import SCL, SDA, I2C
import busio, smbus

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1

ctrl_lp_ver="0.8.0"

enable_wifi = getattr(bcMeterConf, 'enable_wifi', True)
is_ebcMeter = getattr(bcMeterConf, 'is_ebcMeter', False)
use_display = getattr(bcMeterConf, 'use_display', False)

# Create the log folder if it doesn't exist
log_folder = '/home/pi/maintenance_logs/'
log_entity = 'ap_control_loop'
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

current_datetime_timestamp = time.time() #script started

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

use_display = getattr(bcMeterConf, 'use_display', False)


logger.debug(f"bcMeter Network Handler started (v{ctrl_lp_ver})")

if (enable_wifi is False):
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "down"])
	p.communicate()
	stop_access_point()
	sys.exit()


if (use_display is True):
	try:
		from oled_text import OledText, Layout64, BigLine, SmallLine
		oled = OledText(i2c, 128, 64)

		oled.layout = {
			1: BigLine(5, 0, font="Arimo.ttf", size=20),
			2: SmallLine(5, 25, font="Arimo.ttf", size=14),
			3: SmallLine(5, 40, font="Arimo.ttf", size=14)

		}
		logger.debug("Display found (1)")
		
	except ImportError:
		logger.error("No display driver installed, update the device (1)")

def show_display(message, line, clear):
	if (use_display is True):
		if clear is True:
			oled.clear()
		oled.text(str(message),line+1)


show_display(f"Init WiFi", True, 0)
show_display(f"Ctrl Loop {ctrl_lp_ver}", False, 1)




# endpoint for checking internet connection (this is Google's public DNS server)
DNS_HOST = "8.8.8.8"
DNS_PORT = 53
DNS_TIME_OUT = 3

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



def check_connection():
	for _ in range(2):
		try:
			# Attempt to create a socket connection to Google's DNS server (8.8.8.8) on port 53.
			socket.create_connection(("8.8.8.8", 53), timeout=1)
			return True
		except OSError:
			time.sleep(1)
	return False

def get_uptime():
	uptime = time.time()-current_datetime_timestamp
	return uptime


def setup_access_point():
	#deactivate_dnsmasq_service()
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
			if (data['wifi_ssid'] == '') and (data['wifi_pwd'] == ''):
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
			run_bcMeter_service()

			show_display(f"Conn OK", False, 0)
			show_display(f"Starting bcMeter", False, 1)


			break
		elif attempt < retries:
			logger.debug("Connection not OK, retry" if attempt == 0 else "Still no connection, resetting interface")
			force_wlan0_reset()
			sleep(3)
	else:
		logger.error(f"Unable to establish a connection after {retries} retries. Check credentials")





def prime_control_loop():
	we_already_had_a_successful_connection = False
	is_online = False
	wifi_ssid, wifi_pwd=get_wifi_credentials()

	if (wifi_ssid != 0) and (wifi_pwd != 0):
		logger.debug("checking for WiFi config")
		wifi_in_range=is_wifi_in_range(wifi_ssid) 
		if (wifi_in_range is False):
			logger.debug(f"last known wifi not in range , opening hotspot")
			setup_access_point()
		else:
			logger.debug(f"found data for {wifi_ssid}, trying to connect")
			we_already_had_a_successful_connection = True
			connect_to_wifi(wifi_ssid,wifi_pwd, we_already_had_a_successful_connection)
			is_online = check_connection()
	elif (wifi_ssid == 0) or (wifi_pwd == 0):
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


def ap_control_loop(wifi_ssid, wifi_pwd, is_online, we_already_had_a_successful_connection):
	logger.debug("Entering main loop")
	keep_running = False
	while True:
		is_online= check_connection()
		importlib.reload(bcMeterConf)
		uptime=get_uptime()
		if (is_online is False) and (bcMeterConf.run_hotspot is False): 
			wifi_ssid, wifi_pwd=get_wifi_credentials()
			if (uptime >=keep_hotspot_alive_without_successful_connection): 
				if (we_already_had_a_successful_connection is False) and (keep_running is False): #make sure to shutdown after 10 minutes but keep running if connection lost for other reasons
					service_name = 'bcMeter.service'
					if check_service_running(service_name):
						print(f"{service_name} is running, so we keep measuring.")
						keep_running = True
						we_already_had_a_successful_connection = True
						logger.debug("we seem to have lost connection")
					else:
						logger.debug("Shutting down because no configuration")
						stop_bcMeter_service()
						show_display(f"Shutting down", False, 0)
						show_display(f"No Config", False, 1)
						#stop_access_point()
						#os.system("shutdown now -h")
			else:
				if (wifi_ssid != 0) and (wifi_pwd != 0): #we've been online already but lost wifi signal. try to reconnect...
					logger.debug(f"try to reconnect to {wifi_ssid}")
					connect_to_wifi(wifi_ssid,wifi_pwd, we_already_had_a_successful_connection)
		if (is_online is True) and (bcMeterConf.run_hotspot is False):
			stop_access_point()
	#		if (len(wifi_ssid) > 0) and (we_already_had_a_successful_connection is True): #while being online the wifi is deleted and we suspect the hotspot is required
			we_already_had_a_successful_connection= True #if connection set up once, do not stop everything later just because for example weak wifi signal. 
		if (is_online is False) and (we_already_had_a_successful_connection is True):
			if (wifi_ssid != 0) and (wifi_pwd != 0):
				connect_to_wifi(wifi_ssid,wifi_pwd, we_already_had_a_successful_connection)
		time.sleep(5)


wifi_ssid, wifi_pwd, is_online, we_already_had_a_successful_connection = prime_control_loop()
ap_control_loop(wifi_ssid, wifi_pwd, is_online, we_already_had_a_successful_connection)
