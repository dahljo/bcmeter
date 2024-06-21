#upload data to compair network
import requests
import json
import uuid
import random
import socket
import csv
import os
from time import sleep
import sys
from datetime import datetime
import importlib
from bcMeter_shared import convert_config_to_json, load_config_from_json, check_connection, update_interface_status, show_display, setup_logging

config = load_config_from_json()

logger = setup_logging('compair_frost_upload')



logger.debug("Compair FROST Upload initialized")

online = False

frost_id = "bcMeter"
thing_id = frost_id +"_"+hex(uuid.getnode())

name_ng = "Black Carbon"
name_atn = "Attenuation"
name_sen = "Raw Sensor Value"
name_ref = "Raw Reference Value"
name_temperature = "Temperature"
name_coordinates = "Position"
name_filter_status ="Filter Status"

def get_location():
	import json
	import requests 
	my_ip = requests.get('https://api.ipify.org').text
	my_loc = requests.get('https://ipinfo.io/'+my_ip).text
	my_loc = json.loads(my_loc)
	my_lat =  float(my_loc['loc'].split(',')[0])
	my_lon = float(my_loc['loc'].split(',')[1])
	return [my_lat,my_lon]



online = check_connection()
print(online, "frost upload online")

location = config.get('location',[0,0])


if (config.get('get_location') is True) and online is True:
	with open('bcMeter_config.json', 'r') as file:
	    config = json.load(file)
	location = get_location()  # This function needs to return an array [latitude, longitude]
	print(f"location vor save: {location}")
	config['location']['value'] = location
	with open('bcMeter_config.json', 'w') as file:
		json.dump(config, file, indent=4)
	config = load_config_from_json()

location=config.get('location')
location_to_reverse = config.get('location')
location = location_to_reverse[::-1] #reverse to comply to frost syntax

if (location[0]==0) and (location[1] == 0):
	error_message="No valid Location for bcMeter given, cancelling. Enter manually or check options and internet connection"
	logger.error(error_message)
	print(error_message)
	sys.exit(1)


def update_location(location):
	url="https://services.wecompair.eu/receiver/sensors/Locations"
	old_location_request = requests.get(f"https://sensorthings.wecompair.eu/FROST-Server/v1.1/Things('{thing_id}')?$expand=Locations").text
	request_json = json.loads(old_location_request)
	code = request_json.get('code', 0)
	if (code != 404):
		longitude = request_json['Locations'][0]['location']['geometry']['coordinates'][1]
		latitude = request_json['Locations'][0]['location']['geometry']['coordinates'][0]

		old_location = [latitude, longitude]
	else:
		old_location = [0,1]

	old_location = [0, 1] if code == 404 else request_json['Locations'][0]['location']['geometry']['coordinates'][::-1]

	if (old_location != location):
		logger.debug("updating location")
		new_location_body = {
				"name": "BcMeter",
				"description": "BcMeter",
				"encodingType": "application/geo+json",
				"location": {
					"type": "Feature",
					"properties": {},
					"geometry": {
						"type": "Point",
						"coordinates": location
					}
				},
				"Things": [
				{ "@iot.id": f"{thing_id}"}
			  ]
			}		
		res = requests.post(url, json=new_location_body) 
		logger.debug("updated location %s, %s, %s", thing_id, location, res)

	

if (online is True):
	update_location(location)


def get_frost_observations(timestamp, bcngm3,atn,bcmsen,bcmref,bcmtemperature,location, filter_status):
	data_streams = [
		{
			"Datastream": {
				"@iot.id": f"{thing_id}_bc"
			},
			"components": ["phenomenonTime", "result"],
			"dataArray": [[timestamp, bcngm3]],
		},
		{
			"Datastream": {
				"@iot.id": f"{thing_id}_atn"
			},
			"components": ["phenomenonTime", "result"],
			"dataArray": [[timestamp, atn]],
		},
		{
			"Datastream": {
				"@iot.id": f"{thing_id}_sen"
			},
			"components": ["phenomenonTime", "result"],
			"dataArray": [[timestamp, bcmsen]],
		},
		{
			"Datastream": {
				"@iot.id": f"{thing_id}_ref"
			},
			"components": ["phenomenonTime", "result"],
			"dataArray": [[timestamp, bcmref]],
		},
		{
			"Datastream": {
				"@iot.id": f"{thing_id}_temp"
			},
			"components": ["phenomenonTime", "result"],
			"dataArray": [[timestamp, bcmtemperature]],
		},
		{
			"Datastream": {
				"@iot.id": f"{thing_id}_filter_status"
			},
			"components": ["phenomenonTime", "result"],
			"dataArray": [[timestamp, filter_status]],
		},
	]
	return data_streams




def get_timestamp():
	dateTimeObj = datetime.now()
	return dateTimeObj.strftime("%Y-%m-%dT%H:%M:%SZ")

def check_if_sensor_registered(): 
	url = "https://services.dev.wecompair.eu/data/sensors/exists?thingIdentifier=" + thing_id
	registered = requests.get(url).status_code
	if (registered == 404):
		url = "https://sensorthings.wecompair.eu/FROST-Server/v1.1/$batch"
		thing_id_body = {
			"@iot.id": thing_id,
			"name": thing_id,
			"description": "bcMeter",
			"properties": {
				"source": "bcmeter",
				"dataType": "AIR"
			},
			"Locations":[
			{
				"name": "Citizen Science Device",
				"description": "Citizen Science Device",
				"encodingType": "application/geo+json",
				"location": {
					"type": "Feature", "properties": {}, "geometry": {
						"type": "Point", "coordinates": location
					} 
				}
			}
			] 
		 }

		datastreams_bc = {
		"@iot.id": thing_id + "_bc",
		"name": "Black Carbon",
		"ObservedProperty": {
		"@iot.id": "bcngm3" },
		"Sensor": {
		"@iot.id": "bcMeter"
		}, "Thing": {
		"@iot.id": "$" + thing_id
		},
		"description": "measurement done by bcMeter",
		"unitOfMeasurement": {
		"name": "nanograms per cubic meter",
		"symbol": "ng/m3",
		"definition": "http://dd.eionet.europa.eu/vocabulary/uom/concentration/ng.m-3"
		},
		"observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
		}

		datastreams_atn = {
		"@iot.id": thing_id + "_atn",
		"name": "Attenuation",
		"ObservedProperty": {
		"@iot.id": "atn"
		},
		"Sensor": {
		"@iot.id": "bcMeter"
		}, "Thing": {
		"@iot.id": "$" + thing_id
		},
		"description": "measurement done by bcMeter",
		"unitOfMeasurement": {
		"name": "Attenuation (Absolute)",
		"symbol": "mV (conv)",
		"definition": ""
		},
		"observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
		}

		datastreams_sen = {
		"@iot.id": thing_id + "_sen",
		"name": "Raw sensor",
		"ObservedProperty": {
		"@iot.id": "sen"
		},
		"Sensor": {
		"@iot.id": "bcMeter"
		}, "Thing": {
		"@iot.id": "$" + thing_id
		},
		"description": "measurement done by bcMeter",
		"unitOfMeasurement": {
		"name": "Raw Sensor",
		"symbol": "",
		"definition": ""
		},
		"observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
		}

		datastreams_ref = {
		"@iot.id": thing_id + "_ref",
		"name": "Raw Reference",
		"ObservedProperty": {
		"@iot.id": "ref"
		},
		"Sensor": {
		"@iot.id": "bcMeter"
		}, "Thing": {
		"@iot.id": "$" + thing_id
		},
		"description": "measurement done by bcMeter",
		"unitOfMeasurement": {
		"name": "Raw Reference",
		"symbol": "",
		"definition": ""
		},
		"observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
		}

				
		datastreams_temp = {
		"@iot.id": thing_id + "_temp",
		"name": "Device Temperature",
		"ObservedProperty": {
		"@iot.id": "temp"
		},
		"Sensor": {
		"@iot.id": "bcMeter"
		}, "Thing": {
		"@iot.id": "$" + thing_id
		},
		"description": "measurement done by bcMeter",
		"unitOfMeasurement": {
		"name": "Temperature",
		"symbol": "degC",
		"definition": ""
		},
		"observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
		}

		datastreams_filter_status = {
		"@iot.id": thing_id + "_filter_status",
		"name": "Filter Status",
		"ObservedProperty": {
		"@iot.id": "filter_status"
		},
		"Sensor": {
		"@iot.id": "bcMeter"
		}, "Thing": {
		"@iot.id": "$" + thing_id
		},
		"description": "measurement done by bcMeter",
		"unitOfMeasurement": {
		"name": "Filter Status",
		"symbol": "",
		"definition": "Change when 3 or below"
		},
		"observationType": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement"
		}

		thing_requests = [
		{
		"id": thing_id,
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Things",
		"body": thing_id_body
		},
		{
		"id": thing_id + "_bc",
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Datastreams",
		"body": datastreams_bc
		},
		{
		"id": thing_id + "_atn",
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Datastreams",
		"body": datastreams_atn
		},
		{
		"id": thing_id + "_sen",
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Datastreams",
		"body": datastreams_sen
		},
		{
		"id": thing_id + "_ref",
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Datastreams",
		"body": datastreams_ref
		},
		{
		"id": thing_id + "_temp",
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Datastreams",
		"body": datastreams_temp
		},
		{
		"id": thing_id + "_filter_status",
		"atomicityGroup": "group1",
		"method": "post",
		"url": "Datastreams",
		"body": datastreams_filter_status
		}
		]

		save_the_thing = {
		"requests": thing_requests
		}


		res = requests.post(url, json=save_the_thing) 
		logger.debug("Registered this device at CompAIR: %s",res.status_code)

	if (registered == 200):
		logger.debug("bcMeter already registered at CompAIR!")

if (online is True):
	check_if_sensor_registered()


def upload_sample(bcngm3,atn,bcmsen,bcmref,bcmtemperature, location, filter_status):
	timestamp = get_timestamp()
	observations = get_frost_observations(timestamp, bcngm3,atn,bcmsen,bcmref,bcmtemperature,location, filter_status)
	url = "https://sensorthings.wecompair.eu/FROST-Server/v1.1/CreateObservations"
	try:
		res = requests.post(url, json=observations)
		logger.debug(f"uploaded sample to FROST with return code {res}") 
	except Exception as e:
		logger.error(f"An error occurred: {e}")

def compair_frost_upload_offline_log(compair_offline_log_path):
	data_streams = []

	with open(compair_offline_log_path, 'r') as csvfile:
		reader = csv.DictReader(csvfile, delimiter=";")
		for row in reader:
			if row != "":
				timestamp = str(row['timestamp'])
				bcngm3 = float(row['bcngm3'])
				atn = float(row['atn'])
				bcmsen = float(row['bcmsen'])
				bcmref = float(row['bcmref'])
				bcmtemperature = float(row['bcmtemperature'])
				filter_status = int(row['filter_status'])

				data_streams.append({
					"Datastream": {
						"@iot.id": f"{thing_id}_bc"
					},
					"components": ["phenomenonTime", "result"],
					"dataArray": [[timestamp, bcngm3]],
				})
				data_streams.append({
					"Datastream": {
						"@iot.id": f"{thing_id}_atn"
					},
					"components": ["phenomenonTime", "result"],
					"dataArray": [[timestamp, atn]],
				})
				data_streams.append({
					"Datastream": {
						"@iot.id": f"{thing_id}_sen"
					},
					"components": ["phenomenonTime", "result"],
					"dataArray": [[timestamp, bcmsen]],
				})
				data_streams.append({
					"Datastream": {
						"@iot.id": f"{thing_id}_ref"
					},
					"components": ["phenomenonTime", "result"],
					"dataArray": [[timestamp, bcmref]],
				})
				data_streams.append({
					"Datastream": {
						"@iot.id": f"{thing_id}_temp"
					},
					"components": ["phenomenonTime", "result"],
					"dataArray": [[timestamp, bcmtemperature]],
				})
				data_streams.append({
					"Datastream": {
						"@iot.id": f"{thing_id}_filter_status"
					},
					"components": ["phenomenonTime", "result"],
					"dataArray": [[timestamp, filter_status]],
				})


	result_dict = {}
	for obj in data_streams:
		if 'Datastream' in obj and isinstance(obj['Datastream'], dict) and '@iot.id' in obj['Datastream']:
			datastream_id = obj['Datastream']['@iot.id']
			if datastream_id not in result_dict:
				result_dict[datastream_id] = {
					'Datastream': obj['Datastream'],
					'components': obj['components'],
					'dataArray': []
				}
			
			result_dict[datastream_id]['dataArray'].extend(obj['dataArray'])

	output_data = []

	for key, value in result_dict.items():
		output_data.append({
			"Datastream": value["Datastream"],
			"components": value["components"],
			"dataArray": value["dataArray"]
		})


	url = "https://sensorthings.wecompair.eu/FROST-Server/v1.1/CreateObservations"
	res = requests.post(url, json=output_data)
	logger.debug(f"uploaded offline data to frost, return code {res}") 

