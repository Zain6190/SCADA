"""Update downstream impacts with real Census 2023 population data."""
import csv
from sqlalchemy import text
from infrastructure.db.engine import engine as sa_engine

# Read all census files
districts = {}
for file in [
    r"C:\Users\haris\OneDrive\Desktop\SCADA\IBCP-SCADA\data\raw\census_kp_2023.csv",
    r"C:\Users\haris\OneDrive\Desktop\SCADA\IBCP-SCADA\data\raw\census_punjab_2023.csv",
    r"C:\Users\haris\OneDrive\Desktop\SCADA\IBCP-SCADA\data\raw\census_sindh_2023.csv",
]:
    with open(file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["region"] == "OVERALL":
                name = row["name_admin_unit"].title()
                pop = int(row["all_sexes"])
                districts[name] = pop

# Districts along each river segment (approximate flood-prone areas)
segment_mapping = {
    # Tarbela -> Kalabagh (Indus)
    (1, 4): {
        "districts": ["Haripur", "Swabi", "Mardan", "Nowshera"],
        "bridges": 4,
        "hospitals": 2,
        "roads_km": 120,
        "notes": "N-55 Indus Highway corridor, Haripur/Swabi/Mardan/Nowshera",
    },
    # Kalabagh -> Taunsa (Indus)
    (4, 5): {
        "districts": ["Dera Ismail Khan", "Mianwali", "Bhakkar"],
        "bridges": 3,
        "hospitals": 2,
        "roads_km": 200,
        "notes": "D.I. Khan/Mianwali/Bhakkar districts",
    },
    # Taunsa -> Guddu (Indus)
    (5, 6): {
        "districts": ["Rajanpur", "Dera Ghazi Khan", "Rahim Yar Khan", "Kashmore"],
        "bridges": 6,
        "hospitals": 3,
        "roads_km": 350,
        "notes": "Rajanpur/D.G. Khan/Rahim Yar Khan/Kashmore districts",
    },
    # Guddu -> Sukkur (Indus)
    (6, 7): {
        "districts": ["Sukkur", "Khairpur", "Ghotki"],
        "bridges": 8,
        "hospitals": 4,
        "roads_km": 400,
        "notes": "Sukkur/Khairpur/Ghotki districts",
    },
    # Sukkur -> Kotri (Indus)
    (7, 8): {
        "districts": ["Hyderabad", "Matiari", "Tando Muhammad Khan"],
        "bridges": 10,
        "hospitals": 5,
        "roads_km": 450,
        "notes": "Hyderabad/Matiari/Tando Muhammad Khan districts",
    },
    # Nowshera -> Kalabagh (Kabul)
    (9, 4): {
        "districts": ["Nowshera", "Peshawar", "Mardan"],
        "bridges": 3,
        "hospitals": 1,
        "roads_km": 150,
        "notes": "Nowshera/Peshawar/Mardan, high density urban",
    },
    # Marala -> Panjnad (Chenab)
    (10, 11): {
        "districts": ["Sialkot", "Gujrat", "Mandi Bahauddin"],
        "bridges": 4,
        "hospitals": 2,
        "roads_km": 180,
        "notes": "Sialkot/Gujrat/Mandi Bahauddin districts",
    },
    # Panjnad -> Guddu (Jhelum-Chenab)
    (11, 6): {
        "districts": ["Muzaffargarh", "Rajanpur"],
        "bridges": 2,
        "hospitals": 1,
        "roads_km": 100,
        "notes": "Muzaffargarh/Rajanpur, joins Indus at Uch",
    },
}

# Calculate and update
with sa_engine.connect() as conn:
    for (src, dst), info in segment_mapping.items():
        # Get population
        total_pop = sum(districts.get(d, 0) for d in info["districts"])
        village_count = len(info["districts"]) * 50  # rough estimate
        town_count = len(info["districts"]) * 3

        # Get travel time from existing data
        row = conn.execute(
            text("""
                SELECT travel_time_hours_expected, distance_km
                FROM aquavision.water_downstream_impacts
                WHERE source_asset_id = :src AND downstream_asset_id = :dst
            """),
            {"src": src, "dst": dst},
        ).mappings().first()

        if row:
            # Update with real population
            conn.execute(
                text("""
                    UPDATE aquavision.water_downstream_impacts
                    SET affected_population_est = :pop,
                        affected_village_count = :villages,
                        affected_town_count = :towns,
                        bridges_count = :bridges,
                        hospitals_count = :hospitals,
                        roads_km = :roads,
                        notes = :notes
                    WHERE source_asset_id = :src AND downstream_asset_id = :dst
                """),
                {
                    "pop": total_pop,
                    "villages": village_count,
                    "towns": town_count,
                    "bridges": info["bridges"],
                    "hospitals": info["hospitals"],
                    "roads": info["roads_km"],
                    "notes": info["notes"],
                    "src": src,
                    "dst": dst,
                },
            )
            print(f"Updated: {src} -> {dst}: {total_pop:,} people")
        else:
            print(f"No segment found for {src} -> {dst}")

    conn.commit()

print("\nDone!")
