import csv
import json
from yahoo_oauth import OAuth2
import logging
import mlbgame
import yahoo_fantasy_api as yfa
import pandas as pd
from unidecode import unidecode
from datetime import datetime
import numpy as np


def find_league_key(oauth: OAuth2, code: str, league_name: str = None) -> str:
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
            return ""
    else:
        for league_id in league_ids:
            league = game.to_league(league_id)
            details = league.settings()
            if details['name'] == league_name:
                return details['league_key']
            print("Can't find league '{}'".format(league_name))
            return ""


def update_oauth(path='oauth.json') -> OAuth2:
    """
    Authenticates with Yahoo and creates session context from local secrets file.
    Returns an OAuth2 object for use in future calls

    path - where to save the oauth token, defaults to ./oauth.json

    ex: get_oauth()
    ex: get_oauth(path='secrets/oauth.p')
    """

    logging.getLogger('yahoo_oauth').disabled = True

    try:
        oauth = OAuth2(None, None, from_file=path)
        if oauth.token_is_valid():
            return oauth
        else:
            oauth.refresh_access_token()
            # https://github.com/josuebrunel/yahoo-oauth/issues/55#issuecomment-602217706
            oauth.session = oauth.oauth.get_session(token=oauth.access_token)
            # Apparently this is a bug
            return oauth
    except FileNotFoundError:
        with open('../secrets.csv') as secrets_file:
            reader = csv.reader(secrets_file)
            for row in reader:
                if row[0] == 'yahoo_old':
                    consumer_key = row[1]
                    consumer_secret = row[2]
        credentials = {'consumer_key': consumer_key, 'consumer_secret': consumer_secret}
        with open(path, "w") as f:
            f.write(json.dumps(credentials))
        return OAuth2(None, None, from_file=path)


class Roster:

    def __init__(self, league_key, oauth_path="oauth2.p"):

        # Create and confirm that OAuth2 token is updated
        self.oauth_path = oauth_path
        self.oauth = update_oauth()
        assert self.oauth.token_is_valid()

        # Create the Yahoo Fantasy abstraction
        self.league_key = league_key
        self.league = yfa.league.League(self.oauth, league_key)
        self.team = yfa.team.Team(self.oauth, self.league.team_key())
        self.when = self.league.edit_date()  # The next time the roster can be edited

        # Fetches the probable starters and teams from MLB GameDay API
        self.probables = self.fetch_probables()

        # WAR projections for each player that are used to break ties
        # Define where to find WAR projections for each player
        player_values = pd.read_csv(
            "data/proj_steamer_2020_b.csv"  # Batter projections
        ).append(pd.read_csv(
            "data/proj_steamer_2020_p.csv"))  # Pitcher projections
        # If there are two players with the same name, only keep the
        # the player with the most projected ABs or IPs
        player_values = player_values.sort_values(by=['AB', 'IP'])
        player_values = player_values.drop_duplicates(subset=['Name'], keep='last')
        # Clean up the names
        player_values['name'] = player_values['Name'].map(self.cleanup_name)
        self.player_values = player_values.set_index('name')[['WAR']]

        # A "roster" is all of the players that are on a team
        roster = pd.DataFrame(self.team.roster())
        roster['name'] = roster['name'].map(self.cleanup_name)
        roster = roster.set_index('name')
        # Join the values for each player
        self.roster = roster.join(self.player_values, how='left')

        # Ask Yahoo which team each player plays for
        self.roster['team'] = [self.league.player_details(x)[0]["editorial_team_abbr"]
                               for x in self.roster['player_id']]

        # Determine whether each player on the roster is playing
        self.roster['is_playing'] = [self._is_playing(player) for player in self.roster.index]

        self.positions = self.league.positions()

    @staticmethod
    def cleanup_name(x: str) -> str:

        """
        Removes accents/hyphens/periods from a player's name for easier joins
        """

        o = unidecode(x)
        o = o.replace('-', ' ')
        o = o.replace('.', '')
        return o

    def fetch_probables(self) -> dict:

        """
        Gets a list of probable starters for a given date
        from MLB GameDay API

        :return: a dict with keys "pitchers" containing probable pitchers
            and "teams" containing teams that are playing
        """

        # Get probable starters
        abbrevs = {
            "Braves": "Atl",
            "Marlins": "Mia",
            "Mets": "NYM",
            "Phillies": "Phi",
            "Nationals": "Was",

            "Cubs": "ChC",
            "Reds": "Cin",
            "Brewers": "Mil",
            "Pirates": "Pit",
            "Cardinals": "StL",

            "Rockies": "Col",
            "Giants": "SF",
            "D-backs": "Ari",
            "Dodgers": "LAD",
            "Padres": "SD",

            "Orioles": "Bal",
            "Yankees": "NYY",
            "Rays": "TB",
            "Red Sox": "Bos",
            "Blue Jays": "Tor",

            "Twins": "Min",
            "Indians": "Cle",
            "Royals": "KC",
            "White Sox": "CWS",
            "Tigers": "Det",

            "Athletics": "Oak",
            "Rangers": "Tex",
            "Astros": "Hou",
            "Mariners": "Sea",
            "Angels": "LAA"}

        pitchers = []
        teams = []
        for game in mlbgame.day(self.when.year, self.when.month, self.when.day):
            if game.game_status == 'PRE_GAME':
                if len(game.p_pitcher_home) > 2:
                    pitchers.append(game.p_pitcher_home)
                if len(game.p_pitcher_away) > 2:
                    pitchers.append(game.p_pitcher_away)
                if game.home_team not in teams:
                    teams.append(abbrevs[game.home_team])
                if game.away_team not in teams:
                    teams.append(abbrevs[game.away_team])
        pitchers = [self.cleanup_name(name) for name in pitchers]
        o = dict()
        o["pitchers"] = pitchers
        o["teams"] = teams
        return o

    def _is_playing(self, player: str) -> int:
        """
        Determines whether a player is playing, based on the probables
        :param player: the name of a player
        :return: a quasi-boolean:
             0 if not playing
             1 if playing
            -1 if injured
        """

        _, status, _, elig, _, _, _team, *_ = self.roster.loc[player, ]
        if status in ("IL", "NA"):
            return -1
        if status == "DTD":
            return 0
        if _team not in self.probables['teams']:
            return 0
        if 'SP' in elig and player not in self.probables['pitchers']:
            return 0
        else:
            return 1

    def optimize_lineup(self):

        lineup = pd.DataFrame(self.league.positions()).T
        lineup = lineup.loc[lineup.index.repeat(np.array(lineup['count']))]
        lineup = lineup[lineup.index != "BN"]
        lineup = lineup.reset_index()
        lineup = lineup.rename(columns={"index": "pos"})
        lineup['final_player'] = [None for _ in range(0, len(lineup))]
        assigned_players = []

        while None in lineup['final_player'].unique():
            for _ in (_ for _ in lineup.final_player if _ is None):
                lineup['eligible_players'] = [[] for _ in range(0, len(lineup))]
                # Assign each position a list of eligible players
                for row in lineup.itertuples():
                    index, pos, _, _, final_player, eligible_players = row
                    # If there's already a player assigned to the position, continue
                    if final_player:
                        continue
                    for player in self.roster.itertuples():
                        name, _, _, _, eligible_positions, *_ = player
                        # If the player is already assigned, next
                        if name in assigned_players:
                            continue
                        if pos in eligible_positions:
                            eligible_players.append(name)
                    # If there's only one eligible player, cut to the chase and assign him
                    if len(eligible_players) == 1:
                        lineup.loc[index, 'final_player'] = eligible_players[0]
                        print("Assigning", eligible_players[0], "to", lineup.loc[index, 'pos'])
                        assigned_players = [player for player in lineup.final_player if player is not None]

            # Perform tiebreakers based on expected value
            tb_row = np.where([x is None for x in lineup.final_player])[0][0]  # Which row to tiebreak
            # If there are no eligible players, put the final player in the slot as "Empty"
            if len(lineup.eligible_players[tb_row]) == 0:
                lineup.final_player[tb_row] = "Empty"
                continue
            tb = self.roster[self.roster.index.isin(lineup.eligible_players[tb_row])]  # Filter roster for those players
            tb = tb.assign(value=tb.is_playing * tb.WAR)  # Approximate their value
            best = tb.index[tb.value == max(tb.value)][0]  # Player with highest value
            print("Assigning", best, "to", lineup.pos[tb_row])
            lineup.final_player[tb_row] = best
            assigned_players = [player for player in lineup['final_player'].unique() if player is not None]

        o = lineup[['pos', 'final_player']]
        o = o.rename(columns={"final_player": "player_name", "pos": "target_pos"})
        return o

    def set_lineup(self, target):
        # Target lineup
        target = target.set_index('player_name')

        # Current lineup
        current = self.roster[['player_id', 'selected_position']]
        current = current.rename(columns={"selected_position": "current_pos"})

        target = target.join(current).dropna()

        # If we pass these dictionaries, we bench every player except IL/NA players
        bench_everyone = []
        for pid, pos in zip(target.player_id, target.target_pos):
            if pos in ["NA", "IL"]:
                bench_everyone.append({"player_id": int(pid), "selected_position": pos})
            else:
                bench_everyone.append({"player_id": int(pid), "selected_position": "BN"})

        # These dictionaries set the lineup to what we passed in the function call
        target_dict = [
            {"player_id": int(pid), "selected_position": pos}
            for pid, pos in zip(target.player_id, target.target_pos)
        ]

        self.team.change_positions(self.when, bench_everyone)

        for pos in target_dict:
            try:
                self.team.change_positions(self.when, [pos])
                print("Success: {player_id} to {selected_position}".format(**pos))
            except RuntimeError:
                print("Failed (?): {player_id} to {selected_position}".format(**pos))


if __name__ == "__main__":
    token = update_oauth()
    key = find_league_key(token, 'mlb', "Chemical Hydrolysis League")
    ros = Roster(key)
    opt = ros.optimize_lineup()
    ros.set_lineup(opt)
