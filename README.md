# rippled-data

!!!!!! in dev, beware. README may not be fully accurate !!!!!!

Simple python project for collecting and analyzing data from rippled. Basically was a project to emulate the XRP Rich-List in Python.

Utilizes [docker-rippled from Wietse Wind](https://github.com/WietseWind/docker-rippled) for testing among other approaches because, well, I could not get any to work great except AWS.
🙂

## Infrastructure

### Local Docker/Podman
From in the /docker/go/ or /podman/go/ dir run...
1. ./build
2. ./up
3. ./status (from another terminal window and once completed_ledgers is not empty)

### Local Server (aka running under systemctl)
From in the /server/go/ dir run...
1. ./build
2. ./up
3. ./status (from another terminal window and once completed_ledgers is not empty)

### AWS
From in the /aws/go/ dir run...
1. ./up (deploys vpc and EC2 instance, including installing rippled service and running it)
2. ./remote_status (to get ledger status)
Jump on the EC2 instance to run other commands, scripts, etc

## Data Processing
Rippled need to have completed_ledgers in the status step above before you can start collecting the data

### Local Data Steps
From in the /src/ dir run...
1. python ```xrpl-rpc-get-account-balances.py -h localhost -p 51234``` or ```xrpl-ws-get-account-balances.py -h localhost -p 51234```
   1. Once complete it writes a data file to /data
2. python xrpl-data-analysis.py
   1. Reads data file to perform data analysis

### Public Data Steps
From in the /src/ dir run...
1. ```python xrpl-rpc-get-account-balances.py -h s.altnet.rippletest.net -p 51234 -s``` or ```python xrpl-ws-get-account-balances.py -h s.altnet.rippletest.net -p 51234 -s```
   1. Note: These examples are either RPC or WS with a testnet IP and SSL on. Run ```--help``` for all configuration options
   2. Once complete it writes a data file to /data
3. python xrpl-data-analysis.py
   1. Reads data file to perform data analysis

### Logging
Written to /log dir

### Data
Written to /data dir

