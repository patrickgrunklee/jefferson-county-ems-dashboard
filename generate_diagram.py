"""
Generates a visual diagram of Jefferson County Fire & EMS service agreements.

This script uses the Graphviz library to create a PNG image file showing the
relationships between service providers and the municipalities they serve,
highlighting the different payment models with colors.

Requirements:
1. Python package: pip install graphviz
2. System software: Install Graphviz from https://graphviz.org/download/
"""

import os
import graphviz

# --- Add Graphviz to the system's PATH for this script's execution ---
# This is a workaround for when Graphviz is not in the system's PATH.
# It assumes a default installation location for Graphviz on Windows.
graphviz_bin_path = r'C:\Program Files\Graphviz\bin'
if os.path.exists(graphviz_bin_path) and graphviz_bin_path not in os.environ['PATH']:
    os.environ['PATH'] = f"{graphviz_bin_path}{os.pathsep}{os.environ['PATH']}"

# Create a new directed graph
dot = graphviz.Digraph('JeffersonCountyServices', comment='Jefferson County Fire & EMS Service Agreements')
dot.attr(rankdir='TB', splines='ortho', nodesep='0.8', label='Jefferson County Service Agreement Map', labelloc='t', fontsize='20')

# --- Data Definitions ---
provider_style = {'shape': 'box', 'style': 'filled', 'fillcolor': '#a6cee3'} # Blue
town_style = {'shape': 'ellipse', 'style': 'filled', 'fillcolor': '#b2df8a'} # Green

providers = {
    'P_JEF': 'City of Jefferson',
    'P_JC': 'Village of Johnson Creek',
    'P_FA': 'City of Fort Atkinson',
    'P_LM': 'City of Lake Mills\n(via Ryan Bros)',
}

towns = {
    'T_AZ': 'Town of Aztalan',
    'T_FARM': 'Town of Farmington',
    'T_HEB': 'Town of Hebron',
    'T_JEF': 'Town of Jefferson',
    'T_OAK': 'Town of Oakland',
    'T_KOSH': 'Town of Koshkonong',
    'T_MIL': 'Town of Milford',
    'T_WAT': 'Town of Watertown',
    'T_LM': 'Town of Lake Mills',
}

contracts = [
    # City of Jefferson EMS (ends 2027)
    {'provider': 'P_JEF', 'town': 'T_JEF', 'service': 'EMS ($/Capita)', 'end_date': '2027', 'color': 'blue', 'style': 'solid'},
    {'provider': 'P_JEF', 'town': 'T_FARM', 'service': 'EMS ($/Capita)', 'end_date': '2027', 'color': 'blue', 'style': 'solid'},
    {'provider': 'P_JEF', 'town': 'T_HEB', 'service': 'EMS ($/Capita)', 'end_date': '2027', 'color': 'blue', 'style': 'solid'},
    {'provider': 'P_JEF', 'town': 'T_OAK', 'service': 'EMS ($/Capita)', 'end_date': '2027', 'color': 'blue', 'style': 'solid'},
    {'provider': 'P_JEF', 'town': 'T_AZ', 'service': 'EMS ($/Capita)', 'end_date': '2027', 'color': 'blue', 'style': 'solid'},
    # City of Jefferson Fire (ends 2027)
    {'provider': 'P_JEF', 'town': 'T_JEF', 'service': 'Fire (Equalized Value)', 'end_date': '2027', 'color': 'red', 'style': 'dashed'},
    {'provider': 'P_JEF', 'town': 'T_FARM', 'service': 'Fire (Equalized Value)', 'end_date': '2027', 'color': 'red', 'style': 'dashed'},
    {'provider': 'P_JEF', 'town': 'T_HEB', 'service': 'Fire (Equalized Value)', 'end_date': '2027', 'color': 'red', 'style': 'dashed'},
    {'provider': 'P_JEF', 'town': 'T_OAK', 'service': 'Fire (Equalized Value)', 'end_date': '2027', 'color': 'red', 'style': 'dashed'},
    {'provider': 'P_JEF', 'town': 'T_AZ', 'service': 'Fire (Equalized Value)', 'end_date': '2027', 'color': 'red', 'style': 'dashed'},
    # Village of Johnson Creek (ends 2028)
    {'provider': 'P_JC', 'town': 'T_FARM', 'service': 'Fire/EMS (Equalized Value)', 'end_date': '2028', 'color': 'darkgreen', 'style': 'solid'},
    {'provider': 'P_JC', 'town': 'T_MIL', 'service': 'Fire/EMS (Equalized Value)', 'end_date': '2028', 'color': 'darkgreen', 'style': 'solid'},
    {'provider': 'P_JC', 'town': 'T_WAT', 'service': 'Fire/EMS (Equalized Value)', 'end_date': '2028', 'color': 'darkgreen', 'style': 'solid'},
    {'provider': 'P_JC', 'town': 'T_AZ', 'service': 'Fire/EMS (Equalized Value)', 'end_date': '2028', 'color': 'darkgreen', 'style': 'solid'},
    # City of Fort Atkinson (ends 2025)
    {'provider': 'P_FA', 'town': 'T_KOSH', 'service': 'EMS ($/Capita)', 'end_date': '2025', 'color': 'purple', 'style': 'solid'},
    # City of Lake Mills (Rolling Term from 2025)
    {'provider': 'P_LM', 'town': 'T_LM', 'service': 'EMS ($/Capita)', 'end_date': 'Rolling', 'color': 'orange', 'style': 'solid'},
    {'provider': 'P_LM', 'town': 'T_OAK', 'service': 'EMS ($/Capita)', 'end_date': 'Rolling', 'color': 'orange', 'style': 'solid'},
]

# --- Create Nodes ---
with dot.subgraph(name='cluster_providers') as c:
    c.attr(label='Service Providers', style='filled', color='lightgrey')
    for key, name in providers.items():
        c.node(key, name, **provider_style)
    c.attr(rank='same')

with dot.subgraph(name='cluster_towns') as c:
    c.attr(label='Recipient Municipalities (Towns)', style='filled', color='whitesmoke')
    for key, name in towns.items():
        c.node(key, name, **town_style)

# --- Create Edges from data ---
for contract in contracts:
    label = f"{contract['service']}\n(Ends {contract['end_date']})"
    dot.edge(
        contract['provider'],
        contract['town'],
        label=label,
        color=contract['color'],
        fontcolor=contract['color'],
        style=contract['style']
    )

# --- Render the graph to a file ---
try:
    dot.render('jefferson_county_services', view=True, format='png', cleanup=True)
    print("Successfully generated 'jefferson_county_services.png' and opened it.")
except Exception as e:
    print(f"Error generating graph: {e}")
    print("\nPlease ensure you have installed the Graphviz command-line tools from https://graphviz.org/download/")