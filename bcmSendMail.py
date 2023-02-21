#this file is not implemented yet in interface and has to be called manually if you want to have bcMeter send the logs to you by mail. 

import smtplib, ssl
from email.mime.multipart import MIMEMultipart 
from email.mime.text import MIMEText 
from email.mime.application import MIMEApplication
import os
from time import sleep

smtp_server = '' #smtp server, for example smtp.gmail.com
smtp_port = 587
#Replace with your own gmail account. do NOT share _this_ file with anybody. 
gmail = ''
password = ''

mail_interval = 1800 #how often (seconds) send the mail. 1hr = 3600

while True:

	message = MIMEMultipart('mixed')
	message['From'] = os.uname()[1] + ' <{sender}>'.format(sender = gmail)
	message['To'] = '' #replace with receipents mail address(es)
	#message['CC'] = ''
	message['Subject'] = os.uname()[1] + " log" #subject of mail 

	to= message['To']
	cc= message['CC']

	msg_content = 'Find current log attached'
	body = MIMEText(msg_content, 'html')
	message.attach(body)


	attachmentPath = "/home/pi/logs/log_current.csv"
	try:
		with open(attachmentPath, "rb") as attachment:
			p = MIMEApplication(attachment.read(),_subtype="csv")	
			p.add_header('Content-Disposition', "attachment; filename= %s" % attachmentPath.split("/")[-1]) 
			message.attach(p)
	except Exception as e:
		print(str(e))

	msg_full = message.as_string()

	context = ssl.create_default_context()

	with smtplib.SMTP(smtp_server, smtp_port) as server:
		server.ehlo()  
		server.starttls(context=context)
		server.ehlo()
		server.login(gmail, password)
		server.sendmail(gmail, to.split(";") + (cc.split(";") if cc else []), msg_full)
		server.quit()

	print("email sent out successfully")
	sleep(mail_interval)


