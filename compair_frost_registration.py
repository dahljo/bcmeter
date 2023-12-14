
def register_bcMeter():
	url = "https://sensorthings.wecompair.eu/FROST-Server/v1.1/$batch"
	sensor = {
		"requests": [
			{
				"id": frost_id,
				"atomicityGroup": "group1",
				"method": "post",
				"url": "Sensors",
				"body": {
					"@iot.id": frost_id,
					"name": frost_id,
					"description": "Citizen science Black Carbon measurement device",
					"encodingType": "utf-8",
					"metadata": "https://www.bcmeter.org"
				}
			}
		]
	}

	res = requests.post(url, json=sensor) 
	print("bcMeter registered:",res.status_code) 



	observed_properties = {
			"requests": []
			}

		data = [
			{"id": "bcngm3", "name": name_ng, "definition": "https://en.wikipedia.org/wiki/Black_carbon", "description": "Particulate matter < 2.5 μm (aerosol)"},
			{"id": "atn", "name": name_atn, "definition": "Absolute attenuation Sensor / Reference", "description": "Absolute attenuation Sensor / Reference"},
			{"id": "sen", "name": name_sen, "definition": "Sensor Value", "description": "Light emission through loaded filter paper"},
			{"id": "ref", "name": name_ref, "definition": "Reference Value", "description": "Light emission through unloaded filter paper"},
			{"id": "temp", "name": name_temperature, "definition": "Temperature", "description": "Temperature inside the device"},
			{"id": "filter_status", "name": name_filter_status, "definition": "Filter Status", "description": "5 is good, 0 is worst. Change when 3."}

		]

		for datum in data:
			observed_properties["requests"].append({
				"id": datum["id"],
				"atomicityGroup": "group1",
				"method": "post",
				"url": "ObservedProperties",
				"body": {
					"@iot.id": datum["id"],
					"name": datum["name"],
					"definition": datum["definition"],
					"description": datum["description"],
				}
			})
