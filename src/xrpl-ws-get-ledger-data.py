import json
import click
import datetime
import os

from xrpl.models import LedgerData
from xrpl.clients import WebsocketClient
from xrpl.ledger import get_latest_validated_ledger_sequence


@click.command()
@click.option('-h', '--host', default='127.0.0.1', help='JSON RPC Host')
@click.option('-p', '--port', default='51234', help='JSON RPC Host Port')
@click.option('-a', '--api_limit', default=20000, help='API Pagination Limit')
@click.option('-d', '--debug', is_flag=True, help='Setup Debugging Output')
@click.option('-s', '--ssl', is_flag=True, help='Use SSL or not')
@click.option('-c', '--ledger_count', default=1, help='how many ledgers to collect')
@click.option('-l', '--logging', is_flag=True, help='Log?')
def process(host, port, api_limit, debug, ssl, ledger_count, logging):
    # set some variables
    record_count = 0
    call_count = 0
    paginate = True
    marker_val = None
    debug_prefix = "DEBUG: "

    print(f"{debug_prefix}debug is on") if debug else None
    # create a network client
    is_ssl = 'wss' if ssl else 'ws'
    connection_string = f"{is_ssl}://{host}"
    print(f"{debug_prefix}connecting to {connection_string}") if debug else None
    # https://s.altnet.rippletest.net  #testnet
    # https://r.ripple.com  # prod

    with WebsocketClient(connection_string) as client:
        ledger = get_latest_validated_ledger_sequence(client)
        os.makedirs(f'../data/{ledger}/', exist_ok=True)
        os.makedirs(f'../data/{ledger}/ledger-data/', exist_ok=True)
        os.makedirs(f'../data/{ledger}/ledger/', exist_ok=True)
        # log to loggy
        log = open(f'../log/{ledger}_loggy.log', 'w') if logging else None
        while paginate:
            if marker_val is None:
                print(f"{debug_prefix}marker is empty") if debug else None
                ledger_result = client.request(LedgerData(ledger_index=ledger, limit=int(api_limit)))
            else:
                print(f"{debug_prefix}marker NOT is empty") if debug else None
                ledger_result = client.request(LedgerData(ledger_index=ledger, marker=marker_val, limit=int(api_limit)))

            ledger_result = ledger_result.result
            # print(f"{debug_prefix}{ledger_result}") if debug else None
            if call_count == 0:
                ledger_data = open(f'../data/{ledger}/ledger/ledger.json', 'w')
                ledger_data.write(json.dumps([ledger_result["ledger"]]))
            account_list = []
            call_count += 1
            # open data file
            data = open(f'../data/{ledger}/ledger-data/{call_count}_account_balances.json', 'w')
            if "marker" in ledger_result:
                last_marker_val = marker_val
                marker_val = ledger_result["marker"]
                print(f"{debug_prefix}Marker: {marker_val}") if debug else None
            else:
                last_marker_val = marker_val
                marker_val = None
                paginate = False
                print(f"{debug_prefix}last call") if debug else None
            print(
                f"{debug_prefix}current marker: {last_marker_val} next marker: {marker_val} "
                f"total record count: {record_count} total "
                f"api call count: {call_count}") if debug else None

            for acct in ledger_result["state"]:
                if acct["LedgerEntryType"] == "AccountRoot":
                    record_count += 1
                    result = {"account": acct["Account"], "balance": acct["Balance"]}
                    account_list.append(result)
                    print(
                        f"{debug_prefix}ledger: {ledger} account: {acct['Account']} "
                        f"type: {acct['LedgerEntryType']} "
                        f"balance: {acct['Balance']} count: {record_count}") \
                        if debug else None
            data.write(json.dumps(account_list))
            log.write(
                f"date: {datetime.datetime.now()} ledger: {ledger} current marker: {last_marker_val} "
                f"next marker: {marker_val} total record count: "
                f"{record_count} "
                f"total api call count: {call_count}\n") if logging else None
            print(f"ledger: {ledger} account count: {record_count} "
                  f"total api call count: {call_count}") if not logging else None


if __name__ == '__main__':
    process()
