import socket
import time

# alternative check -- http/www on port 80 instead of dns on port 53
CONNECTION_TEST_HOST = "www.google.com" 
CONNECTION_TEST_PORT = 80
CONNECTION_TEST_TIMEOUT = 3     # socket timeout
CONNECTION_TEST_TRIES = 3       # number of attemps
CONNECTION_TEST_RETRY_SLEEP = 2 # in seconds

def check_connection():
	
	for _ in range(CONNECTION_TEST_TRIES):
		try:
			# Attempt to create a socket connection to the test host
			s=socket.create_connection((CONNECTION_TEST_HOST, CONNECTION_TEST_PORT), timeout=CONNECTION_TEST_TIMEOUT)
			s.close()
			return True			
		except OSError:
			time.sleep(CONNECTION_TEST_RETRY_SLEEP)
			
	return False

print(check_connection())