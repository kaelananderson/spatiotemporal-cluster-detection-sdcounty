# [markdown]
# # All years 311 hierarchy data prep to be used for SatScan

# 
import geopandas as gpd
import pandas as pd
df_2018 = gpd.read_file('../../data/2018/hierarchical_data_2018.geojson')
df_2019 = gpd.read_file('../../data/2019/hierarchical_data_2019.geojson')
df_2020 = gpd.read_file('../../data/2020/hierarchical_data_2020.geojson')
df_2021 = gpd.read_file('../../data/2021/hierarchical_data_2021.geojson')
df_2022 = gpd.read_file('../../data/2022/hierarchical_data_2022.geojson')
df_2023 = gpd.read_file('../../data/2023/hierarchical_data_2023.geojson')
df_2024 = gpd.read_file('../../data/2024/hierarchical_data_2024.geojson')


# 
total_rows_before = sum(df.shape[0] for df in [df_2018, df_2019, df_2020, df_2021, df_2022, df_2023, df_2024])

# 
# Merge all GeoDataFrames
df = gpd.GeoDataFrame(
    pd.concat([df_2018, df_2019, df_2020, df_2021, df_2022, df_2023, df_2024], ignore_index=True)
)

# 
total_rows_after = df.shape[0]

# Print verification result
print(f"Total rows before merging: {total_rows_before}")
print(f"Total rows after merging: {total_rows_after}")


# 
df.head()

# 
camp_data = df[df["Camp"] == True]
camp_data.head()

# 
camp_data.shape

# 
cols_to_drop = [
    "record_id",
    "Matches Homeless/Encampment Filter",
    "Vehicle",
    "Individual",
    "Active Camp",
    "Abandoned Camp",
    "Transient Camp",
    "Abandoned Vehicle",
    "Mental Health Crisis",
    "Neutral Presence",
    "Daily Activities",
    "Using Drugs"

]

camp_data = camp_data.drop(columns=cols_to_drop)


# 
camp_data.head()

# 
# Convert `date` column to datetime format
camp_data["date"] = pd.to_datetime(camp_data["date"], utc=True).dt.date
camp_data["date"] = pd.to_datetime(camp_data["date"])
camp_data

# 
# Ensure consistent location_id for duplicate geometries
# Step 1: Create a unique mapping of geometries to location_id
unique_geometries = camp_data[["geometry"]].drop_duplicates().reset_index(drop=True)
unique_geometries["location_id"] = range(1, len(unique_geometries) + 1)

# Step 2: Merge the location_id back into the original camp_data
camp_data = camp_data.merge(unique_geometries, on="geometry", how="left")

# Step 3: Add a unique caseID for each record
# camp_data["caseID"] = range(1, len(camp_data) + 1)

# 
camp_data

# 
# Group by location_id and count occurrences
location_counts = camp_data["location_id"].value_counts()

# Filter for location_ids with a count of 2 or more
duplicate_location_ids = location_counts[location_counts >= 2].index

# Filter camp_data for these location_ids
duplicate_records = camp_data[camp_data["location_id"].isin(duplicate_location_ids)]
duplicate_records

# 
duplicates = camp_data[camp_data.duplicated(keep=False)]
duplicates

# 
duplicates.shape

# 
# Remove full duplicates, keeping only the first occurrence
camp_data_deduplicated = camp_data.drop_duplicates(keep="first")

# Display the deduplicated DataFrame
camp_data_deduplicated


# 
# Overwrite the original camp_data with the deduplicated version
camp_data = camp_data_deduplicated

# 
camp_data

# 
duplicate_geometries = camp_data[camp_data.duplicated(subset="location_id", keep=False)]
duplicate_geometries_sorted = duplicate_geometries.sort_values(by="location_id")

duplicate_geometries_sorted


# 
none_type_rows = camp_data[camp_data['geometry'].isna()]
none_type_rows

# 
camp_data = camp_data.dropna(subset=['geometry'])

# 
none_type_rows = camp_data[camp_data['geometry'].isna()]
none_type_rows

#  [markdown]
# ## Create cas file

# 
# Step 2: Aggregate cases by date and location_id
aggregated_df = camp_data.groupby(["date", "location_id"]).size().reset_index(name="cases")


# 
aggregated_df.head()

# 

# Step 3: Add a unique case_id starting from 1
aggregated_df = aggregated_df.sort_values(by=["date", "location_id"])  # Sort by date and location_id
aggregated_df["case_id"] = range(1, len(aggregated_df) + 1)  # Create unique case IDs


# 
aggregated_df.head()

# 
# Step 4: Reorder columns to match .cas file format
cas_df = aggregated_df[["case_id", "date", "cases", "location_id"]]


# 
cas_df.head()

# 
cas_df.shape

# 
records_with_multiple_cases = cas_df[cas_df["cases"] > 3]
records_with_multiple_cases

# 

# Step 5: Save as a csv text file
cas_file_path = "../../data/satscan_usable/all_years_camps_new.cas"
cas_df.to_csv(cas_file_path, index=False, header=True)



#  [markdown]
# ## Create geo file

# 
camp_data.dtypes

# 
from shapely.geometry import Point

# Ensure camp_data is a copy to avoid SettingWithCopyWarning
camp_data = camp_data.copy()

# Extract longitude and latitude directly from geometry objects
camp_data["longitude"] = camp_data["geometry"].apply(lambda point: point.x)
camp_data["latitude"] = camp_data["geometry"].apply(lambda point: point.y)

camp_data.head()

# 
# Step 2: Handle duplicate coordinates (same lat/lon -> same location_id)
geo_df = camp_data[["location_id", "latitude", "longitude"]].drop_duplicates(subset=["latitude", "longitude"])

geo_df

# 
# Validate coordinates
# Ensure latitude is between -90 and 90, and longitude is between -180 and 180
if not ((geo_df["latitude"].between(-90, 90)) & (geo_df["longitude"].between(-180, 180))).all():
    raise ValueError("Invalid coordinates found in the data.")

# Sort by location_id
geo_df = geo_df.sort_values(by="location_id")
geo_df.head()


# 
geo_df.shape

# 
# Step 5: Save as a csv text file
geo_file_path = "../../data/satscan_usable/all_years_camps_new.geo"
geo_df.to_csv(geo_file_path, index=False, header=True)

# 
# Check for duplicate latitude and longitude combinations
duplicates = geo_df[geo_df.duplicated(subset=["latitude", "longitude"], keep=False)]

# Display the duplicate records
if not duplicates.empty:
    print("Duplicate latitude and longitude pairs found:")
    print(duplicates)
else:
    print("No duplicate latitude and longitude pairs found.")

# 
cas_df

# 
camp_data_counts = camp_data.groupby(['date', 'location_id']).size().reset_index(name='camp_data_count')
camp_data_counts

# 
# Merge the camp_data_counts with cas_df on both location_id and date
merged_df = pd.merge(camp_data_counts, cas_df, on=['date', 'location_id'], how='inner')

# Check if the counts from camp_data match the 'cases' in cas_df
merged_df['match'] = merged_df['camp_data_count'] == merged_df['cases']

# 
merged_df

# 
all_match = merged_df[merged_df["match"] == False]
all_match

# 
# Step 4: Verify that all rows match (i.e., all 'match' values should be True)
all_matches = merged_df['match'].all()

# Display the result
if all_matches:
    print("All counts match!")
else:
    print("There are mismatches.")

# 
# If using your .cas file DataFrame where date is in YYYYMMDD format:
min_date = cas_df['date'].astype(str).min()
max_date = cas_df['date'].astype(str).max()

print(f"Study Period Start: {min_date}")
print(f"Study Period End: {max_date}")

# To calculate total number of days:
from datetime import datetime

# If dates are in YYYY-MM-DD format:
start_date = datetime.strptime(str(min_date), '%Y-%m-%d')
end_date = datetime.strptime(str(max_date), '%Y-%m-%d')

# # If dates are in YYYYMMDD format:
# start_date = datetime.strptime(str(min_date), '%Y%m%d')
# end_date = datetime.strptime(str(max_date), '%Y%m%d')

total_days = (end_date - start_date).days + 1  # +1 to include both start and end dates
print(f"Total days in study period: {total_days}")

# 
# Option 1: Using pandas .isin() method to find missing locations.
missing_locations = cas_df.loc[~cas_df['location_id'].isin(geo_df['location_id']), 'location_id'].unique()

if missing_locations.size > 0:
    print("The following location_ids from the case file are not present in the geo file:")
    for loc in missing_locations:
        print(loc)
else:
    print("All locations in the case file are present in the geo file.")

# 
# This is an alternative approach that achieves the same result.
geo_locations = set(geo_df['location_id'])
case_locations = set(cas_df['location_id'])
missing = case_locations - geo_locations

if missing:
    print("\n[Set Operation] The following location_ids are missing from the geo file:")
    for loc in missing:
        print(loc)
else:
    print("\n[Set Operation] All locations in the case file are present in the geo file.")

# 
# Check if every geo location is referenced in the case file.
unused_geo_locations = geo_df.loc[~geo_df['location_id'].isin(cas_df['location_id']), 'location_id'].unique()

if unused_geo_locations.size > 0:
    print("The following location_ids in the geo file are not referenced in the case file:")
    for loc in unused_geo_locations:
        print(loc)
else:
    print("All locations in the geo file are referenced in the case file.")


# 
geo_df.dtypes

# 
import matplotlib.pyplot as plt

# Group by date and sum the cases
time_series = cas_df.groupby("date")["cases"].sum().reset_index()

# Plot the time series
plt.figure(figsize=(12, 6))
plt.plot(time_series["date"], time_series["cases"], marker='o')
plt.title("Time Series of Cases")
plt.xlabel("Date")
plt.ylabel("Number of Cases")
plt.xticks(rotation=45)
plt.grid(True)
plt.show()

# 
# Ensure 'date' is in datetime format
cas_df['date'] = pd.to_datetime(cas_df['date'])

# Group by year and sum the cases
cas_df['year'] = cas_df['date'].dt.year
annual_cases = cas_df.groupby('year')['cases'].sum()

# Bar Plot
plt.figure(figsize=(10, 6))
plt.bar(annual_cases.index, annual_cases.values, color='#1E90FF')
plt.title("Total Number of Cases Per Year")
plt.xlabel("Year")
plt.ylabel("Total Cases")
plt.grid(axis='y')
plt.show()

# 
# Calculate a 30-day rolling average
cas_df['rolling_avg'] = cas_df['cases'].rolling(window=30).mean()

# Line Plot with Rolling Average
plt.figure(figsize=(12, 6))
plt.plot(cas_df['date'], cas_df['cases'], color='lightgray', alpha=0.5, label='Daily Cases')
plt.plot(cas_df['date'], cas_df['rolling_avg'], color='blue', linewidth=2, label='30-Day Rolling Average')
plt.title("Trend of Cases Over Time with Rolling Average")
plt.xlabel("Date")
plt.ylabel("Number of Cases")
plt.legend()
plt.grid(True)
plt.show()


# 
import matplotlib.pyplot as plt

# Group by date and count the number of unique locations
location_time_series = camp_data.groupby("date")["location_id"].nunique().reset_index()

# Plot the time series
plt.figure(figsize=(12, 6))
plt.plot(location_time_series["date"], location_time_series["location_id"], marker='o')
plt.title("Time Series of Unique Locations")
plt.xlabel("Date")
plt.ylabel("Number of Unique Locations")
plt.xticks(rotation=45)
plt.grid(True)
plt.show()

# 
# Extract the year from the date column
cas_df.loc[:, 'year'] = cas_df['date'].dt.year
# Group by the year and count the number of records
records_per_year = cas_df.groupby('year').size().reset_index(name='record_count')

# Display the result
print(records_per_year)# Assuming cas_df is a slice of another DataFrame


# 
# Count the number of unique locations per year in the cas_df dataframe
locations_per_year_in_cas = cas_df.groupby('year')['location_id'].nunique().reset_index(name='unique_location_count')

# Display the result
print(locations_per_year_in_cas)

# 
all_df = pd.read_csv("../../data/satscan_usable/all_years_camps_new.cas").head()
recs_2024 = all_df[all_df['date'] >= '2024-01-01']

# 
# Check if there are any rows in cas_df with a date in 2024
has_2024 = cas_df['date'].dt.year.eq(2024).any()
print("Contains 2024 dates:", has_2024)

# 
aggregated_df_sorted = aggregated_df.sort_values(by="date", ascending=False)
aggregated_df_sorted.head()

# 
pd.read_csv("../../data/satscan_usable/all_years_camps.geo").head()


