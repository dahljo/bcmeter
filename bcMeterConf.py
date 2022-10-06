#parameters for calculation of bc
sample_time=300 #time in seconds between samples. always keep above the necessary time to take the samples (1000 samples in 35 seconds)
sample_count = 2000 #datapoints to sample and use their average. 
airflow_per_minute=0.63 #airflow_per_minute per minute in liter
filter_scattering_factor = 1.3 #filter specific scattering for black carbon. 1.3 for magee ae33, 1.66 for pallflex t60a20 in aethlabs maeth51
device_specific_correction_factor = 0.5 #device specific calibration factor (mismatching spotarea size, length of tube).
