# Utilization analysis script for Jefferson County EMS report.
import pandas as pd
import numpy as np

xl = pd.ExcelFile('ISyE Project/Comparison Output/county_ems_comparison_data.xlsx')
muni_kpi = xl.parse('Jeff_Municipal_Breakdown')
rt_pct = xl.parse('Jeff_Response_Percentiles')

# Normalize names
muni_kpi['Municipality'] = muni_kpi['Municipality'].replace({'Edgerton (Lakeside)': 'Edgerton'})
rt_pct['Municipality']   = rt_pct['Municipality'].replace({'Edgerton (Lakeside)': 'Edgerton'})

call_data = muni_kpi[['Municipality', 'Total Calls', 'EMS Calls (Cat 3)']].copy()
call_data.columns = ['Municipality', 'Total_Calls', 'EMS_Calls']

budget = pd.DataFrame([
    {'Municipality': 'Ixonia',        'FY': 2024, 'Total_Expense': 631144,  'EMS_Revenue': 125000.0, 'Net_Tax': 151263.0, 'Model': 'Volunteer+FT', 'Staff_FT': 2,  'Staff_PT': 45.0},
    {'Municipality': 'Jefferson',     'FY': 2025, 'Total_Expense': 1500300, 'EMS_Revenue': 732000.0, 'Net_Tax': 144300.0, 'Model': 'Career',       'Staff_FT': 6,  'Staff_PT': 20.0},
    {'Municipality': 'Watertown',     'FY': 2025, 'Total_Expense': 3833800, 'EMS_Revenue': 817000.0, 'Net_Tax': 2947719.0,'Model': 'Career',       'Staff_FT': 31, 'Staff_PT': 3.0},
    {'Municipality': 'Fort Atkinson', 'FY': 2025, 'Total_Expense': 760950,  'EMS_Revenue': 713850.0, 'Net_Tax': 0.0,      'Model': 'Career+PT',    'Staff_FT': 16, 'Staff_PT': 28.0},
    {'Municipality': 'Whitewater',    'FY': 2025, 'Total_Expense': 2710609, 'EMS_Revenue': 625000.0, 'Net_Tax': 1370114.0,'Model': 'Career+PT',    'Staff_FT': 15, 'Staff_PT': 17.0},
    {'Municipality': 'Cambridge',     'FY': 2025, 'Total_Expense': 92000,   'EMS_Revenue': 0.0,      'Net_Tax': 92000.0,  'Model': 'Volunteer',    'Staff_FT': 0,  'Staff_PT': 31.0},
    {'Municipality': 'Lake Mills',    'FY': 2025, 'Total_Expense': 347000,  'EMS_Revenue': 8000.0,   'Net_Tax': 347000.0, 'Model': 'Career+Vol',   'Staff_FT': 4,  'Staff_PT': 20.0},
    {'Municipality': 'Waterloo',      'FY': 2025, 'Total_Expense': 1102475, 'EMS_Revenue': 200000.0, 'Net_Tax': 557475.0, 'Model': 'Career+Vol',   'Staff_FT': 3,  'Staff_PT': 15.0},
    {'Municipality': 'Johnson Creek', 'FY': 2025, 'Total_Expense': 1134154, 'EMS_Revenue': 288600.0, 'Net_Tax': 472352.0, 'Model': 'Volunteer',    'Staff_FT': 3,  'Staff_PT': 40.0},
    {'Municipality': 'Palmyra',       'FY': 2025, 'Total_Expense': 817740,  'EMS_Revenue': 140000.0, 'Net_Tax': 502791.0, 'Model': 'Volunteer',    'Staff_FT': 0,  'Staff_PT': 20.0},
    {'Municipality': 'Edgerton',      'FY': 2025, 'Total_Expense': 704977,  'EMS_Revenue': None,     'Net_Tax': None,     'Model': 'Career+PT',    'Staff_FT': 24, 'Staff_PT': None},
])

ALS_LEVELS = {
    'Watertown': 'ALS', 'Fort Atkinson': 'ALS', 'Whitewater': 'ALS',
    'Jefferson': 'ALS', 'Johnson Creek': 'ALS', 'Edgerton': 'ALS',
    'Cambridge': 'ALS', 'Waterloo': 'AEMT', 'Palmyra': 'BLS',
    'Ixonia': 'BLS', 'Helenville': 'BLS', 'Lake Mills': 'BLS',
    'Western Lakes': 'ALS',
}

df = budget.merge(call_data, on='Municipality', how='left')
df['ALS_Level']   = df['Municipality'].map(ALS_LEVELS)
df['Total_Staff'] = df['Staff_FT'].fillna(0) + df['Staff_PT'].fillna(0)

df['Cost_Per_Call']              = (df['Total_Expense'] / df['Total_Calls']).round(0)
df['Cost_Per_EMS_Call']          = (df['Total_Expense'] / df['EMS_Calls']).round(0)
df['Revenue_Recovery']           = (df['EMS_Revenue'] / df['Total_Expense'] * 100).round(1)
df['EMS_Calls_per_FT']           = (df['EMS_Calls'] / df['Staff_FT'].replace(0, np.nan)).round(0)
df['EMS_Calls_per_Total_Staff']  = (df['EMS_Calls'] / df['Total_Staff'].replace(0, np.nan)).round(1)
df['Tax_Subsidy_Per_Call']       = (df['Net_Tax'] / df['Total_Calls']).round(0)
df['Tax_Subsidy_Per_EMS_Call']   = (df['Net_Tax'] / df['EMS_Calls']).round(0)

sep = '-' * 100

print('\n' + sep)
print('TABLE 1: Cost-Per-Call (Total_Expense / Total_Calls) -- Ranked Most Efficient to Least')
print(sep)
t1 = df[['Municipality','ALS_Level','Model','Total_Calls','Total_Expense','Cost_Per_Call']].dropna(subset=['Cost_Per_Call']).sort_values('Cost_Per_Call')
print(f"{'Rank':<5} {'Municipality':<15} {'ALS':<6} {'Model':<15} {'Calls':>7} {'Expense':>12} {'$/Call':>9}")
for i, r in enumerate(t1.itertuples(), 1):
    print(f"{i:<5} {r.Municipality:<15} {r.ALS_Level:<6} {r.Model:<15} {r.Total_Calls:>7,.0f} ${r.Total_Expense:>11,.0f} ${r.Cost_Per_Call:>8,.0f}")

print('\n' + sep)
print('TABLE 2: Revenue Recovery Rate (EMS_Revenue / Total_Expense) -- Ranked Highest to Lowest')
print(sep)
t2 = df[['Municipality','ALS_Level','Model','Total_Expense','EMS_Revenue','Revenue_Recovery']].dropna(subset=['Revenue_Recovery']).sort_values('Revenue_Recovery', ascending=False)
print(f"{'Rank':<5} {'Municipality':<15} {'ALS':<6} {'Model':<15} {'Expense':>12} {'EMS_Rev':>10} {'Recovery':>10}")
for i, r in enumerate(t2.itertuples(), 1):
    print(f"{i:<5} {r.Municipality:<15} {r.ALS_Level:<6} {r.Model:<15} ${r.Total_Expense:>11,.0f} ${r.EMS_Revenue:>9,.0f} {r.Revenue_Recovery:>9.1f}%")

print('\n' + sep)
print('TABLE 3: EMS Calls per FT Staff -- Ranked Highest (most productive) to Lowest')
print(sep)
t3 = df[['Municipality','ALS_Level','Model','EMS_Calls','Staff_FT','EMS_Calls_per_FT']].dropna(subset=['EMS_Calls_per_FT']).sort_values('EMS_Calls_per_FT', ascending=False)
print(f"{'Rank':<5} {'Municipality':<15} {'ALS':<6} {'Model':<15} {'EMS_Calls':>10} {'FT_Staff':>9} {'Calls/FT':>9}")
for i, r in enumerate(t3.itertuples(), 1):
    print(f"{i:<5} {r.Municipality:<15} {r.ALS_Level:<6} {r.Model:<15} {r.EMS_Calls:>10,.0f} {r.Staff_FT:>9,.0f} {r.EMS_Calls_per_FT:>9,.0f}")

print('\n' + sep)
print('TABLE 4: Tax Subsidy Per Call (Net_Tax / Total_Calls) -- Ranked Lowest to Highest')
print(sep)
t4 = df[['Municipality','ALS_Level','Model','Total_Calls','Net_Tax','Tax_Subsidy_Per_Call']].dropna(subset=['Tax_Subsidy_Per_Call']).sort_values('Tax_Subsidy_Per_Call')
print(f"{'Rank':<5} {'Municipality':<15} {'ALS':<6} {'Model':<15} {'Calls':>7} {'Net_Tax':>12} {'Tax/Call':>10}")
for i, r in enumerate(t4.itertuples(), 1):
    print(f"{i:<5} {r.Municipality:<15} {r.ALS_Level:<6} {r.Model:<15} {r.Total_Calls:>7,.0f} ${r.Net_Tax:>11,.0f} ${r.Tax_Subsidy_Per_Call:>9,.0f}")

print('\n' + sep)
print('TABLE 5: EMS Calls per Total Staff (FT+PT combined)')
print(sep)
t5 = df[['Municipality','ALS_Level','Model','EMS_Calls','Total_Staff','EMS_Calls_per_Total_Staff']].dropna(subset=['EMS_Calls_per_Total_Staff']).sort_values('EMS_Calls_per_Total_Staff', ascending=False)
print(f"{'Rank':<5} {'Municipality':<15} {'ALS':<6} {'Model':<15} {'EMS_Calls':>10} {'TotalStaff':>11} {'Calls/Staff':>12}")
for i, r in enumerate(t5.itertuples(), 1):
    print(f"{i:<5} {r.Municipality:<15} {r.ALS_Level:<6} {r.Model:<15} {r.EMS_Calls:>10,.0f} {r.Total_Staff:>11,.0f} {r.EMS_Calls_per_Total_Staff:>12.1f}")

print('\n' + sep)
print('FULL UTILIZATION MATRIX -- All Departments')
print(sep)
cols = ['Municipality','ALS_Level','Model','Total_Calls','EMS_Calls','Total_Expense','EMS_Revenue',
        'Net_Tax','Staff_FT','Staff_PT','Cost_Per_Call','Cost_Per_EMS_Call',
        'Revenue_Recovery','Tax_Subsidy_Per_Call','EMS_Calls_per_FT','EMS_Calls_per_Total_Staff']
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 300)
pd.set_option('display.float_format', '{:.0f}'.format)
print(df[cols].to_string(index=False))

# Model-level summary
print('\n' + sep)
print('MODEL EFFICIENCY SUMMARY (averages by staffing model, excluding Edgerton partial data)')
print(sep)
df_model = df[df['Municipality'] != 'Edgerton'].dropna(subset=['Cost_Per_Call','Revenue_Recovery'])
model_grp = df_model.groupby('Model').agg(
    Depts=('Municipality', 'count'),
    Avg_Cost_Per_Call=('Cost_Per_Call', 'mean'),
    Avg_Revenue_Recovery=('Revenue_Recovery', 'mean'),
    Avg_Tax_Subsidy_Per_Call=('Tax_Subsidy_Per_Call', 'mean'),
    Total_EMS_Calls=('EMS_Calls', 'sum'),
    Total_Expense=('Total_Expense', 'sum'),
).reset_index().sort_values('Avg_Cost_Per_Call')
print(f"{'Model':<15} {'N':>3} {'AvgCost/Call':>13} {'AvgRevRecov':>12} {'AvgTax/Call':>12} {'TotalEMS':>10} {'TotalExp':>13}")
for r in model_grp.itertuples():
    print(f"{r.Model:<15} {r.Depts:>3} ${r.Avg_Cost_Per_Call:>11,.0f} {r.Avg_Revenue_Recovery:>11.1f}% ${r.Avg_Tax_Subsidy_Per_Call:>10,.0f} {r.Total_EMS_Calls:>10,.0f} ${r.Total_Expense:>12,.0f}")

# Outlier detection
print('\n' + sep)
print('OUTLIER FLAGS -- Departments flagged on 2+ metrics')
print(sep)
df_flag = df[df['Municipality'] != 'Edgerton'].copy()
# Cost outlier: >2x median cost_per_call
med_cpc = df_flag['Cost_Per_Call'].median()
# Revenue recovery outlier: < 15%
# Tax subsidy outlier: > 1000/call
# Calls/FT outlier: < 30 or > 300 where FT > 0
df_flag['flag_high_cost']    = df_flag['Cost_Per_Call'] > (med_cpc * 2)
df_flag['flag_low_recovery'] = df_flag['Revenue_Recovery'] < 15
df_flag['flag_high_tax']     = df_flag['Tax_Subsidy_Per_Call'] > 1000
df_flag['flag_low_calls']    = df_flag['Total_Calls'] < 100
df_flag['flag_count']        = (df_flag[['flag_high_cost','flag_low_recovery','flag_high_tax','flag_low_calls']].astype(int)).sum(axis=1)
outliers = df_flag[df_flag['flag_count'] >= 2].sort_values('flag_count', ascending=False)
print(f"{'Dept':<15} {'Flags':>6} {'HighCost':>9} {'LowRev':>7} {'HighTax':>8} {'LowVol':>7} {'Cost/Call':>10} {'RevRecov':>9} {'Tax/Call':>10} {'TotalCalls':>11}")
for r in outliers.itertuples():
    print(f"{r.Municipality:<15} {r.flag_count:>6} {str(r.flag_high_cost):>9} {str(r.flag_low_recovery):>7} {str(r.flag_high_tax):>8} {str(r.flag_low_calls):>7} ${r.Cost_Per_Call:>9,.0f} {r.Revenue_Recovery:>8.1f}% ${r.Tax_Subsidy_Per_Call:>9,.0f} {r.Total_Calls:>11,.0f}")

print('\nMedian cost/call across all depts:', f'${med_cpc:,.0f}')
print('Done.')
