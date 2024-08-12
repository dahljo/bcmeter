## Thank you for your interest! In this git you find everything you need to build your own bcMeter for non-commercial use as a citizen science device. for commercial use and licencing please contact jd@bcmeter.org.


## Recommended software setup:
download bcMeter.img from https://bcmeter.org and clone that to a microSD card - change WiFi credentials within bcMeters hotspot mode and you're ready. 

## manual software setup:

see https://bcmeter.org/wiki/index.php?title=Installation#Alternative:_Manual_Set_Up_the_microSD_Card for instructions, the basic procedure is:

1. write raspberry LITE(!) image to micro sd card with the help of the imager (https://www.raspberrypi.com/news/raspberry-pi-imager-imaging-utility/) - use the imager to configure SSH and WiFi BEFORE starting the write process!
2. bootup raspberry pi and log into it via ssh, download and run install.sh script: 
wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh && sudo bash install.sh
3. run bcMeter script 


### Script / Interface

install.sh is a just a batch to configure the raspberry for the use as bcMeter
bcMeter.py is the python script which saves the data as csv
/interface contains a d3.js interface for reading out the csv file



### Gerber for PCB Manufactoring

in /gerbers you'll find the gerbers for PCB manufactoring. 

### STL files for 3D Printing

in /stl you find the files for 3d printing. the large case is intended to be used for large internal pumps. the small case is recommended and more flexibile


![bcMeter-smallCase](https://user-images.githubusercontent.com/87074315/152612250-c9c2e578-1b18-46d1-ad44-5a189bbf04da.png)
![bcMeter-5V](https://user-images.githubusercontent.com/87074315/152612590-75ef60a8-828f-4d69-82bb-b6b03c55a555.png)
