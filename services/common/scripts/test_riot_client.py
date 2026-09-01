from common.riot_client import RiotClient

GAME_NAME = "jefff buckley"
TAG_LINE = "GRACE"  # whatever follows the # in your Riot ID

client = RiotClient(region="americas")  # americas = NA/LAN/LAS/BR/OCE

account = client.get_account_by_riot_id(GAME_NAME, TAG_LINE)
puuid = account["puuid"]
print(f"Resolved PUUID: {puuid[:20]}...")

match_ids = client.get_match_ids_by_puuid(puuid, count=5, queue=420)  # 420 = ranked solo/duo
print(f"Recent match IDs: {match_ids}")

if match_ids:
    info = client.get_match(match_ids[0])["info"]
    print(f"Game version: {info['gameVersion']}")
    print(f"Participants: {len(info['participants'])}")
    p = info["participants"][0]
    print(f"Example: {p['championName']} (win={p['win']})")

client.close()