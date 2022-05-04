import pandas as pd
import os

# pd.set_option('display.max_columns', None)  # or 1000
# pd.set_option('display.max_rows', None)  # or 1000
# pd.set_option('display.max_colwidth', None)  # or 199

directory = '../data/test'

df = pd.concat([pd.read_json(f"{directory}/"+x) for x in os.listdir(directory)])
print(df.size/2)

# directory = '../data/test'
# for file in os.listdir(directory):
#     filename = os.path.join(directory, file)
#     if os.path.isfile(filename):
#         print(filename)
#
# df = pd.read_pickle('../data/71247480/11111_ledger.pickle')
# #
# count = 0
# for index, row in df.iterrows():
#     # print(row)
#     # print(index)
#     if pd.notnull(row['Account']) and row['LedgerEntryType'] == 'AccountRoot':
#         count += 1
#         print(row['Account'])
#         print(row['LedgerEntryType'])
#         print(row['Balance'])
#         print(count)


# df.sort_values(by=['balance'], inplace=True, ascending=False)
# df['rank_percent'] = df.balance.rank(pct=True)
# df['rank_number'] = df.balance.rank()
#
# rich_list = [
#     {'rank_max': 100, 'rank_min': 99.99},
#     {'rank_max': 99.99, 'rank_min': 99.9},
#     {'rank_max': 99.9, 'rank_min': 99.8},
#     {'rank_max': 99.8, 'rank_min': 99.5},
#     {'rank_max': 99.5, 'rank_min': 99},
#     {'rank_max': 99, 'rank_min': 98},
#     {'rank_max': 98, 'rank_min': 97},
#     {'rank_max': 97, 'rank_min': 96},
#     {'rank_max': 96, 'rank_min': 95},
#     {'rank_max': 95, 'rank_min': 90}
# ]
#
# for index in range(len(rich_list)):
#     rank_max = rich_list[index]['rank_max'] / 100
#     rank_min = rich_list[index]['rank_min'] / 100
#     df_rank = df[df['rank_percent'].between(rank_min, rank_max, inclusive="both")]
#     print(df_rank.head(2))
#
#     rank_size = df_rank.size
#     balance_min = df_rank["balance"].min()
#     balance_max = df_rank["balance"].max()
#     print(df.size)
#     print(f"Top {rank_max} - {rank_min}: Total Accounts: {rank_size} Balance Range: {balance_min} - {balance_max}")
