#!/usr/bin/env python3
"""SPS30 Particulate Matter Sensor Library for Raspberry Pi - with external lock support"""

import struct
import time
from smbus2 import SMBus, i2c_msg

SPS30_ADDR = 0x69

CMD_START_MEASUREMENT = [0x00, 0x10]
CMD_STOP_MEASUREMENT = [0x01, 0x04]
CMD_DATA_READY = [0x02, 0x02]
CMD_READ_VALUES = [0x03, 0x00]

def _crc8(data):
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) if crc & 0x80 else (crc << 1)
            crc &= 0xFF
    return crc

class SPS30:
    def __init__(self, bus=1, i2c_lock=None):
        self.bus = SMBus(bus)
        self.addr = SPS30_ADDR
        self.lock = i2c_lock

    def _with_lock(self, func):
        if self.lock:
            with self.lock:
                return func()
        return func()

    def _write(self, cmd):
        def do_write():
            msg = i2c_msg.write(self.addr, cmd)
            self.bus.i2c_rdwr(msg)
        self._with_lock(do_write)

    def _read(self, cmd, length):
        def do_read():
            write = i2c_msg.write(self.addr, cmd)
            read = i2c_msg.read(self.addr, length)
            self.bus.i2c_rdwr(write)
            time.sleep(0.02)
            self.bus.i2c_rdwr(read)
            return list(read)
        raw = self._with_lock(do_read)
        data = []
        for i in range(0, length, 3):
            if _crc8(raw[i:i+2]) != raw[i+2]:
                raise IOError(f"CRC mismatch at byte {i}")
            data.extend(raw[i:i+2])
        return data

    def start(self):
        data = [0x03, 0x00, _crc8([0x03, 0x00])]
        self._write(CMD_START_MEASUREMENT + data)
        time.sleep(0.02)

    def stop(self):
        self._write(CMD_STOP_MEASUREMENT)

    def data_ready(self):
        data = self._read(CMD_DATA_READY, 3)
        return data[1] == 1

    def read(self):
        data = self._read(CMD_READ_VALUES, 60)
        values = [struct.unpack('>f', bytes(data[i:i+4]))[0] for i in range(0, len(data), 4)]
        return {
            'pm1.0': values[0], 'pm2.5': values[1], 'pm4.0': values[2], 'pm10': values[3],
            'nc0.5': values[4], 'nc1.0': values[5], 'nc2.5': values[6], 'nc4.0': values[7],
            'nc10': values[8], 'tps': values[9]
        }

    def close(self):
        self.bus.close()

if __name__ == '__main__':
    sensor = SPS30()
    try:
        sensor.start()
        time.sleep(1)
        for _ in range(30):
            if sensor.data_ready():
                break
            time.sleep(1)
        data = sensor.read()
        print(f"PM2.5: {data['pm2.5']:.2f} µg/m³")
        print(f"PM10:  {data['pm10']:.2f} µg/m³")
    finally:
        sensor.stop()
        sensor.close()