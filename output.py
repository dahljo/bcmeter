#!/usr/bin/env python3
import os
os.chdir('/home/pi')
import csv
from tabulate import tabulate
from time import sleep, strftime, time

try:
	while True:
		print('\x1b[2J')
		headers=[]
		with open('logs/current.csv','r') as csv_file:
			csv_reader = list(csv.reader(csv_file, delimiter=';'))
			print(tabulate(csv_reader, headers, tablefmt="fancy_grid"))
			print("You may always go to terminal by pressing ctrl + c (measurement continues in backgound)")
		sleep(120)
except KeyboardInterrupt: 
	#traceback.print_exc()
	print("\nWhen ready again, you may restart the script with 'python3 output.py'")
	pass
