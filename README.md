# rippled-data

!!!!!! in dev, beware. README may not be fully accurate !!!!!!

Simple python project for access data from rippled. Utilizes [docker-rippled from Wietse Wind](https://github.com/WietseWind/docker-rippled) for testing

## Local Docker
From in the /docker-rippled/go/ dir run...
1. ./build
2. ./up
3. ./status (from another terminal window and once completed_ledgers is not empty)

## Local Data Steps
From in the /src/ dir run...
1. python xrpl-get-account-balances.py -h localhost -p 51234
   1. Once complete it writes a data file to /data
2. python xrpl-data-analysis.py
   1. Reads data file to perform data analysis

## Public Data Steps
From in the /src/ dir run...
1. python xrpl-get-account-balances.py -h s.altnet.rippletest.net -p 51234 -s
   1. Note: This example is with a testnet IP and SSL on
   2. Once complete it writes a data file to /data
2. python xrpl-data-analysis.py
   1. Reads data file to perform data analysis

## Logging
Written to /log dir

## Data
Written to /data dir

