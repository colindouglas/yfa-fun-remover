import csv
from yahoo_oauth import OAuth2
import json
import yahoo_fantasy_api as yfa
import pandas as pd

LEAGUE_ID = '398.l.35309'

with open('../secrets.csv') as secrets_file:
    reader = csv.reader(secrets_file)
    for row in reader:
        if row[0] == 'yahoo_old':
            yahoo_creds = {'consumer_key': row[1], 'consumer_secret': row[2]}
        else:
            pass

with open('oauth2.json', "w") as f:
    f.write(json.dumps(yahoo_creds))

oauth = OAuth2(None, None, from_file='oauth2.json')

lg = yfa.league.League(oauth, LEAGUE_ID)

taken = lg.taken_players()
waivers = lg.waivers()
fa_batters = lg.free_agents('B')
fa_pitchers = lg.free_agents('P')

players = taken + waivers + fa_batters + fa_pitchers

players_df = pd.DataFrame(players)

players_df.to_csv(path_or_buf='players_2020.csv')