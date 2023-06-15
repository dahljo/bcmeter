#!/usr/bin/env python3
import time, traceback, os, sys, smbus, datetime, RPi.GPIO as GPIO, subprocess, numpy, os, busio, csv, typing, re, glob
from tabulate import tabulate
from pathlib import Path
from board import SCL, SDA, I2C
from time import sleep, strftime, time
from datetime import datetime
from threading import Thread
import socket, importlib, bcMeterConf
from bcMeter_adc import read_adc

os.chdir('/home/pi')

bcMeter_version = "0.9.85 2023-06-15"
compair_upload = bcMeterConf.compair_upload 

i2c = busio.I2C(SCL, SDA)
bus = smbus.SMBus(1) # 1 indicates /dev/i2c-1

sample_count = getattr(bcMeterConf, 'sample_count', 500)
#old versions use 7000
if (sample_count>1500):
	sample_count=1500

heating = getattr(bcMeterConf, 'heating', False)
pwm_freq = getattr(bcMeterConf, 'pwm_freq', 20)
debug = False #no need to change here

sht40_i2c = None

online = False
online = check_connection()


try:
	import adafruit_sht4x
except ImportError:
	if (online is True):
		subprocess.check_call(["pip3", "install", "adafruit-circuitpython-sht4x"])
		import adafruit_sht4x

try:
	sht = adafruit_sht4x.SHT4x(i2c)
	sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION

	temperature, relative_humidity = sht.measurements
	print("Temperature: %0.1f C" % temperature)
	print("Humidity: %0.1f %%" % relative_humidity)
	print("")
	sht40_i2c = True
except Exception as e:
	sht40_i2c = False

	print("Error: ", e)

sigma_air_880nm = 0.0000000777
run_once = "false"
no_bias = "false"
devicename = socket.gethostname()
#pwm for pump:
GPIO.setup(12,GPIO.OUT)           # initialize as an output.
#using switch to adjust air volume
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)

output_to_terminal = False 


pump_duty = GPIO.PWM(12,pwm_freq)         #GPIO12 as PWM output, with 20Hz frequency

sample_spot_areasize=numpy.pi*(0.50/2)**2 #area of spot in cm2 from bcmeter, diameter 0.50cm

POWERPIN = 26
BUTTON = 16

class TemperatureSensor:
	RETRY_INTERVAL = 0.5
	RETRY_COUNT = 10

	def __init__(self, channel: int):
		GPIO.setmode(GPIO.BCM)
		GPIO.setup(channel, GPIO.IN)
		GPIO.setup(1,GPIO.OUT)
		GPIO.setup(23,GPIO.OUT)
		
	#def __del__(self):
		#GPIO.cleanup()

	@staticmethod
	def read_device() -> typing.List[str]:
		device_file_name = glob.glob('/sys/bus/w1/devices/28*')[0] + '/w1_slave'
		with open(device_file_name, 'r') as fp:
			return [line.strip() for line in fp.readlines()]

	def get_temperature_in_milli_celsius(self) -> int:
		"""
		$ cat /sys/bus/w1/devices/28-*/w1_slave
		c1 01 55 05 7f 7e 81 66 c8 : crc=c8 YES
		c1 01 55 05 7f 7e 81 66 c8 t=28062
		"""
		for i in range(self.RETRY_COUNT):
			lines = self.read_device()
			if len(lines) >= 2 and lines[0].endswith('YES'):
				match = re.search(r't=(\d{1,6})', lines[1])
				if match:
					return int(match.group(1), 10)
			sleep(self.RETRY_INTERVAL)
		raise Exception(
			F'Cannot read temperature (tried {self.RETRY_COUNT} times with an interval of {self.RETRY_INTERVAL})'
		)


def get_location():
	import json
	import requests 
	my_ip = requests.get('https://api.ipify.org').text
	my_loc = requests.get('https://ipinfo.io/'+my_ip).text
	my_loc = json.loads(my_loc)
	my_lat =  float(my_loc['loc'].split(',')[0])
	my_lon = float(my_loc['loc'].split(',')[1])
	print(my_lat, my_lon)
	return [my_lat,my_lon]


def check_connection():
	current_time = 0
	while current_time < 5:
		try:
			socket.setdefaulttimeout(3)
			socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
			return True
		except Exception:
			current_time += 1
			sleep(1)


def startUp():
	global MCP3426_DEFAULT_ADDRESS, sample_time, sample_count, run_once, debug, no_bias
	cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
	process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	my_pid, err = process.communicate()
	bus = smbus.SMBus(1)
	if (debug is False):
		pump_duty.start(bcMeterConf.pump_dutycycle)     #generate PWM signal for pump
	if len(my_pid.splitlines()) > 1:
		sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
		sys.exit(1)
	else:
		if (len(sys.argv)>=2):
			if (sys.argv[1] == "debug"):
				sample_time = 1
				sample_count = 50
				run_once = "true"
				debug = True
		for device in range(128):
			try:
				adc = bus.read_byte(device)
				if (hex(device) == "0x68"):
					MCP3426_DEFAULT_ADDRESS = 0x68
				elif (hex(device) == "0x6a"):
					MCP3426_DEFAULT_ADDRESS = 0x6a
				elif (hex(device) == "0x6d"):
					MCP3426_DEFAULT_ADDRESS = 0x6d

			except: # exception if read_byte fails
				pass
		if (debug == True):
			print("ADC found at Address:", hex(MCP3426_DEFAULT_ADDRESS))

		GPIO.setmode(GPIO.BCM)
		GPIO.setup(POWERPIN, GPIO.OUT)
		GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP) 
		GPIO.setup(1,GPIO.OUT)
		GPIO.setup(23,GPIO.OUT)

			#for i in sys.argv:
			#	print(i)

		

def get_sensor_values(MCP3426_DEFAULT_ADDRESS,sample_count):
	main_sensor_value = reference_sensor_value = 0
	sensor_values = read_adc(MCP3426_DEFAULT_ADDRESS, sample_count)
	main_sensor_value = sensor_values[0]
	reference_sensor_value = sensor_values[1]
	if bcMeterConf.swap_channels is True:
		return reference_sensor_value, main_sensor_value
	return main_sensor_value, reference_sensor_value




def button_pressed():
	input_state = GPIO.input(16)
	if input_state == False:
		if (bcMeterConf.pump_dutycycle<=100) and (increase_duty  == True):
			bcMeterConf.pump_dutycycle+=5
		else:
			bcMeterConf.pump_dutycycle-=5
		if (bcMeterConf.pump_dutycycle == 100):
			increase_duty=False
		if (bcMeterConf.pump_dutycycle==0):
			increase_duty=True
		pump_duty.ChangeDutyCycle(bcMeterConf.pump_dutycycle)               #change duty cycle for varying the brightness of LED.
		time.sleep(0.1)
		print(bcMeterConf.pump_dutycycle)



def createLog(log,header):
	Path("/home/pi/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile("/home/pi/logs/log_current.csv"):
		os.remove("/home/pi/logs/log_current.csv")
	with open("/home/pi/logs/" + log, "a") as logfileArchive: #save this logfile for archive
		logfileArchive.write(header + "\n\n")
	with open("/home/pi/logs/log_current.csv", "a") as temporary_log: # temporary current logfile for web interface
		temporary_log.write(header + "\n\n")



def bcmeter_main():
	bcMeter_location = bcMeterConf.location
	filter_status = 0
	first_value = True
	samples_taken = 0
	sht_humidity=delay=reference_sensor_value=reference_sensor_bias=main_sensor_bias=bcmRefFallback=bcmSenRef=reference_sensor_value_current=main_sensor_value_current=main_sensor_value_last_run=attenuation_last_run=BCngm3=BCngm3pos=carbonRollAvg01=carbonRollAvg02=carbonRollAvg03=temperature_current=bcm_temperature_last_run=attenuation_coeff=absorption_coeff=0
	flag = ""
	calibrated = absorb = main_sensor_value = attenuation = attenuation_current = 0.0000
	today = str(datetime.now().strftime("%y-%m-%d"))
	now = str(datetime.now().strftime("%H:%M:%S"))
	logFileName =(str(today) + "_" + str(now) + ".csv").replace(':','')
	header="bcmDate;bcmTime;bcmRef;bcmSen;bcmATN;relativeLoad;BCngm3;Temperature;flag;main_sensor_bias;reference_sensor_bias;sampleDuration;sht_humidity"
	if (debug == False):
		print("Started new bcMeter log ", today, now, bcMeter_version, logFileName)
		createLog(logFileName,header)
		logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3) + ";" + str(temperature_current) + ";" + str(flag) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(sht_humidity ) 
	else:
		print(today, now + " - happy debugging\nwhen device case is closed, sen & ref should be over 4000 and both bias close to 0")
	if (debug is False):
		internet_available = check_connection()
		if (internet_available  is True) and (bcMeterConf.get_location is True):
			location = get_location()
			if not 'location' in open('bcMeterConf.py').read():
				with open('bcMeterConf.py', 'a') as f:
					f.write("location=" + str(location) + "#Location of the bcMeter. Keep syntax exactly like that [lat,lon] ")
			else:
				with open('bcMeterConf.py', 'r') as f:
					lines = f.readlines()
				for i, line in enumerate(lines):
					if line.startswith('location'):
						lines[i] = "location=" + str(location) + "#Location of the bcMeter. Keep syntax exactly like that [lat,lon] "
				with open('bcMeterConf.py', 'w') as f:
					f.writelines(lines)
			print("using lat lon", location)
		
	if (compair_upload is True):
		import compair_frost_upload

	while(True):
		if (debug == False):
			importlib.reload(bcMeterConf)
			volume_air_per_minute=(bcMeterConf.sample_time/60)*bcMeterConf.airflow_per_minute #liters of air between samples	
			with open("/home/pi/logs/" + logFileName, "a") as log:
				samples_taken+=1
				start = time()
				GPIO.output(POWERPIN, 1) 
				sleep(0.01)
				sensor_values=get_sensor_values(MCP3426_DEFAULT_ADDRESS, bcMeterConf.sample_count)
				GPIO.output(POWERPIN, 0) 
				main_sensor_value = sensor_values[0]
				reference_sensor_value = sensor_values[1]
				sensor_values=get_sensor_values(MCP3426_DEFAULT_ADDRESS, 10)
				main_sensor_bias =sensor_values[0]
				reference_sensor_bias= sensor_values[1]
				main_sensor_value_current=main_sensor_value#-main_sensor_bias
				reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
				if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
					temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
					print("measured temperature:", temperature_current)				
				else:
					if (sht40_i2c is True):
						try:
							sensor = adafruit_sht4x.SHT4x(i2c)
							temperature_samples = []
							humidity_samples = []
							for i in range(100):
							    temperature_samples.append(sensor.temperature)
							    humidity_samples.append(sensor.relative_humidity)

							temperature_current = sum(temperature_samples) / 100
							sht_humidity = sum(humidity_samples) / 100		
						except:
							pass
					
					else:
						print("no temperature sensor detected")
						temperature_current = 1
				if (reference_sensor_value_current == 0): reference_sensor_value_current = 1 #avoid later divide by 0; just for debug
				if (main_sensor_value_current == 0): main_sensor_value_current = 1#avoid later divide by 0; just for debug
				filter_status = (
					5 if main_sensor_value_current > 8000 else
					4 if 6000 < main_sensor_value_current <= 8000 else
					3 if 3000 < main_sensor_value_current <= 6000 else
					2 if 2000 < main_sensor_value_current <= 3000 else
					1 if 1000 < main_sensor_value_current <= 2000 else
					0 if 0 < main_sensor_value_current <= 1000 else
					None
				)

				if (abs(bcm_temperature_last_run-temperature_current) > .5): flag = flag + "tempChange-"
				attenuation_current=round((numpy.log(main_sensor_value_current/reference_sensor_value_current)*-100),5)
				atn_peak = False
				if (attenuation_last_run != 0) and (samples_taken>1):
					peakdetection = 1 - abs((attenuation_last_run/attenuation_current))
					if (peakdetection > 0.015) and (abs(attenuation_current- attenuation_last_run)>1.5):
						atn_peak = True
						flag = flag + "PEAK"
				if (attenuation_last_run == 0):
					attenuation_last_run = attenuation_current
				delay = time() - start
				#if (samples_taken<3):
				#	volume_air_per_minute=(delay/60)*bcMeterConf.airflow_per_minute #liters of air between samples	
				#else:
				volume_air_per_minute=(bcMeterConf.sample_time/60)*bcMeterConf.airflow_per_minute #liters of air between samples	
				if (atn_peak is False):
					attenuation_coeff = sample_spot_areasize*((attenuation_current-attenuation_last_run)/100)/volume_air_per_minute	
				else:
					attenuation_coeff = sample_spot_areasize*((attenuation_current-attenuation_last_run)/100)/volume_air_per_minute	
				#	attenuation_coeff = 0
				absorption_coeff = attenuation_coeff/bcMeterConf.filter_scattering_factor
				BCngm3 = int((absorption_coeff / sigma_air_880nm)*bcMeterConf.device_specific_correction_factor) #bc nanograms per m3
				#logString = str(datetime.now().strftime("%d-%m-%y")) + ";" + str(datetime.now().strftime("%H:%M:%S")) +";" +str(reference_sensor_value_current) +";"  +str(main_sensor_value_current) +";" +str(attenuation_current) + ";"+  str(attenuation_coeff) +";"+ str(BCngm3) + ";" + str(round(temperature_current,1)) + ";" + str(flag) + ";" + str(main_sensor_bias)  + ";" + str(reference_sensor_bias) + ";" + str(round(delay,1)) + ";" + str(round(sht_humidity,1))
				logString = f"{datetime.now().strftime('%d-%m-%y')};{datetime.now().strftime('%H:%M:%S')};{reference_sensor_value_current};{main_sensor_value_current};{attenuation_current};{attenuation_coeff};{BCngm3};{round(temperature_current, 1)};{flag};{main_sensor_bias};{reference_sensor_bias};{round(delay, 1)};{round(sht_humidity, 1)}"
				log.write(logString+"\n")
				if (compair_upload == True) and (samples_taken > 2) and (online is True):
					#print("uploading to CompAir Cloud",BCngm3,attenuation_current,main_sensor_value_current,reference_sensor_value_current,temperature_current, bcMeter_location, filter_status)
					compair_frost_upload.upload_sample(str(BCngm3),str(attenuation_current),str(main_sensor_value_current),str(reference_sensor_value_current),str(temperature_current), str(bcMeter_location), str(filter_status))
				flag=""
				main_sensor_value_last_run=main_sensor_value_current 
				attenuation_last_run=attenuation_current
				bcm_temperature_last_run = temperature_current
				atn_peak = False
				online = False
				flag=""
			
				'''if (samples_taken == 2):
				lines = open("/home/pi/logs/" + logFileName).readlines()
				lines.pop(2)
				with open("/home/pi/logs/" + logFileName, "w") as f:
					#write each line back to the file
					for line in lines:
						f.write(line)
			'''
			os.popen("cp /home/pi/logs/" + logFileName + " /home/pi/logs/log_current.csv")

			if (run_once == "true"): 
				print("cycle of " + str(sample_count) + " took " + str(round(delay,2)) + " seconds")
				GPIO.output(POWERPIN, 0)
				sys.exit(1)
			if (debug == False) and (reference_sensor_value_current !=0) and (main_sensor_value !=0) and (output_to_terminal is True): #output in terminal
				with open('logs/log_current.csv','r') as csv_file:
					os.system('clear')
					print(today, now, bcMeter_version, logFileName)
					headers=[]
					with open('logs/log_current.csv','r') as csv_file:
						csv_reader = list(csv.reader(csv_file, delimiter=';'))
						print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
						print("Exit script with ctrl+c")
			if ((bcMeterConf.sample_time)-delay <= 0):
				sleep(bcMeterConf.sample_time)
			else:
				sleep((bcMeterConf.sample_time)-delay)

			
		else: #debug mode
			print("debugging with sample_count, sample_time:", sample_count, sample_time)
			start = time()
			GPIO.output(POWERPIN, 1) 
			sleep(0.01)
			sensor_values=get_sensor_values(MCP3426_DEFAULT_ADDRESS, sample_count)
			GPIO.output(POWERPIN, 0) 
			main_sensor_value = sensor_values[0]
			reference_sensor_value = sensor_values[1]
			sensor_values=get_sensor_values(MCP3426_DEFAULT_ADDRESS, 10)
			main_sensor_bias =sensor_values[0]
			reference_sensor_bias= sensor_values[1]
			main_sensor_value_current=main_sensor_value#-main_sensor_bias
			reference_sensor_value_current=reference_sensor_value#-reference_sensor_bias
			delay = time() - start
			print(f"sen; {round(main_sensor_value, 5)}; ref; {round(reference_sensor_value, 5)}; senbias; {round(main_sensor_bias, 3)}; refbias; {round(reference_sensor_bias, 3)}; sample_time; {round(delay, 2)}; ATN; {attenuation_current}")
			if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
				temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
				print("measured temperature:", temperature_current)				
			else:
				if (sht40_i2c is True):
					sensor = adafruit_sht4x.SHT4x(i2c)
					temperature_current = sensor.temperature
					sht_humidity   = sensor.relative_humidity			
				else:
					print("no temperature sensor detected")
					temperature_current = 1
			if (run_once == "true"): 
				print("cycle of " + str(sample_count) + " took " + str(round(delay,2)) + " seconds")
				print("exiting debug mode")
				GPIO.output(POWERPIN, False)
				GPIO.output(1,False)
				GPIO.output(23,False)
				sys.exit(1)


def keep_the_temperature():			
	temperature_to_keep = 35
	while (True):
		skipheat=False
		if (len(glob.glob('/sys/bus/w1/devices/28*')) > 0):
			temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
			print("measured temperature:", temperature_current)				
		if (sht40_i2c is True):
			try:
				sensor = adafruit_sht4x.SHT4x(i2c)
				temperature_current = sensor.temperature
				sht_humidity  = sensor.relative_humidity
			except:
				skipheat=True			
		else:
			print("no temperature sensor detected")
			temperature_current = 1
	#sneak in pwm adjustment for pump because we dont want do have on thread just for that
		importlib.reload(bcMeterConf)
		pump_duty.ChangeDutyCycle(bcMeterConf.pump_dutycycle) 
		heating = getattr(bcMeterConf, 'heating', False)
		if (heating is True) and (skipheat is False):
			if ((temperature_to_keep - temperature_current) > 10):
				if (temperature_to_keep > 10):
					temperature_to_keep = temperature_current - 5
				GPIO.output(1,True)
				GPIO.output(23,True)
				#print("adjusted temperature to keep to  ", temperature_to_keep)
			
			if temperature_current < temperature_to_keep:
				GPIO.output(1,True)
				GPIO.output(23,True)
				#print(temperature, "current, heating up to", temperature_to_keep)

			if (temperature_current >(temperature_to_keep+1)):
				if (temperature_to_keep < 40):
					temperature_to_keep = temperature_current+1
				GPIO.output(1,False)
				GPIO.output(23,False)
				#print("adjusted temperature to keep to ", temperature_to_keep)

			if ((temperature_to_keep - temperature_current)<0):
				GPIO.output(1,False)
				GPIO.output(23,False)

		sleep(5)




if __name__ == '__main__':
	startUp()

	try:
		sampling_thread = Thread(target=bcmeter_main)


		sampling_thread.start()
		if (debug is False):
			heating_thread = Thread(target=keep_the_temperature)
			heating_thread.start()

	except KeyboardInterrupt: 
		print("\nWhen ready again, you may restart the script with 'python3 bcMeter.py' or just reboot the device itself")
		GPIO.output(POWERPIN, False)
		GPIO.output(1,False)
		GPIO.output(23,False)
		pump_duty.ChangeDutyCycle(0) 
		sleep(1) #sometimes the dutycycle is not transmitted early

		pass

