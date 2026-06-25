# Fish-Tank-Friend (Ditributed Version)
Automatically feeds for my fish tank.
Connect multiple Pi's together from different locations and control the feeds from one location.

# File structure
## On Rasperry Pi Zeros
<code>mkdir /home/pi/feeder</code>  
├── feed.cpp            ← your source (upload it here)  
├── feed                ← compiled binary:  g++ feed.cpp -o feed -lwiringPi -lm  
├── server.py           ← the Flask API server  
├── feeder_config.json  ← auto-created on first run  
├── feed_log.json       ← auto-created on first run  
├── feeder_token.txt    ← auto-created on first run (holds the auth token)  
└── aquafeed_ui.html    ← hosted by the Pi 

<code>mkdir -p /home/pi/feeder/ui</code>  
<code>cp aquafeed_ui.html /home/pi/feeder/ui/index.html</code>  
Portect the exposed file by putting it in its own folder. Name it index.html to make it shorter to type.

/etc/systemd/system/aquafeed.service   ← copied via: sudo cp aquafeed.service  
/etc/systemd/system/  

# Setup:
## Install libraries
<code>sudo apt update</code>  
<strong>build essential</strong>  
<code>sudo apt install -y build-essential git</code>  
<strong>Maintained WiringPi (GC2 fork) — build from source</strong>  
<code>git clone https://github.com/WiringPi/WiringPi.git</code>  
<code>cd WiringPi</code>  
<code>./build</code>  
<code>gpio -v          # should report version 3.x</code>  
<code>cd ~</code>  
<strong>flask</strong>  
<code>pip install flask flask-cors</code>  

## Compile the feeder
<code>cd /home/pi/feeder</code>  
<code>g++ feed.cpp -o feed -lwiringPi -lm</code>  

## Test stepper motor setup
<code>./feed --angle 90</code>  

## Install service
<code>cd /home/pi/feeder</code>  
<code>python3 server.py    # Should print the auth token. Copy it. Then stop with Ctrl-C</code>  
<code>sudo cp aquafeed.service /etc/systemd/system/</code>  
<code>sudo systemctl enable aquafeed</code>  
<code>sudo systemctl start aquafeed</code>  

## Grab Token
<code>cat /home/pi/feeder/feeder_token.txt</code>  

## Set up GUI hosting on Pi
<code>cd /home/pi/feeder</code>  
<code>python3 -m http.server 8080</code>  

## Open on browser
http://tank-office.local:8080/  
or  
http://192.168.1.50:8080/   
(use <code>hostname -I</code> to find ip of Pi)
