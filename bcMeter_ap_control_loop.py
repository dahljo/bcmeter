
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
from bcMeter_shared import load_config_from_json, check_connection, update_interface_status, show_display, config, setup_logging, get_pinout_info, find_model_number, run_command
import importlib
from datetime import datetime
import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
from board import SCL, SDA, I2C
import busio, smbus
from sys import argv
from threading import Thread, Event

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1

ctrl_lp_ver="0.9.49 2024-11-22"
subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()

time_synced = False

logger = setup_logging('ap_control_loop')


logger.debug(f"bcMeter Network Handler started (v{ctrl_lp_ver})")
pinout_output = get_pinout_info()
if pinout_output:
	logger.debug(find_model_number(pinout_output))

base_dir = '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

try:
	if os.path.exists(base_dir + '/bcMeter_config.json'):
		config = load_config_from_json()
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
WIFI_CREDENTIALS_FILE=base_dir + '/bcMeter_wifi.json'



#stop hotspot from being active after a while (can be overridden by parameter run_hotspot=True)
keep_hotspot_alive_without_successful_connection = 3600


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
		#run_command("iptables -F")
		#run_command("iptables -t nat -F")
		run_command("sudo systemctl stop hostapd")


def stop_bcMeter_service():
	update_interface_status(0)
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
	#p = subprocess.Popen(["sudo", "systemctl", "unmask","hostapd"])
	#p.communicate()
	#stop_access_point()
	
	#reset wpa_supplicant
	file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
	file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
	file.close()

	#reset our own wifi conf
	#with open(WIFI_CREDENTIALS_FILE, 'w') as f:
	#	f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
	#	os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	#
	#logger.debug("Reset WiFi Configs")

	prepare_dhcpd_conf(1)

	activate_dnsmasq_service()
	run_command("sudo systemctl daemon-reload")
	logger.debug("daemon reloaded")
	run_command("sudo service dhcp restart")
	# restart the AP
	#run_command("iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j DNAT --to-destination 192.168.18.8:80")
	#run_command("iptables -t nat -A POSTROUTING -j MASQUERADE")
	run_command("sudo systemctl start hostapd")
	logger.debug("hostapd started")
	show_display("Hotspot", False, 0)
	show_display("Go to Interface", False, 1)



def get_wifi_credentials():
	#logger.debug('Getting wifi credentials from file')
	try:
		with open(WIFI_CREDENTIALS_FILE) as wifi_file:
			data=json.load(wifi_file)
			if (data['wifi_ssid'] == '') or (data['wifi_pwd'] == ''):
				return None, None
			return data['wifi_ssid'], data['wifi_pwd']
	except FileNotFoundError as e:
		logger.error('FileNotFoundError:\n{}'.format(e))
		with open(WIFI_CREDENTIALS_FILE, 'w') as f:
			f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	logger.debug("no file/ssid/pwd!")
	return None, None



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
	reset_wlan0()

	return False



def prepare_dhcpd_conf(option):
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
		file.write("interface wlan0\n")
		file.write("  static ip_address=192.168.18.8/24\n")
		file.write("  nohook wpa_supplicant")
		file.close()

		logger.debug("edited dhcpcd for AP")






def connect_to_wifi():
	wifi_ssid, wifi_pwd = get_wifi_credentials()
	if wifi_ssid == None and wifi_pwd == None:
		if check_service_running("hostapd") is False:
			logger.debug("Setup AP cause no SSID / PWD")
			setup_access_point()
	else:
		wifi_in_range = is_wifi_in_range(wifi_ssid)
		if wifi_in_range is False:
			if check_service_running("hostapd") is False:
				logger.debug("Known WiFi not in range so I am opening the hotspot")
				setup_access_point()
		else:
			logger.debug("Found credentials for wifi %s", wifi_ssid)
			if wifi_ssid != get_wifi_network():
				logger.debug(f"Trying to establish connection to Wi-Fi {wifi_ssid}")
				show_display("Connecting to WiFi", False, 0)
				show_display(f"{wifi_ssid}", False, 1)
				create_wpa_supplicant(wifi_ssid, wifi_pwd)
				# Stop the access point if it is running and reset dhcpcd configuration
				prepare_dhcpd_conf(0)
				stop_access_point()

				subprocess.Popen(["sudo", "systemctl", "daemon-reload"]).communicate()
				logger.debug("reloading dhcpcd")
				subprocess.Popen(["sudo", "service", "dhcpcd", "restart"]).communicate()
				# Attempt to connect to the Wi-Fi
				logger.debug("dhcpcd is restarting and trying to connect to your Wi-Fi")
				retries = 3
				for attempt in range(retries):
					logger.debug(f"Connection attempt {attempt + 1}")
					if check_connection():
						if not check_service_running('bcMeter'):
							run_bcMeter_service()
							show_display(f"Conn OK", False, 0)
							show_display(f"Starting up", False, 1)
						else:
							show_display(f"Conn OK", False, 0)
							show_display(f"Sampling", False, 1)
						break
					else:
						logger.debug("Connection not OK, resetting interface and retrying")
						force_wlan0_reset()
						time.sleep(3)
				if wifi_ssid == get_wifi_network():
					logger.debug("stopping accesspoint; i seem to be offline but connected to the desired wifi") 
					stop_access_point()
			else:
				if check_connection():
					if not check_service_running('bcMeter'):
						run_bcMeter_service()
						show_display(f"Conn OK", False, 0)
						show_display(f"Starting up", False, 1)
					else:
						show_display(f"Conn OK", False, 0)
						show_display(f"Sampling", False, 1)
					
				



def reset_wlan0():
	try:
		subprocess.run(["sudo", "rfkill", "unblock", "all"], check=True)
		logger.debug("Bringing down wlan0 interface...")
		subprocess.run(["sudo", "ip", "link", "set", "wlan0", "down"], check=True)


		logger.debug("Bringing up wlan0 interface...")
		subprocess.run(["sudo", "ip", "link", "set", "wlan0", "up"], check=True)


	except Exception as e:
		logger.error(f"An unexpected error occurred: {e}")



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


def ap_control_loop():
	global time_synced
	config = load_config_from_json()
	keep_running = we_got_correct_time = is_online = False
	scan_interval = 10
	run_hotspot = config.get('run_hotspot', False)
	is_ebcMeter = config.get('is_ebcMeter', False)
	wifi_ssid, wifi_pwd = get_wifi_credentials()
	update_interface_status(4)
	if not run_hotspot and (wifi_ssid != None and wifi_pwd != None):
		connect_to_wifi()
		stop_time_sync_thread = Event()
		time_sync_thread = Thread(target=time_sync_check_loop, args=(stop_time_sync_thread,))
		time_sync_thread.start()
	if run_hotspot or (wifi_ssid == None and wifi_pwd is None):
		setup_access_point()	
	logger.debug("bcMeter AP Control Loop initialized")

	if (not wifi_ssid and not wifi_pwd):
		run_hotspot = True if is_ebcMeter else run_hotspot

	while True:
		time_start=time.time()
		config = load_config_from_json()
		is_online = check_connection()
		if time_synced and we_got_correct_time is False:
			uptime = get_uptime()
			we_got_correct_time = True
		else:
			uptime = keep_hotspot_alive_without_successful_connection-1
		run_hotspot = config.get('run_hotspot', False)
		bcMeter_running = check_service_running("bcMeter")
		bcMeter_flask_running = check_service_running("bcMeter_flask")
		if not bcMeter_running:
			update_interface_status(4 if not is_online else 0)
		else:
			update_interface_status(3 if not is_online else 2)
		if not bcMeter_flask_running:
			subprocess.Popen(["sudo", "systemctl", "start", "bcMeter_flask.service"]).communicate()
		if not is_online:
			#logger.debug("Not online")
			if not run_hotspot:
				if (time_synced is False):
					keep_running = True
				if uptime >= keep_hotspot_alive_without_successful_connection:
					if is_ebcMeter:
						keep_running = True
					if not keep_running:
						logger.debug("Still in configuration timeframe")
						logger.debug("No sampling running")
						if bcMeter_running:
							logger.debug("bcMeter is running, so we keep measuring and override the shutdown timer in hotspot mode. make sure to configure it properly!")
							update_interface_status(3)
							keep_running = True
							logger.debug("Wi-Fi connection lost. Attempting to reconnect.")
							connect_to_wifi()
						else:
							logger.debug("Shutting down due to inactivity.")
							stop_bcMeter_service()
							show_display("Shutting down", False, 0)
							show_display("No Config", False, 1)
							stop_access_point()
							os.system("shutdown now -h")
				else:
					connect_to_wifi()


		if (is_online is True) and (run_hotspot is False):
			if (check_service_running("hostapd")):
				stop_access_point()
				logger.debug("(1) Connection ok so stopping hotspot")


		time.sleep(scan_interval)
		#logger.debug("AP loop took ", time.time()-time_start)




if not debug:
	stop_access_point()
	reset_wlan0()
	ap_control_loop()
else:
	logger.debug("HAPPY DEBUGGING")
	while True:
		time.sleep(1)

