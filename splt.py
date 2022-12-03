import pandas as pd

df = pd.read_csv("./chunk_bogdan.csv")
n = df.shape[0] // 2

df.iloc[:n].to_csv("./chunk_bogdan1.csv")
df.iloc[n:].to_csv("./chunk_bogdan2.csv")
