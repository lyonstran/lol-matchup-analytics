from common.ddragon import get_latest_version, get_champions, build_champion_id_map

version = get_latest_version()
print(f"Latest patch: {version}")

champions = get_champions(version)
print(f"Fetched {len(champions)} champions")

id_map = build_champion_id_map(champions)
sample = {k: id_map[k] for k in list(id_map)[:5]}
print("Sample id -> name:", sample)