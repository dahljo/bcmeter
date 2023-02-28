
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


# endpoint for checking internet connection (this is Google's public DNS server)
DNS_HOST = "8.8.8.8"
DNS_PORT = 53
DNS_TIME_OUT = 3

#status constants
STATUS_OK=1
STATUS_NOK=0
keep_running=False

# sleep timeintervals
SERVICE_WAIT_TIME = 3 			

#wifi credentials file
WIFI_CREDENTIALS_FILE='/home/pi/bcMeter_wifi.json'

#stop hotspot from being active after 10 Minutes of running (can be overridden by parameter run_hotspot=True)
hotspot_maxtime = 600
#var and function for the interrupt from php // not used for bcMeter but might be handy later
BREAK_LOOP=False

def print_to_file(string):
	print(string)
	file = "/home/pi/ap_control_loop.log"
	current_time = time.localtime()
	timestamp = "["+ time.strftime("%H:%M:%S", current_time) +"]"
	string = timestamp + " " + str(string) + "\n"
	with open(file, 'a+') as f:
		f.write(string)

def signal_received(signal_number, frame):
	global BREAK_LOOP
	BREAK_LOOP=True
	#print_to_file('Interrupt received!')
	signal.signal(signal.SIGUSR1, signal_received)    

def run_bcMeter_service():
	p = subprocess.call(["sudo", "systemctl", "enable", "bcMeter"])
	p = subprocess.call(["sudo", "systemctl", "start", "bcMeter"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("bcMeter service activated.")


def stop_bcMeter_service():
	p = subprocess.call(["sudo", "systemctl", "stop", "bcMeter"])
	p = subprocess.call(["sudo", "systemctl", "disable", "bcMeter"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("bcMeter service disabled.")

def activate_dnsmasq_service():
	p = subprocess.call(["sudo", "systemctl", "enable", "dnsmasq"])
	p = subprocess.call(["sudo", "systemctl", "start", "dnsmasq"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("Dnsmasq service activated.")


def deactivate_dnsmasq_service():
	p = subprocess.call(["sudo", "systemctl", "stop", "dnsmasq"])
	p = subprocess.call(["sudo", "systemctl", "disable", "dnsmasq"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("Dnsmasq service deactivated.")


def setup_access_point():
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

	activate_dnsmasq_service()

	# rewrite the last 3 lines (always after #bcMeterConfig)
	file = open("/etc/dhcpcd.conf", "a")
	file.write("interface wlan0\n")
	file.write("  static ip_address=192.168.18.8/24\n")
	file.write("  nohook wpa_supplicant")
	file.close()
	
	p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
	p.communicate()

	# restart the AP
	p = subprocess.Popen(["sudo", "systemctl", "start", "hostapd"])
	p.communicate()
	#start bcMeter routine
	#if bcMeterConf.run_hotspot is True:
	#	print_to_file("starting bcMeter in hotspot mode ")
	#	run_bcMeter_service()

def stop_access_point():
	print_to_file("Stopping access point...")
	p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
	p.communicate()

def check_connection():
	connection_ok = False
	current_time = 0
	while current_time < 5:
		try:
			socket.setdefaulttimeout(DNS_TIME_OUT)
			socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((DNS_HOST, DNS_PORT))
			connection_ok = True
			break
		except Exception:
			current_time += 1
			time.sleep(1)
	

	
	return connection_ok

def get_uptime():
	with open('/proc/uptime', 'r') as f:
		uptime = float(f.readline().split()[0])
		return uptime
	return None

def get_wifi_credentials():
	#print_to_file('Getting wifi credentials from file')
	try:
		with open(WIFI_CREDENTIALS_FILE) as wifi_file:
			data=json.load(wifi_file)
			return data['wifi_ssid'], data['wifi_pwd']
	except FileNotFoundError as e:
		print_to_file('FileNotFoundError:\n{}'.format(e))
	print_to_file("no connection and i did not even try!")
	return '', ''

def get_wifi_bssid(ssid):
	print_to_file('... Getting wifi bssid for ssid={}'.format(ssid))
	ap_list=[]
	out_newlines=None
	for i in range(5):              #try max 5 times
		print_to_file('\ttrying... {}'.format(i))
		scan_cmd='sudo iw dev wlan0 scan ap-force'
		process = subprocess.Popen([scan_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		out, err = process.communicate()
		if(len(err)==0):                                                #the command did not produce an error so e can process the list of access points
			out_newlines=str(out).replace('\\n', '\n')                  #because of the bytes to str conversion newlines are \\n instead of \n
			break
		else:
			print_to_file('\terror: {}'.format(err))
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
	
	print_to_file('Access points found for ssid={}:'.format(ssid))
	for ap in ap_list:
		ap_list=[x for x in ap_list if x['frequency']<2500]                 #filter for 2.4 GHz wifi band -> freqs lower than 2500 MHz
		ap_list=sorted(ap_list, key=lambda x: x['signal'], reverse=True)    #sort on signal_level
	
	if(len(ap_list)>0):
		print_to_file('Using access point: {}'.format(ap_list[0]))
		return ap_list[0]['bssid']
	else:
		print_to_file('Did not find any access points')
		return None
		
connection_ok= check_connection()

if(connection_ok is False):
	status = STATUS_NOK
	keep_running = False
	#print_to_file("no connection on startup, so here is the accesspoint!")
	setup_access_point()
else:
	print_to_file("online now starting bcMeter service")
	deactivate_dnsmasq_service()
	stop_access_point()
	run_bcMeter_service()
	status = STATUS_OK



while True:
	uptime=get_uptime()
	if (status == STATUS_NOK):
		if (uptime >=hotspot_maxtime) and (bcMeterConf.run_hotspot is False) and (keep_running is False): #make sure to shutdown after 10 minutes but keep running if connection lost for other reasons
			print_to_file("up too long go sleep")
			stop_access_point()
			stop_bcMeter_service()
			os.system("shutdown now -h")
		time.sleep(1)
		wifi_ssid, wifi_pwd=get_wifi_credentials()
		if len(wifi_ssid) > 0:
			print_to_file("trying to establishing connection to wifi")
			wifi_bssid = None
			# SSID is new, so replace the conf file
			file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
			file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
			file.write("\nnetwork={\n")
			if(not wifi_bssid): 
				file.write("\tssid=\"" + wifi_ssid + "\"\n")
			else:
				file.write("\tbssid=" + wifi_bssid + "\n")
			file.write("\tpsk=\"" + wifi_pwd + "\"\n")
			file.write("\tscan_ssid=1\n")
			file.write("}")
			file.close()
			print_to_file("created wpa_supplicant.conf and stopping hostapd now")
			# stop the AP
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
			print_to_file("restarting dhcpd to connect to wifi")
			p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
			p.communicate()
			# wait until the wifi is connected
			wait_time = 10
			print_to_file("... Services are restarting, waiting " + str(round(wait_time)) + " seconds...")
			time.sleep(wait_time)
			# check connection
			try:
				connection_ok= check_connection()
				if not connection_ok:
					print_to_file("Connection not OK, retry")
					sleep(10)
					connection_ok= check_connection()
					if not connection_ok:
						raise Exception
				else:
					stop_access_point()
					status = STATUS_OK
					# already in wifi mode, so do nothing
					deactivate_dnsmasq_service()
					print_to_file("Connection OK, starting bcMeter Service")
					keep_running=True
					run_bcMeter_service()
				
			except Exception:
				print_to_file("Connection problems")
				stop_access_point()
				file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
				file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
				file.close()
				if (uptime >=hotspot_maxtime) and (bcMeterConf.run_hotspot is False):
					print_to_file("shutting down hotspot because more than max tries.")
					stop_access_point()
				else:
					setup_access_point()
			#print_to_file("exiting through the gift shop")
	else:
		time.sleep(10)
		connection_ok= check_connection()
		if(connection_ok is False):
			status = STATUS_NOK
		else:
		 keep_running= True #if connection set up once, do not stop everything later just because for example weak wifi signal. 


