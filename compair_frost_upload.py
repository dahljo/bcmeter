#upload data to compair network
import requests
import json
import uuid
import datetime
import random
import socket
import bcMeterConf

from time import sleep


# endpoint for checking internet connection (this is Google's public DNS server)
DNS_HOST = "8.8.8.8"
DNS_PORT = 53
DNS_TIME_OUT = 3

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

location = bcMeterConf.location[::-1]
print(location)

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



def check_connection():
	connection_ok = False
	current_time = 0
	while current_time < 5:
		try:
			socket.setdefaulttimeout(DNS_TIME_OUT)
			socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((DNS_HOST, DNS_PORT))
			connection_ok = True
			break
		except Exception as e:
			current_time += 1
			print("Caught exception: ", e)
			sleep(1)
	return connection_ok


def get_timestamp():
	dateTimeObj = datetime.datetime.now()
	return dateTimeObj.strftime("%Y-%m-%dT%H:%M:%SZ")

def check_if_sensor_registered(): #to be adjusted for FROST
	url = "https://services.dev.wecompair.eu/data/sensors/exists?thingIdentifier=" + thing_id
	registered = requests.get(url).status_code
	if (registered == 404):
		url = "https://sensorthings.wecompair.eu/FROST-Server/v1.1/$batch"


		"body" = {
			"@iot.id": thing_id,
			"name": thing_id,
			"description": "bcMeter",
            "properties": {
                "source": "bcmeter",
                "dataType": "AIR"
            }
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
		print("This device registered:",res.status_code)

	if (registered == 200):
		print("bcMeter already registered!")


online = check_connection()

if (online is True):
	print("checking if sensor is registered")
	check_if_sensor_registered()


def upload_sample(bcngm3,atn,bcmsen,bcmref,bcmtemperature, location, filter_status):
	timestamp = get_timestamp()
	observations = get_frost_observations(timestamp, bcngm3,atn,bcmsen,bcmref,bcmtemperature,location, filter_status)
	url = "https://sensorthings.wecompair.eu/FROST-Server/v1.1/CreateObservations"
	res = requests.post(url, json=observations) 
	print(observations)
