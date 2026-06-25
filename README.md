# Fish-Tank-Friend (Ditributed Version)
Automatically feeds for my fish tank.
Connect multiple Pi's together from different locations and control the feeds from one location.

# Setup:
## Build tools
<code>sudo apt update</code>  
<code>sudo apt install -y build-essential git</code>  

## Maintained WiringPi (GC2 fork) — build from source
<code>git clone https://github.com/WiringPi/WiringPi.git</code>  
<code>cd WiringPi</code>  
<code>./build</code>  
<code>gpio -v          # should report version 3.x</code>  
<code>cd ~</code>  


## Create the file structure
<code>mkdir /home/pi/feeder</code>  

## Compile the feeder
<code>cd /home/pi/feeder</code>  
<code>g++ feed.cpp -o feed -lwiringPi -lm</code>  

## Test stepper motor setup
<code>./feed --angle 90</code>  

## Setup the server
<code>pip install flask flask-cors</code>  
<code>cd /home/pi/feeder</code>  
<code>python3 server.py    # Should print the auth token. Copy it. Then stop with Ctrl-C</code>  
<code>sudo cp aquafeed.service /etc/systemd/system/</code>  
<code>sudo systemctl enable aquafeed</code>  
<code>sudo systemctl start aquafeed</code>  
