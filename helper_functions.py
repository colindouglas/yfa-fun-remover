import csv
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
from datetime import datetime

def update_oauth(path='oauth2.json'):

    """
    Authenticates with Yahoo and creates session context from local secrets file.
    Returns an OAuth2 object for use in future calls

    path - where to save the oauth token, defaults to ./oauth2.json

    ex: get_oauth()
    ex: get_oauth(path='secrets/oauth.json')
    """

    with open('../secrets.csv') as secrets_file:
        reader = csv.reader(secrets_file)
        for row in reader:
            if row[0] == 'yahoo_old':
                yahoo_creds = {'consumer_key': row[1], 'consumer_secret': row[2]}
            else:
                pass

    with open(path, "w") as f:
        f.write(json.dumps(yahoo_creds))

    return OAuth2(None, None, from_file=path)


def get_league_key(oauth, code: str, league_name: str = None) -> dict:

    """
    Get the key of a league by name

    oauth - Fully constructed session context (see get_auth())
    code - Sports code for the league you're looking for (e.g., 'mlb' or 'nfl')
    league_name - The name of the league you're looking for. If no league name is
             passed, will print the names of the leagues and return an empty dictionary

    ex: get_league_details(oauth, code="nfl")
    ex: get_league_details(oauth, code="mlb", league_name="Neato Keeper League")
    """

    this_year = datetime.today().year
    game = yfa.game.Game(oauth, code)
    league_ids = game.league_ids(this_year)

    if league_name is None:
        for league_id in league_ids:
            league = game.to_league(league_id)
            details = league.settings()
            print('League: {name} // Key: {league_key}'.format(**details))
            return {}
    else:
        for league_id in league_ids:
            league = game.to_league(league_id)
            details = league.settings()
            if details['name'] == league_name:
                return details['league_key']
            print("Can't find league '{}'".format(league_name))
            return {}

