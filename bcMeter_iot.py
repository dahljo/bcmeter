#!/usr/bin/env python3
"""
bcMeter IoT Library - SIM7080G Cellular Upload Module

Usage as library:
    from bcMeter_iot import is_iot_available, upload_log, upload_latest_log, IoTUploader

Usage standalone:
    sudo python3 bcMeter_iot.py [--test] [--status] [--latest] [--upload FILE]
"""

import serial
import time
import os
import sys
import glob
import json
import base64
import zlib
import hashlib
import platform
import shutil
import socket
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

__version__ = "1.0.1"

BASE_DIR = '/home/bcmeter' if os.path.isdir('/home/bcmeter') else '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'
LOG_DIR = os.path.join(BASE_DIR, 'maintenance_logs')
CONFIG_PATH = os.path.join(BASE_DIR, 'bcMeter_config.json')

DEFAULT_CONFIG = {
    'iot_enable': False,
    'iot_apn': 'iotsim.melita.io',
    'iot_url': 'https://xwqm43fafwo7w65d4lno3nspzu0ovykv.lambda-url.eu-north-1.on.aws',
    'iot_api_key': '',
    'iot_chunk_size': 2500,
    'iot_pwrkey_pin': 4,
    'iot_max_retries': 3,
    'mail_logs_to': '',
}

CHUNK_SIZE = 2500
MAX_SINGLE_PAYLOAD = 3500
REGISTRATION_TIMEOUT = 120
HTTP_TIMEOUT = 45

logger = None
VERBOSE_DEBUG = False


def setup_logging(name: str = 'bcMeter_iot') -> logging.Logger:
    global logger
    if logger is not None:
        return logger

    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    log_file = os.path.join(LOG_DIR, f'{name}.log')
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except OSError:
            pass

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_ts = os.path.join(LOG_DIR, f'{name}_{ts}.log')
    fh_ts = logging.FileHandler(log_file_ts)
    fh_ts.setLevel(logging.DEBUG)

    fmt = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
    fh.setFormatter(fmt)
    fh_ts.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(fh_ts)

    if VERBOSE_DEBUG:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    try:
        prefix = f"{name}_"
        logs = [f for f in os.listdir(LOG_DIR) if f.startswith(prefix) and f.endswith('.log')]
        logs.sort()
        for old in logs[:-10]:
            os.remove(os.path.join(LOG_DIR, old))
    except Exception:
        pass

    logger.debug(f"IoT library v{__version__} initialized")
    return logger


def vprint(msg: str):
    if VERBOSE_DEBUG:
        print(f"[DEBUG] {msg}")


def get_config() -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
                for k in cfg.keys():
                    if k in data:
                        val = data[k]
                        cfg[k] = val.get('value', val) if isinstance(val, dict) else val
        except Exception as e:
            if logger:
                logger.warning(f"Config load error: {e}")
    return cfg


def get_recipients() -> List[str]:
    cfg = get_config()
    mail_to = cfg.get('mail_logs_to', '')
    if not mail_to or mail_to == 'your@email.address':
        return []
    return [e.strip() for e in mail_to.split(',') if e.strip()]


def get_bcmeter_version() -> str:
    try:
        sys.path.insert(0, BASE_DIR)
        from bcMeter import bcMeter_version
        return bcMeter_version
    except Exception:
        pass
    return "unknown"


def get_mac_address() -> str:
    for iface in ['wlan0', 'eth0', 'usb0']:
        path = f'/sys/class/net/{iface}/address'
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return f.read().strip().replace(':', '')
            except Exception:
                pass
    return "unknown"


def get_device_id() -> str:
    return f"bcMeter_{get_mac_address()}"


def get_telemetry() -> Dict[str, Any]:
    info = {
        'hostname': socket.gethostname(),
        'device_id': get_device_id(),
        'platform': platform.platform(),
        'python': platform.python_version(),
        'bcmeter_version': get_bcmeter_version(),
        'iot_lib_version': __version__,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    try:
        total, used, free = shutil.disk_usage("/")
        info['disk_free_gb'] = round(free / (2**30), 1)
        info['disk_used_pct'] = round((used / total) * 100, 1)
    except Exception:
        pass
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            info['cpu_temp_c'] = round(int(f.read()) / 1000, 1)
    except Exception:
        pass
    try:
        with open('/proc/uptime') as f:
            info['uptime_hours'] = round(float(f.read().split()[0]) / 3600, 1)
    except Exception:
        pass
    return info


def is_uart_port(port: str) -> bool:
    return 'serial0' in port or 'ttyAMA' in port or 'ttyS0' in port


def open_serial(port: str, baudrate: int = 9600, timeout: float = 1) -> serial.Serial:
    vprint(f"Opening port {port}, baud={baudrate}, is_uart={is_uart_port(port)}")
    if is_uart_port(port):
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)
    else:
        ser = serial.Serial(port, baudrate, timeout=timeout)
    vprint(f"Port opened: rtscts={ser.rtscts}, dsrdtr={ser.dsrdtr}, xonxoff={ser.xonxoff}")
    return ser


def find_modem_port() -> Optional[Tuple[str, int]]:
    usb_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    uart_ports = ["/dev/serial0", "/dev/ttyS0"]

    if logger:
        logger.debug(f"Scanning USB: {usb_ports}, UART: {uart_ports}")
    vprint(f"Scanning USB: {usb_ports}, UART: {uart_ports}")

    for port in usb_ports:
        vprint(f"Trying USB port: {port} @ 115200")
        try:
            s = serial.Serial(port, 115200, timeout=1)
            s.write(b"AT\r")
            time.sleep(0.5)
            if s.in_waiting:
                resp = s.read(s.in_waiting)
                vprint(f"  Raw response: {resp}")
                if b"OK" in resp:
                    s.close()
                    if logger:
                        logger.info(f"Modem found on {port} @ 115200")
                    vprint(f"  SUCCESS: Modem found on {port} @ 115200")
                    return (port, 115200)
            s.close()
        except Exception as e:
            vprint(f"  Exception: {e}")
            continue

    for port in uart_ports:
        if not os.path.exists(port):
            continue
        vprint(f"Trying UART port: {port} @ 9600")
        try:
            s = open_serial(port, baudrate=9600, timeout=2)
            time.sleep(0.2)
            s.reset_input_buffer()

            for _ in range(3):
                vprint(f"  Sending AT command...")
                s.write(b"AT\r\n")
                s.flush()
                time.sleep(1)

                if s.in_waiting:
                    resp = s.read(s.in_waiting)
                    vprint(f"  Raw response: {resp}")
                    if b"OK" in resp:
                        s.close()
                        if logger:
                            logger.info(f"Modem found on {port} @ 9600")
                        vprint(f"  SUCCESS: Modem found on {port} @ 9600")
                        return (port, 9600)
            s.close()
        except Exception as e:
            vprint(f"  Exception: {e}")
            continue
    return None


def is_iot_available() -> bool:
    setup_logging()
    cfg = get_config()
    if not cfg.get('iot_enable', False):
        logger.debug("IoT disabled in config")
        return False
    result = find_modem_port()
    if result:
        logger.info("IoT modem available")
        return True
    logger.debug("No modem detected")
    return False


def compress_data(data: bytes) -> Tuple[bytes, float]:
    original = len(data)
    compressed = zlib.compress(data, level=9)
    ratio = len(compressed) / original if original > 0 else 1.0
    return compressed, ratio


class SIM7080G:
    def __init__(self, port: str, apn: str, pwrkey_pin: int = 4, baudrate: int = 9600):
        self.port = port
        self.apn = apn
        self.pwrkey_pin = pwrkey_pin
        self.baudrate = baudrate
        self.ser: Optional[serial.Serial] = None
        self.connected = False
        self.signal_quality = 0
        self._log = setup_logging()

    def _tx(self, cmd: str, wait: float = 2, verbose: bool = True) -> str:
        if not self.ser or not self.ser.is_open:
            return ""
        if verbose:
            self._log.debug(f"TX: {cmd}")
        vprint(f"TX: {cmd}")

        try:
            self.ser.reset_input_buffer()
            self.ser.write((cmd + "\r\n").encode())
            self.ser.flush()

            start = time.time()
            buf = b""
            while time.time() - start < wait:
                if self.ser.in_waiting:
                    chunk = self.ser.read(self.ser.in_waiting)
                    buf += chunk
                    vprint(f"  chunk: {chunk}")
                    if b"OK\r\n" in buf or b"ERROR\r\n" in buf or b"OK\n" in buf or b"ERROR\n" in buf:
                        break
                time.sleep(0.1)

            resp = buf.decode(errors='replace').strip()
        except (OSError, IOError, serial.SerialException) as e:
            self._log.warning(f"Serial I/O error: {e}")
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
            return ""
        if verbose and resp:
            for line in resp.split('\n'):
                if line.strip():
                    self._log.debug(f"RX: {line.strip()}")
        vprint(f"RX: {resp}")
        return resp

    def _tx_wait_urc(self, cmd: str, urc: str, timeout: float = 30) -> str:
        if not self.ser or not self.ser.is_open:
            return ""
        self._log.debug(f"TX (wait {urc}): {cmd}")
        vprint(f"TX (wait {urc}): {cmd}")

        try:
            self.ser.reset_input_buffer()
            self.ser.write((cmd + "\r\n").encode())
            self.ser.flush()

            start = time.time()
            buf = b""
            while time.time() - start < timeout:
                if self.ser.in_waiting:
                    buf += self.ser.read(self.ser.in_waiting)
                    decoded = buf.decode(errors='replace')
                    if urc in decoded and "\n" in decoded.split(urc)[-1]:
                        break
                time.sleep(0.1)

            resp = buf.decode(errors='replace').strip()
        except (OSError, IOError, serial.SerialException) as e:
            self._log.warning(f"Serial I/O error: {e}")
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
            return ""
        for line in resp.split('\n'):
            if line.strip():
                self._log.debug(f"RX: {line.strip()}")
        vprint(f"RX: {resp}")
        return resp

    def pulse_pwrkey(self) -> None:
        if not GPIO_AVAILABLE:
            self._log.error("GPIO not available")
            return
        self._log.info("Pulsing PWRKEY (power on sequence)...")
        vprint("Pulsing PWRKEY (power on sequence)...")

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pwrkey_pin, GPIO.OUT)

        GPIO.output(self.pwrkey_pin, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(self.pwrkey_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(self.pwrkey_pin, GPIO.LOW)

        self._log.info("Waiting 5s for modem boot...")
        vprint("Waiting 5s for modem boot...")
        time.sleep(5)

    def open(self) -> bool:
        try:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(b"AT\r\n")
                    return True
                except:
                    self.ser = None
            self._log.info(f"Opening serial port {self.port} @ {self.baudrate}")
            vprint(f"Opening serial port {self.port} @ {self.baudrate}")

            try:
                self.ser = open_serial(self.port, baudrate=self.baudrate, timeout=1)
            except (OSError, serial.SerialException) as e:
                self._log.warning(f"Original port failed: {e}, rescanning...")
                vprint(f"Original port failed, rescanning...")
                result = find_modem_port()
                if not result:
                    return False
                self.port, self.baudrate = result
                self.ser = open_serial(self.port, baudrate=self.baudrate, timeout=1)

            time.sleep(0.3)

            self.ser.reset_input_buffer()
            for _ in range(3):
                self.ser.write(b"AT\r\n")
                self.ser.flush()
                time.sleep(1)
                if self.ser.in_waiting:
                    resp = self.ser.read(self.ser.in_waiting)
                    vprint(f"Initial AT response: {resp}")
                    if b"OK" in resp:
                        break

            return True
        except Exception as e:
            self._log.error(f"Serial open error: {e}")
            vprint(f"Serial open error: {e}")
            return False

    def close(self) -> None:
        if self.ser:
            try:
                if self.ser.is_open:
                    self.ser.close()
                self._log.debug("Serial port closed")
            except:
                pass
            self.ser = None
        self.connected = False

    def get_signal_quality(self) -> int:
        resp = self._tx("AT+CSQ", 1, verbose=False)
        try:
            if "+CSQ:" in resp:
                val = int(resp.split("+CSQ:")[1].split(",")[0].strip())
                self.signal_quality = val
                return val
        except Exception:
            pass
        return 0

    def get_imsi(self) -> str:
        resp = self._tx("AT+CIMI", 1, verbose=False)
        for line in resp.split('\n'):
            line = line.strip()
            if line.isdigit() and len(line) >= 15:
                return line
        return ""

    def get_iccid(self) -> str:
        resp = self._tx("AT+CICCID", 1, verbose=False)
        if "+ICCID:" in resp:
            return resp.split("+ICCID:")[1].split()[0].strip()
        for line in resp.split('\n'):
            line = line.strip()
            if line.isdigit() and len(line) >= 19:
                return line
        return ""

    def get_ip_address(self) -> str:
        resp = self._tx("AT+CNACT?", 1, verbose=False)
        if "+CNACT:" in resp:
            parts = resp.split("+CNACT:")[1]
            if '"' in parts:
                ip = parts.split('"')[1]
                if ip and ip != "0.0.0.0":
                    return ip
        return ""

    def get_operator(self) -> str:
        resp = self._tx("AT+COPS?", 1, verbose=False)
        if "+COPS:" in resp and '"' in resp:
            return resp.split('"')[1]
        return ""

    def get_sim_info(self) -> dict:
        return {
            'imsi': self.get_imsi(),
            'iccid': self.get_iccid(),
            'ip': self.get_ip_address(),
            'operator': self.get_operator(),
            'signal': self.signal_quality
        }

    def _configure_lte(self) -> None:
        self._log.info("Configuring LTE-M...")
        vprint("Configuring LTE-M...")
        is_usb = 'USB' in self.port or 'ACM' in self.port
        if not is_usb:
            self._tx("AT+CFUN=0", 5)
            time.sleep(1)
        self._tx("AT+CNMP=38", 2)
        self._tx("AT+CMNB=1", 2)
        self._tx('AT+CBANDCFG="CAT-M",8,20', 2)
        self._tx(f'AT+CGDCONT=1,"IP","{self.apn}"', 2)
        self._tx(f'AT+CNCFG=1,1,"{self.apn}"', 2)
        if not is_usb:
            self._tx("AT+CFUN=1", 15)
        self._log.info("LTE config complete, waiting for network...")
        vprint("LTE config complete, waiting for network...")
        time.sleep(5)

    def _check_registration(self, timeout: int = REGISTRATION_TIMEOUT) -> bool:
        self._log.info(f"Waiting for registration (max {timeout}s)...")
        vprint(f"Waiting for registration (max {timeout}s)...")
        start = time.time()
        reconnect_attempts = 0
        while time.time() - start < timeout:
            if not self.ser:
                if reconnect_attempts >= 3:
                    self._log.error("Too many reconnect attempts")
                    return False
                self._log.info("Port lost, attempting reconnect...")
                vprint("Port lost, attempting reconnect...")
                time.sleep(2)
                if not self.open():
                    reconnect_attempts += 1
                    continue
                reconnect_attempts = 0

            csq = self.get_signal_quality()
            resp = self._tx("AT+CEREG?", 1, verbose=False)

            if not self.ser:
                continue

            status = "unknown"
            if "+CEREG:" in resp:
                if ",1" in resp:
                    status = "registered (home)"
                elif ",5" in resp:
                    status = "registered (roaming)"
                elif ",2" in resp:
                    status = "searching"
                elif ",0" in resp:
                    status = "not registered"

            self._log.debug(f"Registration: {status}, Signal: {csq}")
            vprint(f"Registration: {status}, Signal: {csq}")

            if ",1" in resp or ",5" in resp:
                self._log.info(f"Network registered, signal quality: {csq}")
                vprint(f"Network registered, signal quality: {csq}")
                return True
            time.sleep(3)

        self._log.error("Registration timeout")
        vprint("Registration timeout")
        self._tx("AT+CEER", 2)
        return False

    def connect(self) -> bool:
        if not self.open():
            return False

        self._tx("ATE0", 1)
        self._configure_lte()

        if self._check_registration():
            self._log.info("Activating data connection...")
            vprint("Activating data connection...")
            self._tx("AT+CNACT=1,1", 10)

            ip_resp = self._tx("AT+CNACT?", 2)
            if "+CNACT: 1,1" in ip_resp:
                self._log.info("Data connection active")
                vprint("Data connection active")
                self.connected = True
                return True
            else:
                self._log.warning("Data activation uncertain")
                vprint("Data activation uncertain (continuing anyway)")
                self.connected = True
                return True

        return False

    def http_post(self, url: str, api_key: str, device_id: str, payload: str) -> Tuple[bool, int, str]:
        payload_len = len(payload)
        self._log.info(f"HTTP POST {payload_len} bytes")
        vprint(f"HTTP POST {payload_len} bytes to {url}")

        self._tx("AT+SHDISC", 1)
        time.sleep(0.5)

        self._tx('AT+SHCONF="CONTEXTID",1', 1)
        self._tx('AT+CSSLCFG="sslversion",1,3', 1)
        self._tx('AT+SHSSL=1,""', 1)
        self._tx(f'AT+SHCONF="URL","{url}"', 2)
        self._tx('AT+SHCONF="BODYLEN",4096', 1)
        self._tx('AT+SHCONF="HEADERLEN",350', 1)

        self._log.debug("HTTP connecting...")
        vprint("HTTP connecting...")
        if "OK" not in self._tx("AT+SHCONN", 25):
            self._log.error("HTTP connect failed")
            vprint("HTTP connect FAILED")
            return False, 0, "Connect failed"

        time.sleep(0.5)
        self._tx("AT+SHCHEAD", 1)
        self._tx(f'AT+SHAHEAD="x-api-key","{api_key}"', 1)
        self._tx(f'AT+SHAHEAD="x-device-id","{device_id}"', 1)
        self._tx('AT+SHAHEAD="Content-Type","application/json"', 1)

        bod_resp = self._tx(f'AT+SHBOD={payload_len},10000', 2)
        if "ERROR" in bod_resp:
            self._log.error(f"Body setup failed: {bod_resp}")
            vprint(f"Body setup failed: {bod_resp}")
            self._tx("AT+SHDISC", 1)
            return False, 0, "Body setup failed"

        time.sleep(0.3)
        self.ser.write(payload.encode())
        self.ser.flush()
        time.sleep(1)

        self._log.debug("Sending request...")
        vprint("Sending HTTP request...")
        resp = self._tx_wait_urc('AT+SHREQ="/",3', "+SHREQ:", HTTP_TIMEOUT)

        success = False
        status_code = 0
        body = ""

        if "+SHREQ:" in resp:
            try:
                parts = resp.split("+SHREQ:")[1].split(",")
                status_code = int(parts[1])
                resp_len = int(parts[2].split()[0])
                self._log.info(f"HTTP {status_code}, response {resp_len} bytes")
                vprint(f"HTTP {status_code}, response {resp_len} bytes")

                if resp_len > 0:
                    time.sleep(0.5)
                    body_resp = self._tx(f'AT+SHREAD=0,{min(resp_len, 500)}', 5)
                    body = body_resp

                success = status_code in [200, 201]
            except Exception as e:
                self._log.error(f"Response parse error: {e}")
                vprint(f"Response parse error: {e}")
        else:
            self._log.error(f"No SHREQ response: {resp}")
            vprint(f"No SHREQ response: {resp}")

        self._tx("AT+SHDISC", 2)
        return success, status_code, body


class IoTUploader:
    def __init__(self, config: Optional[Dict] = None):
        self._log = setup_logging()
        self.config = config or get_config()
        self.modem: Optional[SIM7080G] = None
        self.device_id = get_device_id()
        self._log.info(f"IoTUploader initialized for {self.device_id}")

    def _ensure_modem(self) -> bool:
        if self.modem and self.modem.connected:
            return True

        result = find_modem_port()
        if not result:
            self._log.warning("No modem found, attempting power cycle...")
            vprint("No modem found, attempting power cycle...")
            temp = SIM7080G("/dev/ttyS0", self.config['iot_apn'], self.config['iot_pwrkey_pin'], 9600)
            temp.pulse_pwrkey()
            time.sleep(2)
            result = find_modem_port()

        if not result:
            self._log.error("Modem not found after power cycle")
            vprint("Modem not found after power cycle")
            return False

        port, baud = result
        self.modem = SIM7080G(port, self.config['iot_apn'], self.config['iot_pwrkey_pin'], baud)
        return self.modem.connect()

    def _upload_single(self, payload: Dict) -> bool:
        json_str = json.dumps(payload)
        if len(json_str) > MAX_SINGLE_PAYLOAD:
            self._log.error(f"Payload too large for single upload: {len(json_str)}")
            return False

        success, status, body = self.modem.http_post(
            self.config['iot_url'],
            self.config['iot_api_key'],
            self.device_id,
            json_str
        )
        return success

    def _upload_chunked(self, filename: str, compressed: bytes, recipients: List[str], telemetry: Dict) -> bool:
        chunk_size = self.config.get('iot_chunk_size', CHUNK_SIZE)
        total_chunks = (len(compressed) + chunk_size - 1) // chunk_size
        file_hash = hashlib.md5(compressed).hexdigest()[:8]
        upload_id = f"{self.device_id}_{int(time.time())}_{file_hash}"

        self._log.info(f"Chunked upload: {len(compressed)} bytes in {total_chunks} chunks")
        self._log.info(f"Upload ID: {upload_id}")

        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(compressed))
            chunk = compressed[start:end]

            payload = {
                "upload_id": upload_id,
                "chunk_index": i,
                "total_chunks": total_chunks,
                "chunk_b64": base64.b64encode(chunk).decode('ascii'),
                "filename": filename,
                "compressed": True,
                "final": i == total_chunks - 1
            }

            if i == 0:
                payload["telemetry"] = telemetry
                payload["recipients"] = recipients
                payload["total_size"] = len(compressed)

            self._log.info(f"Uploading chunk {i+1}/{total_chunks} ({len(chunk)} bytes)")

            retries = self.config.get('iot_max_retries', 3)
            success = False
            for attempt in range(retries):
                if self._upload_single(payload):
                    success = True
                    break
                self._log.warning(f"Chunk {i+1} attempt {attempt+1} failed, retrying...")
                time.sleep(2)

            if not success:
                self._log.error(f"Failed to upload chunk {i+1} after {retries} attempts")
                return False

            time.sleep(1)

        self._log.info("Chunked upload complete")
        return True

    def upload_file(self, filepath: str, recipients: Optional[List[str]] = None) -> bool:
        self._log.info(f"Upload request: {filepath}")

        if not os.path.exists(filepath):
            self._log.error(f"File not found: {filepath}")
            return False

        if recipients is None:
            recipients = get_recipients()
        if not recipients:
            self._log.warning("No recipients configured")

        try:
            with open(filepath, 'rb') as f:
                content = f.read()
        except Exception as e:
            self._log.error(f"File read error: {e}")
            return False

        filename = os.path.basename(filepath)
        original_size = len(content)
        self._log.info(f"File: {filename}, size: {original_size} bytes")

        compressed, ratio = compress_data(content)
        self._log.info(f"Compressed: {len(compressed)} bytes ({ratio*100:.1f}% of original)")

        telemetry = get_telemetry()
        telemetry['original_size'] = original_size
        telemetry['compressed_size'] = len(compressed)
        telemetry['compression_ratio'] = round(ratio, 3)

        if not self._ensure_modem():
            self._log.error("Could not establish modem connection")
            return False

        encoded = base64.b64encode(compressed).decode('ascii')
        payload = {
            "recipients": recipients,
            "filename": filename,
            "content_b64": encoded,
            "compressed": True,
            "telemetry": telemetry
        }

        payload_size = len(json.dumps(payload))
        self._log.debug(f"Total payload size: {payload_size} bytes")

        if payload_size <= MAX_SINGLE_PAYLOAD:
            self._log.info("Using single upload")
            return self._upload_single(payload)
        else:
            self._log.info("Payload too large, using chunked upload")
            return self._upload_chunked(filename, compressed, recipients, telemetry)

    def upload_data(self, data: bytes, filename: str, recipients: Optional[List[str]] = None) -> bool:
        self._log.info(f"Upload data request: {filename}, {len(data)} bytes")

        if recipients is None:
            recipients = get_recipients()

        compressed, ratio = compress_data(data)
        self._log.info(f"Compressed: {len(compressed)} bytes ({ratio*100:.1f}%)")

        telemetry = get_telemetry()
        telemetry['original_size'] = len(data)
        telemetry['compressed_size'] = len(compressed)

        if not self._ensure_modem():
            return False

        encoded = base64.b64encode(compressed).decode('ascii')
        payload = {
            "recipients": recipients,
            "filename": filename,
            "content_b64": encoded,
            "compressed": True,
            "telemetry": telemetry
        }

        if len(json.dumps(payload)) <= MAX_SINGLE_PAYLOAD:
            return self._upload_single(payload)
        else:
            return self._upload_chunked(filename, compressed, recipients, telemetry)

    def send_notification(self, notification_data: dict, recipients: Optional[List[str]] = None) -> bool:
        self._log.info(f"Notification request: {notification_data.get('notification_type', 'unknown')}")

        if recipients is None:
            recipients = get_recipients()

        if not self._ensure_modem():
            return False

        notification_data['recipients'] = recipients
        payload_str = json.dumps(notification_data)

        return self._upload_single(notification_data)

    def get_status(self) -> Dict[str, Any]:
        status = {
            'iot_enabled': self.config.get('iot_enable', False),
            'device_id': self.device_id,
            'modem_found': False,
            'connected': False,
            'signal_quality': 0,
            'recipients': get_recipients(),
        }

        result = find_modem_port()
        if result:
            port, baud = result
            status['modem_found'] = True
            status['modem_port'] = port
            status['modem_baud'] = baud

        if self.modem:
            status['connected'] = self.modem.connected
            status['signal_quality'] = self.modem.signal_quality
            status['sim_info'] = self.modem.get_sim_info()

        return status

    def get_sim_info(self) -> dict:
        if not self._ensure_modem():
            return {}
        return self.modem.get_sim_info()

    def disconnect(self) -> None:
        if self.modem:
            self.modem.close()
            self.modem = None


def upload_log(filepath: str, recipients: Optional[List[str]] = None) -> bool:
    uploader = IoTUploader()
    try:
        return uploader.upload_file(filepath, recipients)
    finally:
        uploader.disconnect()


def upload_latest_log(recipients: Optional[List[str]] = None) -> bool:
    log = setup_logging()
    log_dir = os.path.join(BASE_DIR, 'logs')

    if not os.path.exists(log_dir):
        log.error(f"Log directory not found: {log_dir}")
        return False

    files = []
    for fn in os.listdir(log_dir):
        if fn.lower().endswith(".csv") and fn.lower() != "log_current.csv":
            files.append(os.path.join(log_dir, fn))

    if not files:
        current = os.path.join(log_dir, "log_current.csv")
        if os.path.exists(current):
            files = [current]

    if not files:
        log.error("No log files found")
        return False

    files.sort(key=os.path.getmtime, reverse=True)
    return upload_log(files[0], recipients)


def main():
    global VERBOSE_DEBUG

    import argparse
    parser = argparse.ArgumentParser(description='bcMeter IoT Upload Utility')
    parser.add_argument('--test', action='store_true', help='Test modem connection')
    parser.add_argument('--status', action='store_true', help='Show IoT status')
    parser.add_argument('--upload', type=str, help='Upload specific file')
    parser.add_argument('--latest', action='store_true', help='Upload latest log')
    args = parser.parse_args()

    if args.test:
        VERBOSE_DEBUG = True

    if os.geteuid() != 0:
        print("Run as root (sudo)")
        sys.exit(1)

    setup_logging()
    uploader = IoTUploader()

    try:
        if args.status:
            status = uploader.get_status()
            print(json.dumps(status, indent=2))

        elif args.test:
            print("Testing modem connection (verbose mode)...")
            print(f"Checking UART config: /dev/serial0 exists = {os.path.exists('/dev/serial0')}")

            config_path = '/boot/firmware/config.txt' if os.path.exists('/boot/firmware/config.txt') else '/boot/config.txt'
            uart_enabled = False
            bt_disabled = False

            if os.path.exists(config_path):
                with open(config_path) as f:
                    cfg = f.read()
                    uart_enabled = 'enable_uart=1' in cfg
                    bt_disabled = 'dtoverlay=disable-bt' in cfg or 'dtoverlay=miniuart-bt' in cfg
                    print(f"enable_uart=1: {uart_enabled}")
                    print(f"bluetooth overlay disabled: {bt_disabled}")

            config_changed = False
            if not uart_enabled or not bt_disabled:
                print("\nUART not properly configured. Fixing...")
                try:
                    if not uart_enabled:
                        print("  Enabling UART...")
                        os.system("raspi-config nonint do_serial_hw 0")
                        config_changed = True

                    os.system("raspi-config nonint do_serial_cons 1")

                    if not bt_disabled:
                        print("  Disabling Bluetooth on UART...")
                        with open(config_path, 'a') as f:
                            f.write("\ndtoverlay=disable-bt\n")
                        os.system("systemctl disable hciuart 2>/dev/null")
                        config_changed = True

                    if config_changed:
                        print("\n" + "="*50)
                        print("UART configuration changed. REBOOT REQUIRED.")
                        print("Run: sudo reboot")
                        print("Then re-run: sudo python3 bcMeter_iot.py --test")
                        print("="*50)
                        sys.exit(0)
                except Exception as e:
                    print(f"Failed to configure UART: {e}")
                    print(f"Manually add to {config_path}:")
                    print("  enable_uart=1")
                    print("  dtoverlay=disable-bt")
                    sys.exit(1)

            if uploader._ensure_modem():
                print("\nSUCCESS: Modem connected")
                print(f"Signal quality: {uploader.modem.signal_quality}")
                print(f"SIM info: {json.dumps(uploader.modem.get_sim_info(), indent=2)}")
            else:
                print("\nFAILED: Could not connect")
                sys.exit(1)

        elif args.upload:
            if uploader.upload_file(args.upload):
                print("SUCCESS")
            else:
                print("FAILED")
                sys.exit(1)

        elif args.latest:
            if upload_latest_log():
                print("SUCCESS")
            else:
                print("FAILED")
                sys.exit(1)

        else:
            parser.print_help()

    finally:
        uploader.disconnect()


if __name__ == "__main__":
    main()
