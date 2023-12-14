
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

enable_wifi = getattr(bcMeterConf, 'enable_wifi', True)
is_ebcMeter = getattr(bcMeterConf, 'is_ebcMeter', False)

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



logger.debug("bcMeter Network Handler started")

if (enable_wifi is False):
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "down"])
	p.communicate()
	stop_access_point()
	sys.exit()


# endpoint for checking internet connection (this is Google's public DNS server)
DNS_HOST = "8.8.8.8"
DNS_PORT = 53
DNS_TIME_OUT = 3

we_already_had_a_successful_connection=False

#wifi credentials file
WIFI_CREDENTIALS_FILE='/home/pi/bcMeter_wifi.json'



#stop hotspot from being active after 10 Minutes of running (can be overridden by parameter run_hotspot=True)
keep_hotspot_alive_without_successful_connection = 600

def check_exit_status(service):
	status =""
	output =str(subprocess.run(["systemctl", "status", service], capture_output=True, text=True).stdout.strip("\n"))
	output=output.splitlines()
	for line in output:
		if "Process:" in line:
			status = str(line.split("code=")[1]).split(",")[0]
			break
	return status



def stop_access_point():
	p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
	p.communicate()




def stop_bcMeter_service():
	p = subprocess.Popen(["sudo", "systemctl", "stop", "bcMeter"]).communicate()
	p = subprocess.Popen(["sudo", "systemctl", "disable", "bcMeter"]).communicate()

	#logger.debug("bcMeter service disabled.")

def activate_dnsmasq_service():
	#p = subprocess.Popen(["sudo", "systemctl", "enable", "dnsmasq"]).communicate()
	p = subprocess.Popen(["sudo", "systemctl", "start", "dnsmasq"]).communicate()
	#logger.debug("Dnsmasq service activated.")


def deactivate_dnsmasq_service():
	p = subprocess.Popen(["sudo", "systemctl", "stop", "dnsmasq"]).communicate()
	p = subprocess.Popen(["sudo", "systemctl", "disable", "dnsmasq"]).communicate()
	#logger.debug("Dnsmasq service deactivated.")

def run_bcMeter_service():
	#p = subprocess.call(["sudo", "systemctl", "enable", "bcMeter"])
	deactivate_dnsmasq_service()
	p = subprocess.Popen(["sudo", "systemctl", "start", "bcMeter"]).communicate()

	#logger.debug("bcMeter service activated.")

def force_wlan0_reset():
	logger.debug("forcing wlan0 reset")
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "down"])
	p.communicate()
	p = subprocess.Popen(["sudo", "ip", "link", "set", "wlan0", "up"])
	p.communicate()

def setup_access_point():
	deactivate_dnsmasq_service()
	stop_access_point()
	#reset wpa_supplicant
	file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
	file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
	file.close()

	#reset our own wifi conf
	with open(WIFI_CREDENTIALS_FILE, 'w') as f:
		f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)


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


	process = subprocess.run(['systemctl', 'status', 'dnsmasq'], stdout=subprocess.PIPE)
	if 'active (running)' not in process.stdout.decode('utf-8'):
		activate_dnsmasq_service()



	logger.debug("started dnsmasq")
	p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
	p.communicate()
	logger.debug("daemon reloaded")
	p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
	p.communicate()
	# restart the AP
	p = subprocess.Popen(["sudo", "systemctl", "start", "hostapd"])
	p.communicate()
	logger.debug("hostapd started")



def check_connection():
	for _ in range(3):
		try:
			# Attempt to create a socket connection to Google's DNS server (8.8.8.8) on port 53.
			socket.create_connection(("8.8.8.8", 53), timeout=1)
			return True
		except OSError:
			time.sleep(2)
	return False

def get_uptime():
	with open('/proc/uptime', 'r') as f:
		uptime = float(f.readline().split()[0])
		return uptime
	return None

def get_wifi_credentials():
	#logger.debug('Getting wifi credentials from file')
	try:
		with open(WIFI_CREDENTIALS_FILE) as wifi_file:
			data=json.load(wifi_file)
			return data['wifi_ssid'], data['wifi_pwd']
	except FileNotFoundError as e:
		logger.debug('FileNotFoundError:\n{}'.format(e))
		with open(WIFI_CREDENTIALS_FILE, 'w') as f:
			f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	logger.debug("no file/ssid/pwd!")
	return '', ''

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

stop_bcMeter_service() #if service was enabled and device was not shutdown properly (=service disabled), it will startup immediately even if we dont want to		


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
		logger.debug("Wi-Fi driver is not enabled or loaded. Retrying in 5 seconds...")
		time.sleep(2)  # Wait for 5 seconds before retrying



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


def connect_to_wifi(wifi_ssid, wifi_pwd,we_already_had_a_successful_connection):
	logger.debug("trying to establish connection to wifi %s ", wifi_ssid)
	wifi_bssid = None
	create_wpa_supplicant(wifi_ssid, wifi_pwd)
	# stop the AP
	logger.debug("created wpa_supplicant.conf and stopping hostapd/accesspoint now")
	p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
	p.communicate()
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
	p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
	p.communicate()
	p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
	p.communicate()
	time.sleep(5)
	# wait until the wifi is connected
	logger.debug("dhcpcd is restarting and trying to connect to your WiFi")
	# check connection	
	if (check_connection() is True):
		logger.debug("Connection OK, starting bcMeter Service (1)")
		logger.debug("Stopping access point...")

		stop_access_point()

		run_bcMeter_service()
	else:
		logger.debug("Connection not OK, retry")
		time.sleep(3)
		if check_connection() is False:
			logger.error("Still no connection, resetting interface")
			force_wlan0_reset()
			time.sleep(5)
			if (check_connection() is True):
				logger.debug("Connection OK, starting bcMeter Service (2)")
				logger.debug("Stopping access point...")

				stop_access_point()
				run_bcMeter_service()
			else:
				uptime=get_uptime()
				logger.error("Still no connection, or WiFi out of range? Check credentials. Unable to connect to mesh repeater or 5GHz WiFi. Uptime: %s", uptime)
				if (uptime >= keep_hotspot_alive_without_successful_connection) and (we_already_had_a_successful_connection is False):
					logger.debug("shutting down hotspot now as we tried longer than the defined duration")
					stop_access_point()	
					os.system("shutdown now -h")

				if (uptime <= keep_hotspot_alive_without_successful_connection) and (we_already_had_a_successful_connection is False):
					logger.debug("Deleting wifi credentials")
					with open(WIFI_CREDENTIALS_FILE, 'w') as f:
						f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
					os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
					logger.debug("setting up access point again")
					setup_access_point()
					#raise Exception
		else:
			logger.debug("Connection OK, starting bcMeter Service (3)")
			logger.debug("Stopping access point...")

			stop_access_point()
			run_bcMeter_service()	





def prime_control_loop(we_already_had_a_successful_connection):
	wifi_ssid, wifi_pwd=get_wifi_credentials()
	is_online = check_connection() #initial ping Google determines if we're online
	logger.debug("We are online: %s",is_online)

	if (is_online is True):
		if (len(wifi_ssid) > 0) and (len(wifi_pwd) > 0):
			we_already_had_a_successful_connection = True
			logger.debug("online at startup, starting bcMeter service (0)")
			deactivate_dnsmasq_service()
			stop_access_point()
			run_bcMeter_service()
	else:
		if (len(wifi_ssid) > 1) and (len(wifi_pwd) > 1):
			connect_to_wifi(wifi_ssid,wifi_pwd, is_online)
			is_online = check_connection() #initial ping Google determines if we're online
			if is_online is True:
				logger.debug("found wifi and reconnect")
			else:		
				we_already_had_a_successful_connection = False
				logger.debug("no connection but wifi credentials on startup, so here is the accesspoint! (1)")
				setup_access_point()
		else:		
			we_already_had_a_successful_connection = False
			logger.debug("no connection and no wifi credentials on startup, so here is the accesspoint! (2)")
			setup_access_point()
	if (len(wifi_ssid)!=0) and (len(wifi_pwd)!=0):
		return wifi_ssid, wifi_pwd, is_online
	else: return 0,0, is_online

def ap_control_loop(wifi_ssid, wifi_pwd, is_online):
	while True:
		is_online= check_connection()
		importlib.reload(bcMeterConf)
		uptime=get_uptime()
		if (is_online is False) and (bcMeterConf.run_hotspot is False): 
			wifi_ssid, wifi_pwd=get_wifi_credentials()
			if (uptime >=keep_hotspot_alive_without_successful_connection) and ((wifi_ssid)==0): #make sure to shutdown after 10 minutes but keep running if connection lost for other reasons
				logger.debug("up too long go sleep")
				stop_access_point()
				stop_bcMeter_service()
				os.system("shutdown now -h")
			if (len(wifi_ssid)>1 ): #we've been online already but lost wifi signal. try to reconnect...
				connect_to_wifi(wifi_ssid,wifi_pwd, we_already_had_a_successful_connection)
		if (is_online == True) and (bcMeterConf.run_hotspot is False):
	#		if (len(wifi_ssid) > 0) and (we_already_had_a_successful_connection is True): #while being online the wifi is deleted and we suspect the hotspot is required
			we_already_had_a_successful_connection= True #if connection set up once, do not stop everything later just because for example weak wifi signal. 
		if (is_online is False) and (we_already_had_a_successful_connection is True):
			if (len(wifi_ssid)>1 ): #we've been online already but lost wifi signal. try to reconnect...
				connect_to_wifi(wifi_ssid,wifi_pwd, we_already_had_a_successful_connection)

		time.sleep(10)
wifi_ssid, wifi_pwd, is_online = prime_control_loop(we_already_had_a_successful_connection)
ap_control_loop(wifi_ssid, wifi_pwd, is_online)
