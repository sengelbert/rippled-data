#!/bin/bash -xe

####### Start Ubuntu 20.04 #######

sudo apt -y update
sudo apt -y install apt-transport-https ca-certificates wget gnupg
wget -q -O - "https://repos.ripple.com/repos/api/gpg/key/public" | sudo apt-key add -
apt-key finger
echo "deb https://repos.ripple.com/repos/rippled-deb focal stable" | sudo tee -a /etc/apt/sources.list.d/ripple.list

sudo apt -y update
sudo apt -y install rippled

sudo setcap 'cap_net_bind_service=+ep' /opt/ripple/bin/rippled

####### End Ubuntu 20.04 #######

######## Start RHL / AL2 #######
#
#cat << REPOFILE | sudo tee /etc/yum.repos.d/ripple.repo
#[ripple-stable]
#name=XRP Ledger Packages
#enabled=1
#gpgcheck=0
#repo_gpgcheck=1
#baseurl=https://repos.ripple.com/repos/rippled-rpm/stable/
#gpgkey=https://repos.ripple.com/repos/rippled-rpm/stable/repodata/repomd.xml.key
#REPOFILE
#
#sudo yum -y update
#sudo yum install -y rippled
#
######## Stop RHL / AL2 #######

######## Start Set Configs #######

sudo cp /etc/opt/ripple/rippled.cfg /etc/opt/ripple/rippled-original.cfg

cat << CONFIG | sudo tee /etc/opt/ripple/rippled.cfg
[server]
port_rpc_admin_local
port_rpc_public
port_peer
port_ws_admin_local
port_ws_public

[port_rpc_admin_local]
port = 5005
ip = 127.0.0.1
admin = 127.0.0.1
protocol = http

[port_rpc_public]
port = 51234
ip = 0.0.0.0
protocol = http

[port_peer]
port = 51235
ip = 0.0.0.0
protocol = peer

[port_ws_admin_local]
port = 6006
ip = 127.0.0.1
admin = 127.0.0.1
protocol = ws

[port_ws_public]
port = 6005
ip = 0.0.0.0
protocol = ws

[node_size]
small

[ledger_history]
512

[node_db]
type=NuDB
path=/var/lib/rippled/db/nudb
online_delete=512
advisory_delete=1

[database_path]
/var/lib/rippled/db

[debug_logfile]
/var/log/rippled/debug.log

[sntp_servers]
time.windows.com
time.apple.com
time.nist.gov
pool.ntp.org

[ips]
r.ripple.com 51235

[validators_file]
validators.txt

[rpc_startup]
{ "command": "log_level", "severity": "warning" }

[ssl_verify]
1

CONFIG

######## Stop Set Configs #######

######## Start Start Service #######

sudo systemctl daemon-reload
sudo systemctl enable rippled.service
sudo systemctl start rippled.service
sudo systemctl status rippled.service --no-pager

######## Stop Start Service #######

######## Start Setup Python #######

#sudo yum update -y
#sudo yum groupinstall "Development Tools" -y
#sudo yum install openssl11 openssl11-devel libffi-devel bzip2-devel wget python3.8 pip -y

sudo apt install python3-pip -y

pip install pandas click datetime

######## Stop Setup Python #######
