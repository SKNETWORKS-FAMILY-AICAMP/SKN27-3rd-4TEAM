import pandas as pd
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

data_dir = "data"
all_files = sorted(os.listdir(data_dir))
jeonse_files = [f for f in all_files if "전세" in f]
sale_files = [f for f in all_files if "매매" in f]

print(f"전세: {len(jeonse_files)}개 / 매매: {len(sale_files)}개")

# 전세 오피스텔
df = pd.read_csv(os.path.join(data_dir, "2025_전세_오피스텔_서울_종로구.csv"), nrows=2)
print(f"\n=== 전세 오피스텔 컬럼 ===")
for c in df.columns:
    print(f"  {c}: {df[c].iloc[0]}")

# 전세 연립다세대
df2 = pd.read_csv(os.path.join(data_dir, "2025_전세_연립다세대_서울_종로구.csv"), nrows=2)
print(f"\n=== 전세 연립다세대 컬럼 ===")
for c in df2.columns:
    print(f"  {c}: {df2[c].iloc[0]}")

# 매매 오피스텔
df3 = pd.read_csv(os.path.join(data_dir, "2025_매매_오피스텔_서울_종로구.csv"), nrows=2)
print(f"\n=== 매매 오피스텔 컬럼 ===")
for c in df3.columns:
    print(f"  {c}: {df3[c].iloc[0]}")

# 매매 연립다세대
df4 = pd.read_csv(os.path.join(data_dir, "2025_매매_연립다세대_서울_종로구.csv"), nrows=2)
print(f"\n=== 매매 연립다세대 컬럼 ===")
for c in df4.columns:
    print(f"  {c}: {df4[c].iloc[0]}")

# 전체 규모
total_j = sum(len(pd.read_csv(os.path.join(data_dir, f))) for f in jeonse_files)
total_s = sum(len(pd.read_csv(os.path.join(data_dir, f))) for f in sale_files)
print(f"\n전세 총: {total_j:,}건 / 매매 총: {total_s:,}건")
