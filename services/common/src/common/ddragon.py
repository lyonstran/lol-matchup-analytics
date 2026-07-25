import httpx

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"


def get_latest_version() -> str:
    """Newest patch version. The versions list is ordered newest-first."""
    resp = httpx.get(f"{DDRAGON_BASE}/api/versions.json", timeout=10)
    resp.raise_for_status()
    return resp.json()[0]


def get_champions(version: str) -> dict:
    """Champion static data for a patch, keyed by string id (e.g. 'Aatrox')."""
    url = f"{DDRAGON_BASE}/cdn/{version}/data/en_US/champion.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()["data"]


def build_champion_id_map(champions: dict) -> dict[int, str]:
    """Map the numeric championId (as Match-V5 returns it) to display name."""
    return {int(c["key"]): c["name"] for c in champions.values()}


def get_items(version: str) -> dict:
    """Item static data for a patch, keyed by numeric item id (as a string)."""
    url = f"{DDRAGON_BASE}/cdn/{version}/data/en_US/item.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()["data"]