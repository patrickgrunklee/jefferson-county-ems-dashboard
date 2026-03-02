# Jefferson County EMS Dashboard

Interactive Dash dashboard for analyzing Jefferson County, WI EMS operations — call volume, response times, financials, staffing, and cross-county comparisons.

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the dashboard

```bash
python ems_dashboard_app.py
```

### 3. Open in browser

Navigate to **http://127.0.0.1:8050**

## Project Structure

```
.
├── ems_dashboard_app.py                          # Main dashboard application
├── requirements.txt                              # Python dependencies
├── jefferson_county.geojson                      # County boundary (Census TIGER 2023)
├── jefferson_ems_districts.geojson               # EMS service district boundaries
├── jefferson_fire_districts.geojson              # Fire district boundaries
├── jefferson_stations.geojson                    # Station locations
├── jefferson_helenville_responders.geojson       # Helenville responder locations
│
└── ISyE Project/
    ├── Comparison Output/
    │   └── county_ems_comparison_data.xlsx        # Cross-county comparison data
    └── Data and Resources/
        ├── EMS Contract Details for all Towns in Jefferson County.xlsx
        └── Call Data/
            └── Copy of 2024 EMS Workgroup - *.xlsx   # 14 NFIRS call record files
```

## Data Sources

- **Call Data**: 14 NFIRS Excel workbooks from the 2024 EMS Workgroup (one per department)
- **Comparison Data**: Compiled county-level KPIs for Jefferson, Portage, and Bayfield counties
- **GeoJSON Boundaries**: Census TIGER 2023 shapefiles converted to GeoJSON
- **Benchmarks**: WI statewide EMS averages, National CMS GADCS data, NFPA 1710/1720 standards (embedded in app with citable sources)

## Notes

- On first run, the app creates a parquet cache in your system temp directory for faster subsequent loads
- All data citations and source URLs are displayed in the dashboard footer of each section
- Budget and billing data are hand-compiled from FY2024-2025 PDF budgets and embedded in the app code
