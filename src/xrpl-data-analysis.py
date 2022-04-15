import pandas as pd

df = pd.read_pickle('../data/account_balances.pickle')

# print(df)
print(df.describe())
print(df.size)
# print(df["balance"].mean())
# print(df.count())