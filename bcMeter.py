import glob
import os
import re
import signal
import socket
import subprocess
import sys
import typing
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Thread, Event, Lock
from time import sleep, time

import numpy
import pigpio
import RPi.GPIO as GPIO
import smbus
import spidev
from scipy.ndimage import median_filter

from bcMeter_shared import (
	config_json_handler,
	check_connection,
	manage_bcmeter_status,
	show_display,
	config,
	i2c,
	setup_logging,
	run_command,
	send_email,
	update_config,
	filter_values_ona,
	apply_dynamic_airflow
)

bcMeter_version = "1.1.0 2025-11-13"
base_dir = '/home/bcmeter' if os.path.isdir('/home/bcmeter') else '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

logger = setup_logging('bcMeter')
debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "debug") else False
if debug:
	logger.debug("--- DEBUG MODE ENABLED ---")
logger.debug(config)
logger.debug(f"bcMeter Version {bcMeter_version}")
bus = smbus.SMBus(1)
i2c_lock = Lock()

NUM_CHANNELS = config.get('num_channels', 1)
LED_880NM_PIN = 26
LED_520NM_PIN = 25
LED_370NM_PIN = 24
BUSY_PIN = 17

CHANNELS_CONFIG = {
	'880nm': {'pin': LED_880NM_PIN, 'sigma': 7.77e-8, 'sens': 0, 'ref': 0, 'atn': 0, 'bc': 0, 'bc_unfiltered': 0},
	'520nm': {'pin': LED_520NM_PIN, 'sigma': 13.14e-8, 'sens': 0, 'ref': 0, 'atn': 0, 'bc': 0, 'bc_unfiltered': 0},
	'370nm': {'pin': LED_370NM_PIN, 'sigma': 18.47e-8, 'sens': 0, 'ref': 0, 'atn': 0, 'bc': 0, 'bc_unfiltered': 0},
}
WAVELENGTH_ORDER = ['880nm', '520nm', '370nm']

disable_pump_control = config.get('disable_pump_control', False)
get_location = config.get('get_location', False)
heating = config.get('heating', False)
pump_pwm_freq = int(config.get('pwm_freq', 20))
af_sensor_type = int(config.get('af_sensor_type', 1))
use_rgb_led = config.get('use_rgb_led', 0)
use_display = config.get('use_display', False)
airflow_sensor = config.get('airflow_sensor', False)
pump_dutycycle = int(config.get('pump_dutycycle', 20))
reverse_dutycycle = config.get('reverse_dutycycle', False)
sample_spot_diameter = float(str(config.get('sample_spot_diameter', 0.4)).replace(',', '.'))
is_ebcMeter = config.get('is_ebcMeter', False)
mail_logs_to = config.get('mail_logs_to', "")
send_log_by_mail = config.get('send_log_by_mail', False)
filter_status_mail = config.get('filter_status_mail', False)
disable_led = config.get('disable_led', False)
airflow_type = int(config.get('af_sensor_type', 1))
TWELVEVOLT_ENABLE = config.get('TWELVEVOLT_ENABLE', False)
twelvevolt_duty = config.get('twelvevolt_duty', 20)
automatic_airflow_control = config.get('automatic_airflow_control', False)
spi_vref=config.get('spi_vref', 4.096)

bc_data_history = {
	'unfiltered': {wl: [] for wl in WAVELENGTH_ORDER},
	'filtered': {wl: [] for wl in WAVELENGTH_ORDER},
	'all_log_data': []
}
current_measured_airflow_lpm = 0.0
desired_airflow_in_lpm = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))

def filter_bc_values():
	global bc_data_history, is_ebcMeter, WAVELENGTH_ORDER
	kernel = 3 if is_ebcMeter else 5
	for wl in WAVELENGTH_ORDER:
		unfiltered_data = bc_data_history['unfiltered'][wl]
		if not unfiltered_data:
			bc_data_history['filtered'][wl] = []
			continue

		if len(unfiltered_data) >= kernel:
			filtered_bc = median_filter(unfiltered_data, size=kernel)
			bc_data_history['filtered'][wl] = [int(val) for val in filtered_bc]
		else:
			bc_data_history['filtered'][wl] = [int(val) for val in unfiltered_data]


class ADS8344:
    START_BIT = 0x80
    SINGLE_END = 0x04
    CLOCK_INTERNAL = 0x02
    CHANNELS = {
        0: 0x00, 1: 0x04, 2: 0x01, 3: 0x05,
        4: 0x02, 5: 0x06, 6: 0x03, 7: 0x07
    }

    def __init__(self, bus=0, device=0, vref=spi_vref, busy_pin=None):
        self.spi = spidev.SpiDev()
        self.busy_pin = busy_pin
        try:
            self.spi.open(bus, device)
            self.spi.max_speed_hz = 1000000 
            self.spi.mode = 0
            self.vref = vref
            if self.busy_pin is not None:
                GPIO.setup(self.busy_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize SPI: {e}")
            self.initialized = False

    def close(self):
        if hasattr(self, 'spi') and self.spi is not None:
            self.spi.close()

    def read_channel(self, channel):
        if not self.initialized:
            return -1, None
        try:
            channel_bits = (self.CHANNELS[channel] & 0x7) << 4
            cmd = self.START_BIT | self.SINGLE_END | channel_bits | self.CLOCK_INTERNAL
            self.spi.writebytes([cmd])

            if self.busy_pin is not None:
                timeout_start = time()
                while GPIO.input(self.busy_pin) == GPIO.LOW:
                    if time() - timeout_start > 0.002:
                        break
            else:
                sleep(0.00005) 

            result = self.spi.readbytes(3)
            value = (result[0] << 9) | (result[1] << 1) | (result[2] >> 7)
            voltage = (value / 65536.0) * self.vref
            return voltage, result
        except Exception as e:
            logger.error(f"SPI read error: {e}")
            return -1, None

    def read_all_channels(self):
        if not self.initialized:
            return {}
        results = {}
        try:
            for ch in self.CHANNELS.keys():
                voltage, _ = self.read_channel(ch)
                if voltage != -1:
                    results[f"CH{ch}"] = voltage
            return results
        except Exception as e:
            logger.error(f"SPI batch read error: {e}")
            return {}


if airflow_type == 9:
	from bcMeter_shared import read_airflow_ml
cooling = False
temperature_to_keep = 35 if cooling is False else 0
run_once = "false"
airflow_debug = True if (len(sys.argv) > 1) and (sys.argv[1] == "airflow") else False
sht40_i2c = None
online = False
output_to_terminal = False
use_spi = False
spi_adc = None

show_display(f"Initializing bcMeter", False, 0)
show_display(f"bcMeter {bcMeter_version}", False, 1)

GPIO.setmode(GPIO.BCM)
devicename = socket.gethostname()
sample_spot_areasize=numpy.pi*(float(sample_spot_diameter)/2)**2
os.chdir(base_dir)
calibration = True if (len(sys.argv) > 1) and (sys.argv[1] == "cal") else False
GPIO.setmode(GPIO.BCM)
MONOLED_PIN=1
PUMP_PIN = 12
TWELVEVOLT_PIN = 27
GPIO.setup(MONOLED_PIN, GPIO.OUT)

if TWELVEVOLT_ENABLE:
	GPIO.setup(TWELVEVOLT_PIN, GPIO.OUT)

MCP342X_DEFAULT_ADDRESS = 0x68
MCP342X_GENERAL_CALL_RESET = 0x06
VOLTAGE_REFERENCE = 2.048

MCP342X_CONFIG_READY = 0x80
MCP342X_CONFIG_MODE_ONESHOT = 0x00
MCP342X_CONFIG_MODE_CONTINUOUS = 0x10
MCP342X_CONFIG_CH1 = 0x00
MCP342X_CONFIG_CH2 = 0x20
MCP342X_CONFIG_CH3 = 0x40
MCP342X_CONFIG_CH4 = 0x60
MCP342X_CONFIG_SPS_240_12BIT = 0x00
MCP342X_CONFIG_SPS_60_14BIT = 0x04
MCP342X_CONFIG_SPS_15_16BIT = 0x08
MCP342X_CONFIG_GAIN_1X = 0x00
MCP342X_CONFIG_GAIN_2X = 0x01
MCP342X_CONFIG_GAIN_4X = 0x02
MCP342X_CONFIG_GAIN_8X = 0x03

adc_rate = MCP342X_CONFIG_SPS_60_14BIT
adc_gain = MCP342X_CONFIG_GAIN_1X

airflow_only = True if (len(sys.argv) > 1) and (sys.argv[1] == "airflow") else False
airflow_channel = MCP342X_CONFIG_CH1 if airflow_only is True and sys.argv[1] == "1" else MCP342X_CONFIG_CH3
sampling_thread = housekeeping_thread = airflow_control_thread = None

stop_event = Event()
change_blinking_pattern = Event()

PUMP_PWM_RANGE = 100 if reverse_dutycycle else 255
PUMP_PWM_FREQ = int(config.get('pwm_freq', 20))
LED_PWM_RANGE = 255
LED_PWM_FREQ = 1000




def gradual_shutdown_12v(steps=20, step_delay=0.25):
	global pi, TWELVEVOLT_PIN
	try:
		if not (pi and pi.connected):
			return

		current_duty = pi.get_PWM_dutycycle(TWELVEVOLT_PIN)
		if current_duty == 0:
			return

		step_size = current_duty / steps
		for i in range(steps):
			if not pi.connected:
				logger.warning("pigpio disconnected during 12V shutdown.")
				break
			
			reduced_duty = max(0, int(current_duty - (step_size * (i + 1))))
			pi.set_PWM_dutycycle(TWELVEVOLT_PIN, reduced_duty)
			sleep(step_delay)
		
		if pi.connected:
			pi.set_PWM_dutycycle(TWELVEVOLT_PIN, 0)
		
		logger.debug("12V power ramp-down complete or was interrupted.")
	except Exception as e:
		logger.error(f"Error during 12V gradual shutdown: {e}")
		try:
			if pi and pi.connected:
				pi.set_PWM_dutycycle(TWELVEVOLT_PIN, 0)
		except:
			pass
			
def shutdown(reason, shutdown_code=None):
    global reverse_dutycycle, housekeeping_thread, airflow_control_thread, sampling_thread, TWELVEVOLT_ENABLE
    global spi_adc, use_spi
    stop_event.set()
    change_blinking_pattern.set()
    print(f"Quitting: {reason}")
    logger.debug(f"Shutdown initiated: {reason}")
    
    show_display("Goodbye", 0, True)
    if reason == "SIGINT" or reason == "SIGTERM":
        show_display("Turn off bcMeter", 1, True)
    else:
        show_display(f"{reason}", 1, True)
    show_display("", 2, True)

    if use_spi and spi_adc is not None:
        try:
            spi_adc.close()
            logger.debug("SPI ADC connection closed")
        except Exception as e:
            logger.error(f"Error closing SPI ADC: {e}")

    if reason != "Already running":
        try:
            if 'pi' in globals() and pi.connected:
                if TWELVEVOLT_ENABLE:
                     gradual_shutdown_12v()
                     sleep(1)
                if reverse_dutycycle is False:
                    try:
                        pi.set_PWM_dutycycle(PUMP_PIN, 0)
                    except:
                        pass
                else:
                    try:
                        pi.set_PWM_dutycycle(PUMP_PIN, PUMP_PWM_RANGE)
                    except:
                        pass
                pi.stop()
                logger.debug("pigpio connection stopped")
                try:
                    subprocess.run(["sudo", "killall", "pigpiod"], check=False, timeout=2)
                    logger.debug("pigpiod process terminated")
                except subprocess.TimeoutExpired:
                    logger.warning("Timeout while trying to kill pigpiod")
        except Exception as e:
            logger.error(f"Error stopping pigpio: {e}")

    from threading import current_thread
    current_thread_id = current_thread().ident
    threads_to_join = []
    if sampling_thread and sampling_thread.is_alive() and sampling_thread.ident != current_thread_id:
        threads_to_join.append(sampling_thread)
    if housekeeping_thread and housekeeping_thread.is_alive() and housekeeping_thread.ident != current_thread_id:
        threads_to_join.append(housekeeping_thread)
    if airflow_control_thread and airflow_control_thread.is_alive() and airflow_control_thread.ident != current_thread_id:
        threads_to_join.append(airflow_control_thread)
    for thread in threads_to_join:
        thread.join(timeout=1)
        if thread.is_alive():
            logger.warning(f"Thread {thread.name} didn't terminate within timeout")

    if shutdown_code is None:
        shutdown_code = 5
    manage_bcmeter_status(action='set', bcMeter_status=shutdown_code)

    try:
        GPIO.cleanup()
        logger.debug("GPIO cleanup completed")
    except Exception as e:
        logger.error(f"Error during GPIO cleanup: {e}")
    sys.exit(0)

cmd = ['ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3']
process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
my_pid, err = process.communicate()
if len(my_pid.splitlines()) > 1:
	sys.stdout.write("bcMeter Script already running.\n" + str(my_pid.splitlines())+"\n")
	shutdown("Already running")
if manage_bcmeter_status(parameter='bcMeter_status') !=5:
	manage_bcmeter_status(action='set', bcMeter_status=0)
online = check_connection()
if (online):
	logger.debug("bcMeter is online!")
else:
	logger.debug("bcMeter is offline!")
try:
	import adafruit_sht4x
except ImportError:
	logger.debug("need to be online to install sht library first!")
	shutdown("Update needed for sht4x")

def find_mcp_address():
	global MCP342X_DEFAULT_ADDRESS
	try:
		for device in range(128):
			if device in [0x68, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f]:
				try:
					bus.read_byte(device)
					MCP342X_DEFAULT_ADDRESS = device
					logger.debug("ADC found at Address: %s", hex(MCP342X_DEFAULT_ADDRESS))
					if debug: print(f"[DEBUG] I2C ADC found at address {hex(MCP342X_DEFAULT_ADDRESS)}")
					return True
				except:
					continue
		logger.error("No ADC found on I2C bus")
		if debug: print("[DEBUG] No I2C ADC found on bus scan.")
		return False
	except Exception as e:
		logger.error(f"I2C bus error while scanning for ADC: {e}")
		shutdown(f"I2C bus error: {e}", 6)

exception_timestamps = deque(maxlen=10)
shutdown_threshold = 2

def initialize_pwm_control():
	global pi
	if airflow_only:
		return True
	try:
		pigpiod_running = subprocess.run(["pgrep", "-x", "pigpiod"],
									 stdout=subprocess.PIPE).returncode == 0
		if pigpiod_running:
			try:
				subprocess.run(["sudo", "killall", "pigpiod"], check=False)
				sleep(2)
			except:
				pass
		os.system("sudo pigpiod -l -m")
		sleep(3)
		retry_count = 0
		while retry_count < 5:
			try:
				pi = pigpio.pi()
				if pi.connected:
					break
				retry_count += 1
				sleep(2)
			except:
				retry_count += 1
				sleep(2)
		if not pi.connected:
			raise Exception("Failed to connect to pigpiod after multiple attempts")
		pi.set_mode(PUMP_PIN, pigpio.OUTPUT)
		for wavelength in WAVELENGTH_ORDER:
			pin = CHANNELS_CONFIG[wavelength]['pin']
			pi.set_mode(pin, pigpio.OUTPUT)
			pi.set_PWM_range(pin, LED_PWM_RANGE)
			pi.set_PWM_frequency(pin, LED_PWM_FREQ)
			pi.set_PWM_dutycycle(pin, 0)

		pi.set_PWM_range(PUMP_PIN, PUMP_PWM_RANGE)
		pi.set_PWM_frequency(PUMP_PIN, PUMP_PWM_FREQ)

		sleep(0.5)
		return True
	except Exception as e:
		logger.error(f"Error initializing PWM control: {e}")
		return False
if not airflow_only:
	try:
		if not initialize_pwm_control():
			logger.error("Failed to initialize PWM control")
			shutdown("Pigpiod Error. Reboot and retry.", 6)
		if debug:
			print("pigpiod initialized")
	except Exception as e:
		logger.error("Error: %s", e)
		shutdown("PWM initialization failed", 6)
try:
	from scipy.ndimage import median_filter
except ImportError:
	logger.error("Update bcMeter!")
	shutdown("Update needed for scipy",6)
try:
	sht = adafruit_sht4x.SHT4x(i2c)
	sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
	temperature, relative_humidity = sht.measurements
	logger.debug("Temperature: %0.1f C" % temperature)
	logger.debug("Humidity: %0.1f %%" % relative_humidity)
	sht40_i2c = True
	ds18b20 = False
except Exception as e:
	sht40_i2c = False
	logger.error("Error: %s", e)


if sht40_i2c is False:
	class TemperatureSensor:
		RETRY_INTERVAL = 0.5
		RETRY_COUNT = 10
		device_file_name = None
		def __init__(self, channel: int):
			GPIO.setmode(GPIO.BCM)
			GPIO.setup(channel, GPIO.IN)
		@staticmethod
		def read_device() -> typing.List[str]:
			device_file_name = None
			try:
				device_file_name = glob.glob('/sys/bus/w1/devices/28*')[0] + '/w1_slave'
			except Exception as e:
				logger.error(f"Temperature Sensor DS18b20 Error {e}")
			if device_file_name is not None:
				with open(device_file_name, 'r') as fp:
					return [line.strip() for line in fp.readlines()]
		def get_temperature_in_milli_celsius(self) -> int:
			for i in range(self.RETRY_COUNT):
				lines = self.read_device()
				try:
					if len(lines) >= 2 and lines[0].endswith('YES'):
						match = re.search(r't=(\d{1,6})', lines[1])
						if match:
							return int(match.group(1), 10)
					sleep(self.RETRY_INTERVAL)
				except:
					pass
			logger.error(f"Cannot read temperature (tried {self.RETRY_COUNT} times with an interval of {self.RETRY_INTERVAL})")
	try:
		temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000,2)
		if temperature_current is not None:
			ds18b20 = True
			if debug:
				print("using ds18b20")
			logger.debug("Using ds18b20 as temperature sensor")
			logger.debug("Temperature: %0.1f C" % temperature_current)
	except:
		print("no temperature sensor detected!")
		ds18b20 = False

def handle_signal(signum, frame):
	if signum == signal.SIGUSR1:
		signal_handler()
	elif signum == signal.SIGINT:
		shutdown("SIGINT")
	elif signum == signal.SIGTERM:
		shutdown("SIGTERM")


signal.signal(signal.SIGUSR1, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def signal_handler():
	file_path = '/tmp/bcMeter_signalhandler'
	if os.path.isfile(file_path):
		with open(file_path, 'r+') as file:
			content = file.read().strip()
			logger.debug("signal handler: %s", content)
			if content == 'pump_test':
				pump_test()
			if content == 'identify':
				led_communication()
			file.seek(0)
			file.truncate()

def check_spi_adc_available():
	global spi_adc
	try:
		spi_adc = ADS8344(bus=0, device=0, vref=4.096, busy_pin=None)
		value, result = spi_adc.read_channel(0)
		if result is not None:
			for _ in range(3):
				test_value, test_result = spi_adc.read_channel(0)
				if test_result is None:
					logger.debug("SPI ADC gave inconsistent results")
					spi_adc.close()
					return False, None
			logger.info(f"SPI ADC detected with reading: {value}, raw bytes: {result}")
			return True, spi_adc
		else:
			logger.debug("SPI ADC not detected (no result)")
			if spi_adc:
				spi_adc.close()
			return False, None
	except Exception as e:
		logger.error(f"SPI ADC check failed: {e}")
		if 'spi_adc' in globals() and spi_adc is not None:
			try:
				spi_adc.close()
			except:
				pass
		return False, None



def calibrate_sens_ref():
	global use_spi, spi_adc, NUM_CHANNELS, WAVELENGTH_ORDER, config

	logger.info("=== Starting LED calibration ===")
	print("=== Starting LED calibration ===")

	led_brightness_legacy = int(config.get('led_brightness', False))
	led_duty_cycle_880 = int(config.get('led_duty_cycle_880nm', led_brightness_legacy)) if not led_brightness_legacy else led_brightness_legacy

	def measure_short():
		return read_alternating_spi(1) if use_spi else read_adc(sample_time=1)

	def measure_long():
		return read_alternating_spi(10) if use_spi else read_adc(sample_time=10)

	def auto_adjust(wl, pin, limit, dc):
		logger.debug(f"{wl}: Starting duty search at {dc}")
		last_safe_dc = None
		while True:
			set_pwm_duty_cycle(pin, dc)
			sleep(0.1)
			sens, ref = measure_short()
			set_pwm_duty_cycle(pin, 0)
			logger.debug(f"{wl}: sens={sens:.3f}, ref={ref:.3f} at duty={dc}")
			print(f"{wl}: sens={sens:.3f}, ref={ref:.3f}, duty={dc}")
			too_bright = sens >= limit or ref >= limit
			if too_bright:
				new_dc = max(0, dc - 10)
				logger.debug(f"{wl}: too bright → decreasing {dc}→{new_dc}")
				dc = new_dc
				update_config(variable=f"led_duty_cycle_{wl}", value=dc, description=f"LED duty cycle {wl}", type="number", parameter="administration")
				continue
			last_safe_dc = dc
			if dc < 255:
				next_dc = min(255, dc + 10)
				set_pwm_duty_cycle(pin, next_dc)
				sleep(0.1)
				n_sens, n_ref = measure_short()
				set_pwm_duty_cycle(pin, 0)
				logger.debug(f"{wl}: test next duty {next_dc}: sens={n_sens:.3f}, ref={n_ref:.3f}")
				print(f"{wl}: test next duty {next_dc}: sens={n_sens:.3f}, ref={n_ref:.3f}")
				if n_sens >= limit or n_ref >= limit:
					logger.debug(f"{wl}: next step hits limit → final duty={last_safe_dc}")
					return last_safe_dc
				logger.debug(f"{wl}: too dim → increasing {dc}→{next_dc}")
				dc = next_dc
				update_config(variable=f"led_duty_cycle_{wl}", value=dc, description=f"LED duty cycle {wl}", type="number", parameter="administration")
			else:
				
				logger.debug(f"{wl}: reached duty=255, checking minimum brightness…")
				set_pwm_duty_cycle(pin, int(config.get(f"led_duty_cycle_{wl}", led_brightness_legacy)))
				sleep(0.1)
				sens, ref = measure_short()
				set_pwm_duty_cycle(pin, 0)
				min_volt=0.1 if use_spi else 0.4
				if sens < min_volt or ref < min_volt:
					logger.debug(f"{wl}: LED too dim at max duty (sens={sens:.3f}, ref={ref:.3f}) → shutting down")
					shutdown("LED too dim", 6)
				logger.debug(f"{wl}: Using duty=255")

				return 255

	correction_output = []

	if use_spi:
		limit = 3.8
		active_wls = WAVELENGTH_ORDER[:NUM_CHANNELS]
		for wl in active_wls:
			pin = CHANNELS_CONFIG[wl]['pin']
			start_dc = int(config.get(f"led_duty_cycle_{wl}", led_duty_cycle_880))
			auto_adjust(wl, pin, limit, start_dc)
		for wl in active_wls:
			pin = CHANNELS_CONFIG[wl]['pin']
			dc = int(config.get(f"led_duty_cycle_{wl}", led_duty_cycle_880))
			logger.debug(f"{wl}: Taking long measurement at duty={dc}")
			set_pwm_duty_cycle(pin, dc)
			sleep(0.1)
			sens, ref = measure_long()
			set_pwm_duty_cycle(pin, 0)
			logger.debug(f"{wl}: long sens={sens:.3f}, ref={ref:.3f}")
			print(f"{wl}: long sens={sens:.3f}, ref={ref:.3f}")
			sens_c = 1 if sens >= ref else ref / sens
			ref_c = 1 if ref >= sens else sens / ref
			update_config(variable=f"sens_correction_{wl}", value=sens_c, description=f"Sensor Correction {wl}", type="float", parameter="hidden")
			update_config(variable=f"ref_correction_{wl}", value=ref_c, description=f"Reference Correction {wl}", type="float", parameter="hidden")
			correction_output.append(f"{wl}: sens_c={sens_c:.4f}, ref_c={ref_c:.4f}")

	else:
		wl = "880nm"
		limit = 1.85
		start_dc = led_duty_cycle_880
		auto_adjust(wl, LED_880NM_PIN, limit, start_dc)
		dc = int(config.get("led_duty_cycle_880nm", start_dc))
		logger.debug(f"{wl}: Taking long measurement at duty={dc}")
		set_pwm_duty_cycle(LED_880NM_PIN, dc)
		sleep(0.1)
		sens, ref = measure_long()
		set_pwm_duty_cycle(LED_880NM_PIN, 0)
		logger.debug(f"{wl}: long sens={sens:.3f}, ref={ref:.3f}")
		print(f"{wl}: long sens={sens:.3f}, ref={ref:.3f}")
		sens_c = 1 if sens >= ref else ref / sens
		ref_c = 1 if ref >= sens else sens / ref
		update_config(variable="sens_correction", value=sens_c, description="Sensor Correction", type="float", parameter="administration")
		update_config(variable="ref_correction", value=ref_c, description="Reference Correction", type="float", parameter="administration")
		correction_output.append(f"{wl}: sens_c={sens_c:.4f}, ref_c={ref_c:.4f}")

	calibration_time = datetime.now().strftime("%y%m%d_%H%M%S")
	logger.debug(f"Calibration completed at {calibration_time}")
	manage_bcmeter_status(action='set', calibration_time=calibration_time)
	manage_bcmeter_status(action='set', filter_status=5)

	print("=== Correction Factors ===")
	logger.info("=== Correction Factors ===")
	for line in correction_output:
		print(line)
		logger.info(line)


def find_adc():
	global MCP342X_DEFAULT_ADDRESS, use_spi, spi_adc
	if debug: print("[DEBUG] Finding ADC...")
	try:
		if not find_mcp_address():
			if debug: print("[DEBUG] I2C ADC not found, checking for SPI ADC...")
			spi_available, spi_device = check_spi_adc_available()
			if spi_available:
				if debug: print("[DEBUG] SPI ADC detected.")
				use_spi = True
				spi_adc = spi_device
				return
			use_spi = False
			spi_adc = None
			logger.error("No ADC found (neither SPI nor I2C)")
			shutdown("No ADC detected", 6)
	except Exception as e:
		logger.error(f"Error during ADC detection: {e}")
		shutdown(f"No ADC found: {e}", 6)

def read_i2c_adc_channel(channel):
	global bus, adc_rate, adc_gain, MCP342X_DEFAULT_ADDRESS, VOLTAGE_REFERENCE

	with i2c_lock:
		if adc_rate == MCP342X_CONFIG_SPS_240_12BIT:
			conversion_time = 1.0 / 240
			N = 12
		elif adc_rate == MCP342X_CONFIG_SPS_60_14BIT:
			conversion_time = 1.0 / 60
			N = 14
		else:
			conversion_time = 1.0 / 15
			N = 16

		config_byte = (MCP342X_CONFIG_READY |
					   channel |
					   MCP342X_CONFIG_MODE_ONESHOT |
					   adc_rate |
					   adc_gain)

		try:
			bus.write_byte(MCP342X_DEFAULT_ADDRESS, config_byte)
		except OSError as e:
			logger.error(f"I2C write error on channel {channel}: {e}")
			return None

		sleep(conversion_time * 1.4)

		try:
			data = bus.read_i2c_block_data(MCP342X_DEFAULT_ADDRESS, 0x00, 2)
			raw_value = (data[0] << 8) | data[1]

			if raw_value >= 32768:
				raw_value -= 65536

			voltage = (2 * VOLTAGE_REFERENCE * raw_value) / (2 ** N)

			return round(voltage, 5)

		except OSError as e:
			logger.error(f"I2C read error on channel {channel}: {e}")
			return None

class SamplingSession:
	def __init__(self):
		self.j = 0

def calculate_airflow(samples_to_take=25):
	global airflow_type, airflow_channel, use_spi, spi_adc, adc_rate
	samples_to_take = 500 if use_spi else 5
	if airflow_type == 9:
		return read_airflow_ml(), read_airflow_ml()

	if airflow_type < 9:
		airflow_sum = 0
		airflow_count = 0

		if use_spi and spi_adc is not None:
			for _ in range(samples_to_take):
				if stop_event.is_set(): break
				v, _ = spi_adc.read_channel(2) 
				if v != -1:
					airflow_sum += v
					airflow_count += 1
		else:
			original_rate = adc_rate
			adc_rate = MCP342X_CONFIG_SPS_240_12BIT
			for _ in range(samples_to_take):
				if stop_event.is_set(): break
				v = read_i2c_adc_channel(MCP342X_CONFIG_CH3)
				if v is not None:
					if v == 2.047: v = 5.0
					airflow_sum += v
					airflow_count += 1
			adc_rate = original_rate

		if airflow_count > 0:
			avg_voltage = airflow_sum / airflow_count
			if avg_voltage >= 2.047 and not use_spi:
				logger.debug("airflow over sensor limit")

			current_airflow = round(airflow_by_voltage(avg_voltage, af_sensor_type), 4)

			return current_airflow, avg_voltage

	return -1, -1

def calibrate_airflow_sensor_bias():
	global airflow_sensor_bias, airflow_channel, use_spi, spi_adc, adc_rate
	if debug: print("[DEBUG] Calibrating airflow sensor bias...")

	samples_to_take = 100
	airflow_sum = 0
	airflow_count = 0

	try:
		if use_spi and spi_adc is not None:
			for _ in range(samples_to_take):
				v, _ = spi_adc.read_channel(2)

				if v != -1:
					airflow_sum += v
					airflow_count += 1
					if debug: print(v, "raw spi airflow sensor voltage")

		else:
			original_rate = adc_rate
			adc_rate = MCP342X_CONFIG_SPS_240_12BIT
			if debug: print(f"[DEBUG] calibrate_airflow_sensor_bias: Temporarily setting ADC rate to 12-bit.")
			for i in range(samples_to_take):
				v = read_i2c_adc_channel(MCP342X_CONFIG_CH3)
				if v is not None:
					airflow_sum += v
					airflow_count += 1
				if debug: print(f"[DEBUG] calibrate_airflow_sensor_bias: Sample {i+1}/{samples_to_take}, Voltage: {v}")

			adc_rate = original_rate
			if debug: print(f"[DEBUG] calibrate_airflow_sensor_bias: Restored ADC rate.")


		if airflow_count > 0:
			average_voltage = airflow_sum / airflow_count
			if debug: print(f"[DEBUG] calibrate_airflow_sensor_bias: Average voltage over {airflow_count} samples is {average_voltage:.4f}V.")
			airflow_sensor_bias = 0.5 - average_voltage

			if abs(airflow_sensor_bias) > 0.05:
				logger.error(f"Airflow Sensor Bias is too high ({airflow_sensor_bias}). Check Sensor")
				if not debug:
					shutdown(f"Airflow Sensor Bias is too high ({airflow_sensor_bias}). Check Sensor.", 6)
			else:
				logger.debug(f"airflow_sensor_bias is set to {airflow_sensor_bias}")
				return average_voltage
		else:
			if debug: print("[DEBUG] calibrate_airflow_sensor_bias: Failed to get any valid readings.")
			return None
	except Exception as e:
		print(f"Error calculating airflow sensor bias: {e}")
		airflow_sensor_bias = 0
		return None

def calculate_aae(absorption_data):
	wavelengths_nm = []
	b_abs_values = []

	for wl_str, b_abs in absorption_data.items():
		if b_abs is not None and b_abs > 0:
			try:
				wl_nm = int(re.search(r'\d+', wl_str).group())
				wavelengths_nm.append(wl_nm)
				b_abs_values.append(b_abs)
			except (AttributeError, ValueError):
				continue

	if len(wavelengths_nm) < 2:
		return -1

	log_wavelengths = numpy.log(wavelengths_nm)
	log_b_abs = numpy.log(b_abs_values)

	try:
		slope, _ = numpy.polyfit(log_wavelengths, log_b_abs, 1)
		aae = -slope
		return aae
	except Exception as e:
		logger.error(f"AAE calculation failed: {e}")
		return -1

def set_pwm_duty_cycle(component, duty_cycle, stop_event=None):
	global config, pi
	reverse_dutycycle = config.get('reverse_dutycycle', False)
	if stop_event and stop_event.is_set():
		return
	try:
		duty_cycle = int(duty_cycle)
		if isinstance(component, int):
			pin = component
			if 0 <= duty_cycle <= LED_PWM_RANGE:
				try:
					if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
						pi.set_PWM_dutycycle(pin, duty_cycle)
					else:
						if initialize_pwm_control():
							pi.set_PWM_dutycycle(pin, duty_cycle)
				except Exception as e:
					logger.warning(f"PWM error for pin {pin}: {e}")

		elif component == 'pump':
			if 0 <= duty_cycle <= PUMP_PWM_RANGE:
				adjusted_duty = PUMP_PWM_RANGE - duty_cycle if reverse_dutycycle else duty_cycle
				try:
					if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
						pi.set_PWM_dutycycle(PUMP_PIN, adjusted_duty)
					else:
						if initialize_pwm_control():
							pi.set_PWM_dutycycle(PUMP_PIN, adjusted_duty)

				except Exception as e:
					logger.warning(f"PWM error for {component}: {e}")
	except Exception as e:
		logger.error(f"PWM control failed for {component}: {e}")
		if component == 'pump':
			try:
				if 'pi' in globals() and pi and hasattr(pi, 'connected') and pi.connected:
					safe_duty = PUMP_PWM_RANGE if reverse_dutycycle else 0
					pi.set_PWM_dutycycle(PUMP_PIN, safe_duty)
			except:
				pass



def airflow_control_thread_func(stop_event):
	"""
	Manages airflow using feedback, allowing for live config changes
	while ensuring downward adjustment for unreachable targets persists.
	"""
	global current_measured_airflow_lpm, pump_dutycycle, desired_airflow_in_lpm, config, disable_pump_control, reverse_dutycycle

	if debug:
		print("[DEBUG] Airflow control thread started.")

	# Initialize both the base and the active target from the config
	base_target_from_config = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))
	desired_airflow_in_lpm = base_target_from_config
	if debug:
		print(f"[DEBUG] Airflow Control: Initial target set to {desired_airflow_in_lpm:.3f} LPM.")

	zero_airflow_counter = 0
	unreachable_airflow = False

	while not stop_event.is_set():
		config = config_json_handler()
		disable_pump_control = config.get('disable_pump_control', False)
		airflow_sensor_present = config.get('airflow_sensor', False)
		new_base_target = float(str(config.get('airflow_per_minute', 0.1)).replace(',', '.'))
		if new_base_target != base_target_from_config:
			if debug:
				print(f"[DEBUG] Airflow Control: Config changed. New target is {new_base_target:.3f} LPM.")
			desired_airflow_in_lpm = new_base_target
			base_target_from_config = new_base_target

		if disable_pump_control or not airflow_sensor_present or airflow_only:
			sleep(0.5)
			continue

		measured_lpm, voltage = calculate_airflow()
		if measured_lpm == -1:
			sleep(1)
			continue

		current_measured_airflow_lpm = measured_lpm
		show_display(f"{round(current_measured_airflow_lpm*1000)} ml/min", 2, False)

		if measured_lpm < 0.003 and desired_airflow_in_lpm > 0:
			zero_airflow_counter += 1
			if zero_airflow_counter >= 50:
				logger.warning("No airflow detected, resetting pump.")
				pump_test()
				zero_airflow_counter = 0
		else:
			zero_airflow_counter = 0

		if not unreachable_airflow:
			if measured_lpm < desired_airflow_in_lpm:
				pump_dutycycle += 1
			elif measured_lpm > desired_airflow_in_lpm:
				pump_dutycycle -= 1

		pump_dutycycle = max(0, min(pump_dutycycle, PUMP_PWM_RANGE))

		if pump_dutycycle >= PUMP_PWM_RANGE and measured_lpm < desired_airflow_in_lpm:
			unreachable_airflow = True
			desired_airflow_in_lpm -= 0.01
			logger.warning(f"Cannot reach target. Adjusting target down to {desired_airflow_in_lpm:.3f} LPM.")
			if desired_airflow_in_lpm <= 0.03:
				logger.error("Minimum airflow not reached. Stopping.")
				if not debug:
					shutdown("NOMAXAIRFLOW", 6)
		else:
			unreachable_airflow = False

		set_pwm_duty_cycle('pump', pump_dutycycle, stop_event)
		sleep(0.1)

	if debug:
		print("[DEBUG] Airflow control thread stopped.")

def pump_test():
	logger.debug("Init Pump Test")
	if (reverse_dutycycle is True):
		for cyclepart in range(1,11):
			set_pwm_duty_cycle('pump', PUMP_PWM_RANGE/cyclepart)
			sleep(0.1)
		set_pwm_duty_cycle('pump', PUMP_PWM_RANGE)
	else:
		for cyclepart in range(1,11):
			try:
				set_pwm_duty_cycle('pump', cyclepart*10*(PUMP_PWM_RANGE/100))
				sleep(0.1)
			except Exception as e:
				logger.error(e)
		set_pwm_duty_cycle('pump', 0)

def button_pressed():
	input_state = GPIO.input(16)
	if input_state == False:
		print(yo)
		pass

def createLog(log,header):
	Path(base_dir +"/logs").mkdir(parents=True, exist_ok=True)
	if os.path.isfile(base_dir+"/logs/log_current.csv"):
		os.remove(base_dir+"/logs/log_current.csv")
	with open(base_dir+"/logs/" + log, "a") as logfileArchive:
		logfileArchive.write(header + "\n\n")
		os.chmod(base_dir+"/logs/" + log, 0o777)
	with open(base_dir+"/logs/log_current.csv", "a") as temporary_log:
		temporary_log.write(header + "\n\n")

def read_adc(sample_time=None):
	global airflow_only, airflow_sensor, calibration, use_spi, spi_adc, debug

	if debug: print(f"[DEBUG] Entering read_adc for sample_time: {sample_time}s")

	session = SamplingSession()
	sums = [0.0, 0.0]
	counts = [0, 0]
	start_time = time()

	while (time() - start_time) < sample_time:
		if stop_event.is_set():
			if debug: print("[DEBUG] read_adc: Stop event detected, breaking loop.")
			break

		if use_spi and spi_adc is not None and not airflow_only:
			channels_data = spi_adc.read_all_channels()
			if channels_data and 'CH0' in channels_data and 'CH1' in channels_data:
				sums[0] += channels_data['CH0']
				counts[0] += 1
				sums[1] += channels_data['CH1']
				counts[1] += 1
		else:
			if not airflow_only:
				voltage_ch1 = read_i2c_adc_channel(MCP342X_CONFIG_CH1)
				if voltage_ch1 is not None:
					sums[0] += voltage_ch1
					counts[0] += 1
				else:
					if debug: print("[DEBUG] read_adc: CH1 Result: None")

				voltage_ch2 = read_i2c_adc_channel(MCP342X_CONFIG_CH2)
				if voltage_ch2 is not None:
					sums[1] += voltage_ch2
					counts[1] += 1
				else:
					if debug: print("[DEBUG] read_adc: CH2 Result: None")

	avg_ch1 = sums[0] / counts[0] if counts[0] > 0 else 0
	avg_ch2 = sums[1] / counts[1] if counts[1] > 0 else 0

	if debug: print(f"[DEBUG] read_adc: Finished. Averages: CH1={avg_ch1:.4f}, CH2={avg_ch2:.4f}")

	return avg_ch1, avg_ch2

def write_log_with_updated_bc(logFileName, base_dir, active_wavelengths):
	global bc_data_history, is_ebcMeter, CHANNELS_CONFIG

	unit = "ug" if is_ebcMeter else "ng"

	header_parts = ["bcmDate", "bcmTime"]
	for wl in active_wavelengths:
		header_parts.extend([
			f"bcmRef_{wl}", f"bcmSen_{wl}", f"bcmATN_{wl}",
			f"BC{unit}m3_unfiltered_{wl}", f"BC{unit}m3_{wl}"
		])
	header_parts.extend([
		"relativeLoad", "AAE", "Temperature", "notice", "sampleDuration",
		"sht_humidity", "airflow"
	])
	header = ";".join(header_parts)

	with open(f"{base_dir}/logs/{logFileName}", "w") as log:
		log.write(header + "\n\n")
		for i, log_entry_dict in enumerate(bc_data_history['all_log_data']):
			# Update the filtered 'bc' value for all wavelengths for this historical entry
			for wl in active_wavelengths:
				if i < len(bc_data_history['filtered'].get(wl, [])):
					log_entry_dict['wavelengths'].setdefault(wl, {})['bc'] = bc_data_history['filtered'][wl][i]

			log_list = [log_entry_dict['common']['date'], log_entry_dict['common']['time']]
			for wl in active_wavelengths:
				w_data = log_entry_dict['wavelengths'].get(wl, {})
				log_list.extend([
					w_data.get('ref', 0), w_data.get('sen', 0), w_data.get('atn', 0),
					w_data.get('bc_unfiltered', 0), w_data.get('bc', 0)
				])
			log_list.extend([
				log_entry_dict['common'].get('relativeLoad', 0),
				log_entry_dict['common'].get('aae', -1),
				log_entry_dict['common'].get('temp', 0),
				log_entry_dict['common'].get('notice', ''),
				log_entry_dict['common'].get('duration', 0),
				log_entry_dict['common'].get('humidity', 0),
				log_entry_dict['common'].get('airflow', 0)
			])
			log_string = ";".join(map(str, log_list))
			log.write(log_string + "\n")

	with open(f"{base_dir}/logs/log_current.csv", "w") as temp_log:
		temp_log.write(header + "\n\n")
		for i, log_entry_dict in enumerate(bc_data_history['all_log_data']):
			# Update the filtered 'bc' value for all wavelengths for this historical entry
			for wl in active_wavelengths:
				if i < len(bc_data_history['filtered'].get(wl, [])):
					log_entry_dict['wavelengths'].setdefault(wl, {})['bc'] = bc_data_history['filtered'][wl][i]

			log_list = [log_entry_dict['common']['date'], log_entry_dict['common']['time']]
			for wl in active_wavelengths:
				w_data = log_entry_dict['wavelengths'].get(wl, {})
				log_list.extend([
					w_data.get('ref', 0), w_data.get('sen', 0), w_data.get('atn', 0),
					w_data.get('bc_unfiltered', 0), w_data.get('bc', 0)
				])
			log_list.extend([
				log_entry_dict['common'].get('relativeLoad', 0),
				log_entry_dict['common'].get('aae', -1),
				log_entry_dict['common'].get('temp', 0),
				log_entry_dict['common'].get('notice', ''),
				log_entry_dict['common'].get('duration', 0),
				log_entry_dict['common'].get('humidity', 0),
				log_entry_dict['common'].get('airflow', 0)
			])
			log_string = ";".join(map(str, log_list))
			temp_log.write(log_string + "\n")



def read_alternating_spi(duration, chunk_duration=0.5):
    global spi_adc
    
    samples_needed = int(duration * 20) 
    if samples_needed < 10: samples_needed = 10
    
    def get_batch(channel, count):
        vals = []
        spi_adc.read_channel(channel)
        sleep(0.002)
        
        for _ in range(count):
            if stop_event.is_set(): break
            v, _ = spi_adc.read_channel(channel)
            if v != -1:
                vals.append(v)
            sleep(0.001) 
            
        if not vals: return 0
        vals.sort()
        trim = int(len(vals) * 0.2)
        if trim > 0:
            vals = vals[trim:-trim]
        return sum(vals) / len(vals)

    end_time = time() + duration
    
    sens_batch = []
    ref_batch = []
    
    while time() < end_time:
        if stop_event.is_set(): break
        sens_batch.append(get_batch(0, 10))
        ref_batch.append(get_batch(1, 10))
        
    avg_sens = sum(sens_batch) / len(sens_batch) if sens_batch else 0
    avg_ref = sum(ref_batch) / len(ref_batch) if ref_batch else 0
    
    return avg_sens, avg_ref


def bcmeter_main(stop_event):
	global housekeeping_thread, airflow_sensor, temperature_to_keep, airflow_sensor_bias, desired_airflow_in_lpm
	global session_running_since, ds18b20, config, temperature_current, sht_humidity
	global TWELVEVOLT_ENABLE, notice
	global use_spi, spi_adc, bc_data_history, is_ebcMeter, NUM_CHANNELS, CHANNELS_CONFIG, WAVELENGTH_ORDER, debug
	global current_measured_airflow_lpm

	if airflow_only:
		return

	samples_taken = 0
	last_run_values = {wl: {'ref': 0, 'sen': 0, 'atn': 0} for wl in WAVELENGTH_ORDER}
	notice = devicename
	today = datetime.now().strftime("%y-%m-%d")

	now = datetime.now().strftime("%H:%M:%S")
	logFileName = f"{today}_{now.replace(':','')}.csv"
	last_filter_mail_time = 0
	active_wavelengths = WAVELENGTH_ORDER[:1] if is_ebcMeter or NUM_CHANNELS == 1 else WAVELENGTH_ORDER[:NUM_CHANNELS]
	if not use_spi:
		active_wavelengths = WAVELENGTH_ORDER[:1]
	
	unit = "ug" if is_ebcMeter else "ng"

	header_parts = ["bcmDate", "bcmTime"]
	for wl in active_wavelengths:
		header_parts.extend([f"bcmRef_{wl}", f"bcmSen_{wl}", f"bcmATN_{wl}", f"BC{unit}m3_unfiltered_{wl}", f"BC{unit}m3_{wl}"])
	header_parts.extend(["relativeLoad", "AAE", "Temperature", "notice", "sampleDuration", "sht_humidity", "airflow"])
	header = ";".join(header_parts)
	
	new_log_message = f"Started log {today} {now} {bcMeter_version} {logFileName}"
	print(new_log_message)
	logger.debug(new_log_message)
	createLog(logFileName, header)
	manage_bcmeter_status(action='set', bcMeter_status=1)
	
	write_log = False

	while True:
		if stop_event.is_set():
			logger.debug("Main sampling thread received stop signal")
			return
		
		device_specific_correction_factor = float(str(config.get('device_specific_correction_factor', 1)).replace(',', '.'))
		filter_scattering_factor = float(str(config.get('filter_scattering_factor', 1.39)).replace(',', '.'))
		sample_time = int(config.get('sample_time', 300))
		sens_correction_default = float(str(config.get('sens_correction', 1)).replace(',', '.'))
		ref_correction_default = float(str(config.get('ref_correction', 1)).replace(',', '.'))
		
		led_brightness_legacy = int(config.get('led_brightness', False))
		led_duty_cycle_880nm = int(config.get('led_duty_cycle_880nm', led_brightness_legacy)) if not led_brightness_legacy else led_brightness_legacy
		print(f"LED 880 duty: {led_duty_cycle_880nm}")
		led_duty_cycle_settings = {
			'880nm': led_duty_cycle_880nm,
			'520nm': int(config.get('led_duty_cycle_520nm', led_duty_cycle_880nm)),
			'370nm': int(config.get('led_duty_cycle_370nm', led_duty_cycle_880nm)),
		}


		start = time()
		samples_taken += 1
		
		log_entry = {'common': {}, 'wavelengths': {}}
		raw_sensor_data_chunks = {wl: {'main': [], 'ref': []} for wl in active_wavelengths}

		# Loop for the total sample_time, taking 10-second chunks from each channel
		while (time() - start) < sample_time:
			# Iterate in 370, 520, 880 order
			for wavelength in reversed(active_wavelengths):
				if stop_event.is_set() or (time() - start) >= sample_time:
					break
				
				led_pin = CHANNELS_CONFIG[wavelength]['pin']
				duty_cycle = led_duty_cycle_settings[wavelength]
				set_pwm_duty_cycle(led_pin, duty_cycle)
				sleep(0.1) # Brief pause for LED to stabilize

				if use_spi:
					main_val, ref_val = read_alternating_spi(10)
				else:
					main_val, ref_val = read_adc(sample_time=10)
				
				raw_sensor_data_chunks[wavelength]['main'].append(main_val)
				raw_sensor_data_chunks[wavelength]['ref'].append(ref_val)

				set_pwm_duty_cycle(led_pin, 0)
			
			if stop_event.is_set():
				break
		
		# Average the collected chunks for final calculation
		raw_sensor_data = {}
		for wavelength in active_wavelengths:
			main_chunks = raw_sensor_data_chunks[wavelength]['main']
			ref_chunks = raw_sensor_data_chunks[wavelength]['ref']
			
			avg_main = sum(main_chunks) / len(main_chunks) if main_chunks else 0
			avg_ref = sum(ref_chunks) / len(ref_chunks) if ref_chunks else 0
			
			raw_sensor_data[wavelength] = {'main': avg_main, 'ref': avg_ref}

		delay = time() - start
		
		if airflow_sensor and current_measured_airflow_lpm > 0:
			volume_air_per_sample = (delay / 60) * current_measured_airflow_lpm
			airflow_per_minute = current_measured_airflow_lpm
		else:
			if config.get('disable_pump_control', False):
				airflow_per_minute = float(str(config.get('airflow_per_minute', 0.250)).replace(',', '.'))
				volume_air_per_sample = (delay / 60) * airflow_per_minute
			else:
				shutdown("No Airflow",6)

		absorption_coeffs = {}
		total_attenuation_coeff = 0
		bc_unfiltered_primary = 0 

		for wavelength in active_wavelengths:
			wl_config = CHANNELS_CONFIG[wavelength]
			
			sens_c = float(str(config.get(f"sens_correction_{wavelength}", sens_correction_default)).replace(',', '.'))
			ref_c = float(str(config.get(f"ref_correction_{wavelength}", ref_correction_default)).replace(',', '.'))
			
			main_sensor_value = raw_sensor_data[wavelength]['main'] * sens_c
			reference_sensor_value = raw_sensor_data[wavelength]['ref'] * ref_c

			if reference_sensor_value == 0: reference_sensor_value = 1
			if main_sensor_value == 0: main_sensor_value = 1

			attenuation_current = round((numpy.log(main_sensor_value / reference_sensor_value) * -100), 5)
			attenuation_last_run = last_run_values[wavelength]['atn']
			
			attenuation_coeff = sample_spot_areasize * ((attenuation_current - attenuation_last_run) / 100) / volume_air_per_sample if volume_air_per_sample > 0 else 0
			absorption_coeff = attenuation_coeff / filter_scattering_factor
			absorption_coeffs[wavelength] = absorption_coeff
			
			if wavelength == '880nm':
				total_attenuation_coeff = attenuation_coeff

			try:
				bc_unfiltered = int((absorption_coeff / wl_config['sigma']) * device_specific_correction_factor)
				if is_ebcMeter: bc_unfiltered /= 1000
			except Exception as e:
				bc_unfiltered = 1 if not is_ebcMeter else 0.001
				logger.error(f"Invalid BC calculation for {wavelength}: {e}")
			
			if wavelength == '880nm':
				bc_unfiltered_primary = bc_unfiltered

				quotient = main_sensor_value / reference_sensor_value
				filter_status = next((5 - i for i, t in enumerate([0.8, 0.7, 0.6, 0.4, 0.2]) if quotient > t), 0)
				manage_bcmeter_status(action='set', filter_status=filter_status)
				
				if config.get('filter_status_mail', False) and filter_status < 3 and (time() - last_filter_mail_time > 7200):
					send_email("Filter")
					last_filter_mail_time = time()

			last_run_values[wavelength]['atn'] = attenuation_current
			log_entry['wavelengths'][wavelength] = {'sen': main_sensor_value, 'ref': reference_sensor_value, 'atn': attenuation_current, 'bc_unfiltered': bc_unfiltered, 'bc': 0}

		# Append all new unfiltered values to our main history.
		for wavelength in active_wavelengths:
			unfiltered_val = log_entry['wavelengths'].get(wavelength, {}).get('bc_unfiltered', 0)
			bc_data_history['unfiltered'][wavelength].append(unfiltered_val)

		# Run the filter on all channels.
		filter_bc_values()

		# Update the 'bc' (filtered) value in the current log_entry for all wavelengths
		for wl in active_wavelengths:
			if bc_data_history['filtered'][wl]:
				log_entry['wavelengths'][wl]['bc'] = bc_data_history['filtered'][wl][-1]
			else: # Fallback if filtering didn't run
				log_entry['wavelengths'][wl]['bc'] = log_entry['wavelengths'][wl]['bc_unfiltered']

		aae_value = calculate_aae(absorption_coeffs) if len(active_wavelengths) > 1 else -1
		
		log_entry['common'] = {
			'date': datetime.now().strftime('%d-%m-%y'),
			'time': datetime.now().strftime('%H:%M:%S'),
			'relativeLoad': total_attenuation_coeff,
			'aae': aae_value,
			'temp': round(get_temperature(), 1),
			'notice': notice,
			'duration': round(delay, 1),
			'humidity': round(sht_humidity, 1) if 'sht_humidity' in globals() else 0,
			'airflow': round(airflow_per_minute, 3)
		}
		notice = ""

		should_log = not airflow_only and (
			bc_unfiltered_primary >= 10 or
			(datetime.now() - session_running_since).total_seconds() >= 15 * 60 or
			write_log
		) and samples_taken >= 3
		
		if is_ebcMeter:
			should_log = (samples_taken > 3 and bc_unfiltered_primary > 0) or write_log
		
		should_log = True if debug else should_log

		if should_log and not stop_event.is_set():
			write_log = True
			bc_data_history['all_log_data'].append(log_entry)
			
			write_log_with_updated_bc(logFileName, base_dir, active_wavelengths)
			
			valid_bc_values = [val for val in bc_data_history['filtered']['880nm'] if val > 0]
			recent_bc_values = valid_bc_values[-12:]
			average = sum(recent_bc_values) / len(recent_bc_values) if recent_bc_values else 0
			
			if samples_taken > 15 and average > 0:
				show_display(f"{int(average)} {unit}/m3 avg", False, 0)
			else:
				show_display("Sampling...", False, 0)




def check_service_running(service_name):
	try:
		result = subprocess.run(['systemctl', 'is-active', service_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		return result.stdout.decode().strip() == 'active'
	except subprocess.CalledProcessError:
		return False

def get_temperature():
	global last_valid_temperature, temperature_error_count, notice, sht_humidity
	try:
		if ds18b20:
			temperature_current = round(TemperatureSensor(channel=5).get_temperature_in_milli_celsius()/1000, 2)
		elif sht40_i2c:
			with i2c_lock:
				sensor = adafruit_sht4x.SHT4x(i2c)
				temperature_samples = []
				humidity_samples = []
				for i in range(20):
					temperature_samples.append(sensor.temperature)
					humidity_samples.append(sensor.relative_humidity)
				temperature_current = sum(temperature_samples) / 20
				sht_humidity = sum(humidity_samples) / 20
		else:
			logger.warning("No temperature sensor detected, using fallback value")
			return last_valid_temperature if 'last_valid_temperature' in globals() else 1
		last_valid_temperature = temperature_current
		temperature_error_count = 0
		return temperature_current
	except Exception as e:
		error_message = f"Temperature sensor error: {str(e)}"
		logger.warning(error_message)
		if 'temperature_error_count' not in globals():
			temperature_error_count = 0
		temperature_error_count += 1
		if temperature_error_count > 3:
			notice += f"TempErr({temperature_error_count})-"
		return last_valid_temperature if 'last_valid_temperature' in globals() else 1

def housekeeping(stop_event):
	"""
	Manages housekeeping tasks like temperature control and display updates.
	Airflow control is now in its own thread.
	"""
	global temperature_to_keep, session_running_since, ds18b20, config, temperature_current, TWELVEVOLT_ENABLE, notice
	
	if debug:
		print("[DEBUG] Housekeeping thread started.")
	TWELVEVOLT_IS_ENABLED = False
	while not stop_event.is_set():
		config = config_json_handler()
		
		
		send_log_by_mail = config.get('send_log_by_mail', False)
		if send_log_by_mail:
			mail_sending_interval_hours = float(str(config.get('mail_sending_interval', 24)).replace(',', '.'))
			interval_seconds = mail_sending_interval_hours * 3600
			
			if (time() - last_email_time) >= interval_seconds:
				logger.debug(f"Email interval of {mail_sending_interval_hours} hours reached. Attempting to send log.")
				if check_connection():
					send_email("Log") 
					last_email_time = time()
				else:
					logger.warning("Offline, cannot send periodic email log.")




		now = datetime.now()
		time_diff = now - session_running_since
		hours, remainder = divmod(time_diff.seconds, 3600)
		minutes, seconds = divmod(remainder, 60)
		show_display(f"Running: {hours:02d}:{minutes:02d}", 1, False)
		twelvevolt_duty = int(config.get('twelvevolt_duty', 20))
		if TWELVEVOLT_ENABLE:
			if not TWELVEVOLT_IS_ENABLED:
				pi.set_PWM_dutycycle(TWELVEVOLT_PIN, 0)
				sleep(2)
				TWELVEVOLT_IS_ENABLED = True
				print("12V Power is on, powering pump")
				for duty in range(0, twelvevolt_duty, int(twelvevolt_duty/5)):  
					pi.set_PWM_dutycycle(TWELVEVOLT_PIN, duty)
					sleep(0.1)
			twelvevolt_duty = int(config.get('twelvevolt_duty', 20))
			pi.set_PWM_dutycycle(TWELVEVOLT_PIN, twelvevolt_duty)
		# Handle temperature measurement and control
		try:
			temperature_current = get_temperature()
			#if debug: print(f"[DEBUG] Housekeeping: Current temperature is {temperature_current:.2f}°C.")
		except Exception as e:
			logger.error(f"Unexpected error in temperature handling: {str(e)}")
			temperature_current = temperature_current if 'temperature_current' in locals() else 1
			notice += "TempFail-"

		heating = config.get('heating', False)
		if heating and temperature_current != 1: # Skip if temp reading failed
			if debug: print(f"[DEBUG] Housekeeping: Heating is ON. Target: {temperature_to_keep}°C.")
			if temperature_current < temperature_to_keep:
				GPIO.output(1, GPIO.HIGH) # Heater ON
				GPIO.output(23, GPIO.HIGH)
				if debug: print("[DEBUG] Housekeeping: Temperature below target. Turning heater ON.")
			else:
				GPIO.output(1, GPIO.LOW) # Heater OFF
				GPIO.output(23, GPIO.LOW)
				if debug: print("[DEBUG] Housekeeping: Temperature at or above target. Turning heater OFF.")

		sleep(2)
		
	if debug:
		print("[DEBUG] Housekeeping thread stopped.")


def blink_led(pattern, change_blinking_pattern):
	if debug:
		return 
	while not change_blinking_pattern.is_set():
		blink_duration = 0.5 if pattern != 555 else 3
		GPIO.output(MONOLED_PIN, GPIO.HIGH)
		sleep(blink_duration)
		GPIO.output(MONOLED_PIN, GPIO.LOW)
		sleep(blink_duration*2)

def airflow_by_voltage(voltage,sensor_type):
	global airflow_sensor_bias
	
	corrected_voltage = voltage + airflow_sensor_bias
	#if debug: print(f"[DEBUG] Airflow calc: voltage={voltage:.4f}, bias={airflow_sensor_bias:.4f}, corrected_v={corrected_voltage:.4f}")

	if (sensor_type == 0):
		table = {0.5: 0.000, 2.5: 0.100} #
	elif (sensor_type == 1) :
		table = {0.50:0, 0.511:0.010, 0.8:0.055, 0.9:0.09, 1.34:0.19, 1.855:0.39, 1.96:0.46, 2.0:0.487, 2.024:0.504}
	else:
		return 0 

	if corrected_voltage in table:
		return table[corrected_voltage]
	else:
		voltages = sorted(table.keys())
		if corrected_voltage < voltages[0]: return 0
		if corrected_voltage > voltages[-1]:
			# Extrapolate for max range
			return table[voltages[-1]]

		# Linear interpolation
		lower_voltage = max(v for v in voltages if v <= corrected_voltage)
		upper_voltage = min(v for v in voltages if v >= corrected_voltage)
		
		if lower_voltage == upper_voltage:
			return table[lower_voltage]

		lower_value = table[lower_voltage]
		upper_value = table[upper_voltage]
		
		interpolated_value = lower_value + (corrected_voltage - lower_voltage) * (upper_value - lower_value) / (upper_voltage - lower_voltage)
		return interpolated_value

if __name__ == '__main__':
	GPIO.setup(1,GPIO.OUT)
	GPIO.setup(23,GPIO.OUT)
	GPIO.setwarnings(False)
	find_adc()

	if use_spi:
		logger.info("Using SPI ADC for measurements")
	else:
		logger.info("Using I2C ADC for measurements")

	if (calibration):
		if not use_spi:
			if not find_mcp_address():
				shutdown("I2C ADC not found for calibration", 6)
		if not initialize_pwm_control():
			logger.error("Failed to initialize PWM control for calibration")
			shutdown("PWM initialization failed", 6)

		print("Starting calibration, will take about a minute")
		calibrate_sens_ref()
		shutdown("Calibration done",5)

	blinking_pattern = 111
	show_display(f"Sampling...", False, 0)
	try:
		if not disable_led:
			blinking_thread = Thread(target=blink_led, args=(blinking_pattern,change_blinking_pattern))
			blinking_thread.start()
		if debug is True:
			print("Init")

		if not use_spi:
			if not find_mcp_address():
				shutdown("I2C ADC initialization failed", 6)

		airflow_sensor_bias = 0 
		if not calibration and airflow_type < 9:
			try:
				if debug: print("[DEBUG] __main__: Calling calibrate_airflow_sensor_bias...")
				bias_voltage = calibrate_airflow_sensor_bias()
				if debug: print(f"[DEBUG] __main__: calibrate_airflow_sensor_bias returned. Bias voltage: {bias_voltage}")
			except Exception as e:
				logger.error(f"Error reading airflow sensor bias: {e}")

		sleep(1)


		if not airflow_only:
			global session_running_since
			session_running_since = datetime.now()
			if debug: print("[DEBUG] __main__: Starting airflow control thread.")
			airflow_control_thread = Thread(target=airflow_control_thread_func, args=(stop_event,), name="AirflowControlThread")
			airflow_control_thread.daemon = True
			airflow_control_thread.start()

			if debug: print("[DEBUG] __main__: Starting housekeeping thread.")
			housekeeping_thread = Thread(target=housekeeping, args=(stop_event,), name="HousekeepingThread")
			housekeeping_thread.daemon = True
			housekeeping_thread.start()

		if debug: print("[DEBUG] __main__: Starting main sampling thread.")
		sampling_thread = Thread(target=bcmeter_main, args=(stop_event,), name="SamplingThread")
		sampling_thread.start()

		if debug:
			print("--- All threads started and running ---")
			if use_spi: print("--- Using SPI ADC ---")
			else: print("--- Using I2C ADC ---")

		# Keep the main thread alive to catch signals
		while not stop_event.is_set():
			sleep(1)

	except KeyboardInterrupt:
		shutdown("CTRL+C",5)
	except Exception as e:
		logger.error(f"An unexpected error occurred in the main block: {e}")
		shutdown("Main Exception", 6)
