run_hotspot =False#Hotspot Mode: 'True' for continouus operation, 'False' to turn off after 10 Minutes
sample_time=300 #Time in seconds between to samples. 
sample_count = 7000 #This many samples are take for each datapoint. 
airflow_per_minute=0.180 #Airflow per minute in liter
filter_scattering_factor = 1.3 #Scattering of Filter. 1.3 for magee ae33, 1.66 for pallflex t60a20 in aethlabs maeth51
device_specific_correction_factor = 1 #Device specific correction factor (Tube, other Filter, ...)
pump_dutycycle=22 #Power 0-100 for the pump
swap_channels =False#Swap data channels if you see continous negative values or on Rev 2 bcMeters. 
compair_upload =False#Upload Data to CompAIR. Needs coordinates. 
get_location =False#Get rough location by IP? False: Need to enter Manually below.
location=[00.0000, 00.0000]#Location of the bcMeter. Keep syntax exactly like that [lat,lon] and keep above value to False