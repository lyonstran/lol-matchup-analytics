# Prints the PUUID (Riot's permanent player id) for a Riot ID.
# Usage: uv run python pipeline/lookup_puuid.py "fionaapple21" "IKNOW"
import sys

from riot_client import RiotClient


def main():
    # we need exactly two arguments: the game name and the tag line
    if len(sys.argv) != 3:
        print('usage: uv run python pipeline/lookup_puuid.py "<game name>" "<tag line>"')
        return
    game_name = sys.argv[1]
    tag_line = sys.argv[2]

    # one Account-V1 call; this also proves your RIOT_API_KEY works
    client = RiotClient(region="americas")
    account = client.get_account_by_riot_id(game_name, tag_line)
    client.close()

    print(account["puuid"])


if __name__ == "__main__":
    main()
