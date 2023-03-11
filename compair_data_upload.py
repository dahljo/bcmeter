#upload data to compair network
import requests
import json
import uuid
import datetime
import random
from time import sleep

# endpoint for checking internet connection (this is Google's public DNS server)
DNS_HOST = "8.8.8.8"
DNS_PORT = 53
DNS_TIME_OUT = 3

online = False

thing_id = hex(uuid.getnode())
post_to_sensors = "/sensors"
post_to_observations = "/sensors/observations"

name_ng = "Nanogram per cubic meter"
name_atn = "Attenuation"
name_sen = "Raw Sensor Value"
name_ref = "Raw Reference Value"
name_temperature = "Temperature measured in device"
name_coordinates = "Position"
name_filter_status ="Filter Status"


sensor = {
		"MultiDatastreams": [ 
		{ 
			"thingId": thing_id, 
			"unitOfMeasurements": [ 
			  
			{ 
					"name": name_ng, 
					"symbol": "ng/m3" 
				}, 
				{ 
					"name": name_atn, 
					"symbol": "ATN" 
				}, 
				{ 
					"name": name_sen, 
					"symbol": "mV at ADC" 
				},
				{ 
					"name": name_ref, 
					"symbol": "mV at ADC" 
				},
				{ 
					"name": name_temperature, 
					"symbol": "°C" 
				},
				{ 
					"name": name_coordinates, 
					"symbol": "lat/lon" 
				},
				{ 
					"name": name_filter_status, 
					"symbol": "fs" 
				}  


			],

			 "Sensor": { 
				"name": "bcMeter sensor", 
				"description": "low cost black carbon measurement device www.bcmeter.org" 
			},
			"ObservedProperties": [ 
				{ 
					"name": "bcngm3" 
				}, 
				{ 
					"name": "atn" 
				}, 
				{ 
					"name": "rawSen" 
				},
				{ 
					"name": "rawRef" 
				},
				{ 
					"name": "temperature" 
				},
				{ 
					"name": "coordinates" 
				},
				{ 
					"name": "filter status" 
				}

	] 


}
]
}





def get_observations(timestamp,bcngm3,atn,bcmsen,bcmref,bcmtemperature,location, filter_status):
	observations = {
	  "provider": "bcmeter", 
	   "data": {
	   "observations": [ 
				{ 
					"multiDatastream@iot.name": name_ng, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": 
						 [bcngm3] 
	  
				}, 
				{ 
					"multiDatastream@iot.name": name_atn, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": 
						 [atn]
	  
				}, 
				{ 
					"multiDatastream@iot.name": name_sen, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": 
						 [bcmsen] 
	  
				}, 
							{ 
					"multiDatastream@iot.name": name_ref, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": [bcmref]  
				}, 
				{ 
					"multiDatastream@iot.name": name_temperature, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": 
						 [bcmtemperature] 
	  
				},
				{ 
					"multiDatastream@iot.name": name_coordinates, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": 
						 location
	  
				},
				{ 
					"multiDatastream@iot.name": name_filter_status, 
					"thingId": thing_id, 
					"resultTime": timestamp, 
					"result": 
						 [filter_status]
	  
				} 
			]
	   } 
	 }

	return observations

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
	


def get_timestamp():
	dateTimeObj = datetime.datetime.now()
	return dateTimeObj.strftime("%Y-%m-%dT%H:%M:%SZ")

def check_if_sensor_registered():
	print("checking if this bcMeter is known at CompAir")
	url = "https://services.dev.wecompair.eu/receiver/sensors/exists?thingIdentifier=" + thing_id
	registered = requests.get(url).text
	if (registered == "false"):
		url = "https://services.dev.wecompair.eu/receiver" + post_to_sensors
		res = requests.post(url, json=sensor) 
		print("bcMeter registered:",res.status_code)
	else:
		print("bcMeter already registered!")

online = check_connection()
if (online is True):
	check_if_sensor_registered()

def upload_sample(bcngm3,atn,bcmsen,bcmref,bcmtemperature, location, filter_status):
	timestamp = get_timestamp()
	observations = get_observations(timestamp,bcngm3,atn,bcmsen,bcmref,bcmtemperature,location, filter_status)
	url = "https://services.dev.wecompair.eu/receiver" + post_to_observations
	res = requests.post(url, json=observations) 

