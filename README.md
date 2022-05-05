# rippled-data
👷👷👷 Work in progress 👷👷👷

Simple python project for collecting and analyzing data from rippled. Basically was a project to emulate the XRP Rich-List in Python.

Utilizes [docker-rippled from Wietse Wind](https://github.com/WietseWind/docker-rippled) for testing among other approaches because, well, I could not get any to work consistently except AWS.
🙂

## Infrastructure

### Local Docker/Podman
From in the /docker/go/ or /podman/go/ dir run...
1. ```./build```
2. ```./up```
3. ```./status``` (from another terminal window and once completed_ledgers is not empty)

### Local Server (aka running under systemctl)
From in the /server/go/ dir run...
1. ```./build```
2. ```./up```
3. ```./status``` (from another terminal window and once completed_ledgers is not empty)

### AWS
From in the /aws/go/ dir run...
1. ```./up``` (deploys vpc and EC2 instance, including installing rippled service and running it)
2. ```./remote_status``` (to get ledger status)
Jump on the EC2 instance to run other commands, scripts, etc

## Data Collection
Rippled need to have completed_ledgers in the status step above before you can start collecting the data

From in the /src/ dir run...
1. ```python xrpl-rpc-get-ledger-data.py -h s.altnet.rippletest.net -p 51234 -s``` or ```python xrpl-ws-get-ledger-data.py -h s.altnet.rippletest.net -s```
   1. Note: These examples are either RPC or WS with a testnet IP and SSL on. Run ```--help``` for all configuration options
   2. Once complete it writes a data to /data
      1. Ledger details to /data/ledger
      2. Ledger data to /data/ledger-data
   3. Logs, if enabled are written to /log

## Data Analysis
Processing of a full ledger must complete

From in the /src/ dir run...
1. ```python xrpl-ledger-data-analysis.py -l <ledger index>```
   1. Reads data file to perform data analysis
   2. Sample output:
```commandline
#### Ledger Data ####
Ledger: 71432020
Total Coins: 99989514857905488 XRP
Close Time: 2022-May-05 15:03:41.000000000 UTC

#### Account Data ####
Top 100% - 99.99%: Total Accounts: 416 out of 4,168,651 (416 inclusive) Balance Range: 2,677,168,712,244,180 - 7,477,035,025,504 XRP
Top 99.99% - 99.9%: Total Accounts: 4,168 out of 4,168,651 (3,752 inclusive) Balance Range: 7,466,514,497,084 - 421,191,393,194 XRP
Top 99.9% - 99.8%: Total Accounts: 8,337 out of 4,168,651 (4,169 inclusive) Balance Range: 421,142,942,585 - 236,368,994,950 XRP
Top 99.8% - 99.5%: Total Accounts: 20,843 out of 4,168,651 (12,506 inclusive) Balance Range: 236,306,971,075 - 105,720,699,850 XRP
Top 99.5% - 99%: Total Accounts: 41,686 out of 4,168,651 (20,843 inclusive) Balance Range: 105,714,539,666 - 56,026,449,989 XRP
Top 99% - 98%: Total Accounts: 83,373 out of 4,168,651 (41,687 inclusive) Balance Range: 56,025,821,500 - 26,719,678,721 XRP
Top 98% - 97%: Total Accounts: 125,059 out of 4,168,651 (41,686 inclusive) Balance Range: 26,719,623,700 - 16,024,772,989 XRP
Top 97% - 96%: Total Accounts: 166,746 out of 4,168,651 (41,687 inclusive) Balance Range: 16,024,636,724 - 10,485,237,248 XRP
Top 96% - 95%: Total Accounts: 208,432 out of 4,168,651 (41,686 inclusive) Balance Range: 10,485,134,425 - 7,887,900,000 XRP
Top 95% - 90%: Total Accounts: 416,865 out of 4,168,651 (208,433 inclusive) Balance Range: 7,887,831,194 - 2,020,249,985 XRP
```

