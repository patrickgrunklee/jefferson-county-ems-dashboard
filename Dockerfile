FROM python:3.11-slim

WORKDIR /app

# Install system deps for geopandas (GDAL/GEOS/PROJ)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev libgeos-dev libproj-dev gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy app code + data files
COPY ems_dashboard_app.py .
COPY jefferson_county.geojson .
COPY jefferson_ems_districts.geojson .
COPY jefferson_fire_districts.geojson .
COPY jefferson_stations.geojson .
COPY jefferson_helenville_responders.geojson .
COPY jefferson_zcta.geojson .
COPY ["ISyE Project/Data and Resources/Call Data", "ISyE Project/Data and Resources/Call Data/"]
COPY ["ISyE Project/Comparison Output/county_ems_comparison_data.xlsx", "ISyE Project/Comparison Output/county_ems_comparison_data.xlsx"]
COPY simulation_output/ simulation_output/

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "120", "ems_dashboard_app:server"]
