import smbus
import time

bus = smbus.SMBus(1)
#MCP3426_DEFAULT_ADDRESS = 0x68

# /RDY bit definition
MCP3426_CONF_NO_EFFECT = 0x00
MCP3426_CONF_RDY = 0x80

# Conversion mode definitions
MCP3426_CONF_MODE_ONESHOT = 0x00
MCP3426_CONF_MODE_CONTINUOUS = 0x10

# Channel definitions
MCP3426_CONF_CHANNEL_1 = 0x00
MCP3426_CHANNEL_2 = 0x20

# Sample size definitions - these also affect the sampling rate
MCP3426_CONF_SIZE_12BIT = 0x00
MCP3426_CONF_SIZE_14BIT = 0x04
MCP3426_CONF_SIZE_16BIT = 0x08

# Programmable Gain definitions
MCP3426_CONF_GAIN_1X = 0x00
MCP3426_CONF_GAIN_2X = 0x01
MCP3426_CONF_GAIN_4X = 0x02
MCP3426_CONF_GAIN_8X = 0x03

VRef = 2.048

ready = MCP3426_CONF_RDY
channel1 = MCP3426_CONF_CHANNEL_1
channel2 = MCP3426_CHANNEL_2
mode = MCP3426_CONF_MODE_CONTINUOUS
rate_12bit = MCP3426_CONF_SIZE_12BIT
rate_14bit = MCP3426_CONF_SIZE_14BIT
rate_16bit = MCP3426_CONF_SIZE_16BIT 
gain = MCP3426_CONF_GAIN_2X
rate = rate_16bit

verbose_output = False

def initialise(channel, rate):
    config = (ready|channel|mode|rate|gain)
    bus.write_byte(MCP3426_DEFAULT_ADDRESS, config)
    time.sleep(0.01)


def find_mcp_adress():
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
    print("ADC found at Address:", hex(MCP3426_DEFAULT_ADDRESS))
    return(MCP3426_DEFAULT_ADDRESS)




def getconvert(channel, rate):
    if rate == rate_12bit:
        N = 12
        mcp_sps = 1/240
    elif rate == rate_14bit:
        N = 14
        mcp_sps = 1/60
    elif rate == rate_16bit:
        N = 16
        mcp_sps = 1/15


    time.sleep(mcp_sps) 
    data = bus.read_i2c_block_data(MCP3426_DEFAULT_ADDRESS, channel, 2)



    voltage = ((data[0] << 8) | data[1])
    if voltage >= 32768:
        voltage = 65536 - voltage
    voltage = (2 * VRef * voltage) / (2 ** N)
    return voltage

def read_adc(mcp_i2c_address, samplecount):
    global MCP3426_DEFAULT_ADDRESS, verbose_output
    MCP3426_DEFAULT_ADDRESS = mcp_i2c_address
    sum_channel1 = 0
    sum_channel2 = 0
    for _ in range(samplecount):
        initialise(channel1, rate)
        voltage_channel1 = getconvert(channel1, rate)
        sum_channel1 += voltage_channel1
        initialise(channel2, rate)
        voltage_channel2 = getconvert(channel2, rate)
        sum_channel2 += voltage_channel2
        if (verbose_output is True): 
            print("ref:", voltage_channel2, "sen:", voltage_channel1)

    average_channel1 = sum_channel1 / samplecount
    average_channel2 = sum_channel2 / samplecount
    return(int(average_channel1*10000), int(average_channel2*10000))

    
if __name__ == '__main__':
    verbose_output = True
    MCP3426_DEFAULT_ADDRESS=find_mcp_adress()

    while True:
        read_adc(MCP3426_DEFAULT_ADDRESS,100)




