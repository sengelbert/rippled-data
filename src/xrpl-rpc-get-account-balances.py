import json
import pandas as pd
import click
import datetime

from xrpl.models import LedgerData
from xrpl.clients import JsonRpcClient
from xrpl.ledger import get_latest_validated_ledger_sequence


@click.command()
@click.option('-h', '--host', default='127.0.0.1', help='JSON RPC Host')
@click.option('-p', '--port', default='51234', help='JSON RPC Host Port')
@click.option('-l', '--api_limit', default=20000, help='API Pagination Limit')
@click.option('-d', '--debug', is_flag=True, help='Setup Debugging Output')
@click.option('-s', '--ssl', is_flag=True, help='Use SSL or not')
@click.option('-c', '--ledger_count', default=1, help='how many ledgers to collect')
def process(host, port, api_limit, debug, ssl, ledger_count):
    # log to loggy
    log = open(f'../log/loggy.log', 'w')

    # set some variables
    record_count = 0
    call_count = 0
    paginate = True
    marker_val = None
    total_df = pd.DataFrame()
    debug_prefix = "DEBUG: "

    print(f"{debug_prefix}debug is on") if debug else None
    # create a network client
    is_ssl = 'https' if ssl else 'http'
    connection_string = f"{is_ssl}://{host}:{port}/"
    print(f"{debug_prefix}connecting to {connection_string}") if debug else None
    client = JsonRpcClient(connection_string)  # local
    # https://s.altnet.rippletest.net:51234/  #testnet
    # https://r.ripple.com:51235/  # prod

    # ledger_info = LedgerData()
    # ledger_response = client.request(ledger_info)
    # ledger_result = ledger_response.result
    # ledger = int(ledger_result["ledger_index"]) - 1
    ledger = get_latest_validated_ledger_sequence(client)
    # print(ledger)

    # loop through API results
    for i in range(ledger_count):
        print(f"{debug_prefix}collecting data from {ledger}") if debug else None
        # need to decrement for multiple ledger loops
        while paginate:
            if marker_val is None:
                print(f"{debug_prefix}marker is empty") if debug else None
                ledger_info = LedgerData(
                    ledger_index=ledger,
                    limit=int(api_limit)
                )
                ledger_response = client.request(ledger_info)
                ledger_result = ledger_response.result
            else:
                print(f"{debug_prefix}marker NOT is empty") if debug else None
                ledger_info = LedgerData(
                    ledger_index=ledger,
                    marker=marker_val,
                    limit=int(api_limit)
                )
                ledger_response = client.request(ledger_info)
                ledger_result = ledger_response.result

            # print(ledger_result)
            print(f"{debug_prefix}{ledger_result}") if debug else None
            account_list = []
            call_count += 1
            if "marker" in ledger_result:
                last_marker_val = marker_val
                marker_val = ledger_result["marker"]
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
                if "Account" in acct:
                    if "LedgerEntryType" in acct:
                        if "Balance" in acct:
                            account = acct["Account"]
                            account_balance = acct["Balance"]
                            account_ledger_entry_type = acct["LedgerEntryType"]
                            if account_ledger_entry_type == "AccountRoot":
                                record_count += 1
                                result = {"account": account, "balance": account_balance}
                                account_list.append(result)
                                print(
                                    f"{debug_prefix}account: {account} type: {account_ledger_entry_type} "
                                    f"count: {record_count}") \
                                    if debug else None
            working_df = pd.read_json(json.dumps(account_list))
            total_df = pd.concat([working_df, total_df], sort=False)
            log.write(
                f"date: {datetime.datetime.now()} ledger: {ledger} current marker: {last_marker_val} "
                f"next marker: {marker_val} total record count: "
                f"{record_count} total df count: {(total_df.size / 2)} "
                f"total api call count: {call_count}\n")
            print(f"{debug_prefix}df count: {total_df.count()} account count: {record_count}") if debug else None
        total_df.to_pickle(f"../data/{ledger}_account_balances.pickle")
        print(f"{debug_prefix} {total_df.describe()}") if debug else None
    ledger -= 1


if __name__ == '__main__':
    process()
