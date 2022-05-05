import pandas as pd
import os
import click


@click.command()
@click.option('-l', '--ledger', required=True, help='Ledger number')
def process(ledger):
    ledger_data_directory = f'../data/{ledger}/ledger-data/'
    ledger_directory = f'../data/{ledger}/ledger/'

    data_df = pd.concat([pd.read_json(f"{ledger_data_directory}/" + x) for x in os.listdir(ledger_data_directory)])
    # print(len(data_df.index))
    ledger_df = pd.read_json(f"{ledger_directory}/ledger.json")
    # print(ledger_df)
    print(f"#### Ledger Data ####\nLedger: {ledger}\nTotal Coins: {ledger_df.iloc[0]['total_coins']} XRP\n"
          f"Close Time: {ledger_df.iloc[0]['close_time_human']}\n\n#### Account Data ####")

    data_df.sort_values(by=['balance'], inplace=True, ascending=False)
    data_df['rank_number'] = data_df.balance.rank()
    data_df['rank_percent'] = data_df.rank_number.rank(pct=True)

    rich_list = [
        {'rank_max': 100, 'rank_min': 99.99},
        {'rank_max': 99.99, 'rank_min': 99.90},
        {'rank_max': 99.9, 'rank_min': 99.8},
        {'rank_max': 99.8, 'rank_min': 99.5},
        {'rank_max': 99.5, 'rank_min': 99},
        {'rank_max': 99, 'rank_min': 98},
        {'rank_max': 98, 'rank_min': 97},
        {'rank_max': 97, 'rank_min': 96},
        {'rank_max': 96, 'rank_min': 95},
        {'rank_max': 95, 'rank_min': 90}
    ]

    for index in range(len(rich_list)):
        rank_max_dec = rich_list[index]['rank_max'] / 100
        rank_min_dec = rich_list[index]['rank_min'] / 100
        rank_max_prct = rich_list[index]['rank_max']
        rank_min_prct = rich_list[index]['rank_min']
        df_rank_inclusive = data_df[data_df['rank_percent'].between(rank_min_dec, rank_max_dec, inclusive="left")]
        df_rank_total = data_df[data_df['rank_percent'].between(rank_min_dec, 1.0, inclusive="left")]

        rank_size_inclusive = "{:,}".format(len(df_rank_inclusive.index))
        rank_size_total = "{:,}".format(len(df_rank_total.index))
        balance_min = "{:,}".format(df_rank_inclusive["balance"].min())
        balance_max = "{:,}".format(df_rank_inclusive["balance"].max())
        total_size = "{:,}".format(len(data_df.index))
        print(f"Top {rank_max_prct}% - {rank_min_prct}%: "
              f"Total Accounts: {rank_size_total} out of {total_size} ({rank_size_inclusive} inclusive) "
              f"Balance Range: {balance_max} - {balance_min} XRP")


if __name__ == '__main__':
    process()
