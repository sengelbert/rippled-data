import json
import pandas as pd
import click
import datetime

from xrpl.models import LedgerData
from xrpl.clients import JsonRpcClient


@click.command()
@click.option('-h', '--host', default='127.0.0.1', help='JSON RPC Host')
@click.option('-p', '--port', default='51234', help='JSON RPC Host Port')
@click.option('-l', '--api_limit', default=20000, help='API Pagination Limit')
@click.option('-d', '--debug', is_flag=True, help='Setup Debugging Output')
@click.option('-s', '--ssl', is_flag=True, help='Use SSL or not')
def process(host, port, api_limit, debug, ssl):
    # log to sample
    log = open(f'../log/sample.log', 'w')

    debug_prefix = "DEBUG: "

    print(f"{debug_prefix}debug is on") if debug else None
    # create a network client
    is_ssl = 'https' if ssl else 'http'
    connection_string = f"{is_ssl}://{host}:{port}/"
    print(f"{debug_prefix}connecting to {connection_string}") if debug else None
    client = JsonRpcClient(connection_string)  # local
    # https://s.altnet.rippletest.net:51234/  #testnet
    # https://r.ripple.com:51235/  # prod

    ledger_info = LedgerData(
        ledger_index=71010651,
        limit=int(api_limit)
    )
    ledger_response = client.request(ledger_info)
    ledger_result = ledger_response.result
    json_sample = json.dumps(ledger_result, indent=2)
    print(json_sample)
    log.write(json_sample)


if __name__ == '__main__':
    process()
