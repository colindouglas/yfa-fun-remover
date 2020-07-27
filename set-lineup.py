from helper_functions import get_league_key, get_oauth
import yahoo_fantasy_api as yfa

if 'oauth' not in globals():
    oauth = get_oauth()

league_key = get_league_key(oauth, "mlb", "Chemical Hydrolysis League")

league = yfa.league.League(oauth, league_key)
team = yfa.team.Team(oauth, league.team_key())

positions = league.positions()

roster = team.roster()

jose = league.player_details('Jose Altuve')

jose[0].keys()

jose[0]['player_stats']['stats']