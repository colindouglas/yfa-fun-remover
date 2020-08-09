import csv
import json
from yahoo_oauth import OAuth2
import mlbgame
import yahoo_fantasy_api as yfa
import pandas as pd
from unidecode import unidecode
from datetime import datetime, timedelta
import numpy as np
import logging
from logging.handlers import TimedRotatingFileHandler



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


def earliest_game() -> int:
    """
    Queries the MLB GameDay API for the start time of all of today's games.

    :return: the hour of the start time of the earliest game today
    """
    when = datetime.today()
    games = mlbgame.day(when.year, when.month, when.day)
    start_times = []  # Hour that game starts, Eastern
    for game in games:
        start_times.append(game.date.hour)
    return min(start_times)


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

    def __init__(self, league_key, values="steamer", oauth_path="oauth.json"):
        # Setup the logger
        self.logger = logging.getLogger('yahoo-fantasy')
        formatter = logging.Formatter('%(asctime)7s - %(name)s - %(levelname)s - %(message)s')

        # Write a log file for everything DEBUG and up
        self.logger.setLevel(logging.DEBUG)

        # Rotate the log files at midnight, keep a week's worth of logging
        fh = logging.handlers.TimedRotatingFileHandler(filename='lineup.log', when='D', interval=2, backupCount=1)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        # Create and confirm that OAuth2 token is updated
        self.oauth = update_oauth(oauth_path)
        assert self.oauth.token_is_valid()

        # Create the Yahoo Fantasy abstraction
        self.league_key = league_key
        self.logger.info("Getting league info...")
        self.league = yfa.league.League(self.oauth, league_key)
        self.positions = self.league.positions()
        self.logger.info("Getting team info...")
        self.team = yfa.team.Team(self.oauth, self.league.team_key())

        # Stop optimizing today's roster an hour before the first game starts
        if earliest_game() > datetime.now().hour + 1:
            self.when = datetime.today()
        else:
            self.when = datetime.today() + timedelta(days=1)
        self.logger.info("Updating lineup for {}".format(self.when.date()))

        # Fetches the probable starters and teams from MLB GameDay API
        self.probables = self.fetch_probables()

        # A "roster" is all of the players that are on a team
        self.logger.info("Fetching current roster...")
        self.roster = pd.DataFrame(self.team.roster(day=self.when))

        # Clean up the player names
        self.roster['name'] = self.roster['name'].map(self.cleanup_name)

        # Assign an approximate value to each player
        self.roster['value'] = self.value_players(how=values)

        self.roster = self.roster.set_index('name')

        # Ask Yahoo which team each player plays for
        self.roster['team'] = [self.league.player_details(x)[0]["editorial_team_abbr"]
                               for x in self.roster['player_id']]

        self.logger.info("Determining likely starters for {}...".format(self.when.date()))
        # Determine whether each player on the roster is playing
        self.roster['is_playing'] = [self.is_playing(player) for player in self.roster.index]

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

        # Translate between the names GameDay uses (keys) and the names YF uses (values)
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

    def refresh_token(self) -> None:
        """
        Refreshes the OAuth token in a Roster without without returning anything

        :return: Nadda
        """
        if self.oauth.token_is_valid():
            return
        else:
            self.oauth.refresh_access_token()
            # https://github.com/josuebrunel/yahoo-oauth/issues/55#issuecomment-602217706
            self.oauth.session = self.oauth.oauth.get_session(token=self.oauth.access_token)
            # Apparently this is a bug
            return

    def is_playing(self, player: str) -> int:
        """
        Determines whether a player is playing, based on the probables
        :param player: the name of a player
        :return: a quasi-boolean:
             0 if not playing or day-to-day
             1 if playing
            -1 if on the IL or NA list
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
                        self.logger.info("Assigning {player} to {pos}".format(
                            player=eligible_players[0],
                            pos=lineup.loc[index, 'pos']))
                        assigned_players = [player for player in lineup.final_player if player is not None]

            # Perform tiebreakers based on expected value
            tb_row = np.where([x is None for x in lineup.final_player])[0][0]  # Which row to tiebreak
            # If there are no eligible players, put the final player in the slot as "Empty"
            if len(lineup.eligible_players[tb_row]) == 0:
                lineup.final_player[tb_row] = "Empty"
                continue
            tb = self.roster[self.roster.index.isin(lineup.eligible_players[tb_row])]  # Filter roster for those players
            tb = tb.assign(value=tb.is_playing * tb.value)  # Approximate their value
            try:
                best = tb.index[tb.value == max(tb.value)][0]  # Player with highest value
                self.logger.info("Optimizing {player} to {pos}".format(
                    player=best,
                    pos=lineup.pos[tb_row]))
            except IndexError:
                self.logger.warning("Failed assigning {}".format(lineup.pos[tb_row]))

            lineup.final_player[tb_row] = best
            assigned_players = [player for player in lineup['final_player'].unique() if player is not None]

        o = self.roster[['selected_position', 'player_id']].join(lineup.set_index('final_player'))
        o['pos'] = o['pos'].fillna("BN")
        o = o.rename(columns={"pos": "target_position",
                              "selected_position": "current_position"})
        self.logger.info("Finished optimizing lineup!")
        return o

    def set_lineup(self, target: pd.DataFrame) -> None:

        """
        This function sets your line using the Yahoo Fantasy API. It accepts a pd.DataFrame indexed
        by the player name with the following columns:

            current_position: the player's position in the lineup before
            target_position: where you _want_ the player to be (after)
            player_id: the 4 or 5 digit int that corresponds to the Yahoo player ID

        No point in trying to construct it with anything other than optimize_lineup()

        :param target: a dataframe describing a target lineup, probably generated by optimize_lineup()

        """

        target = target.rename(columns={"current_position": "c_pos",
                                        "target_position": "t_pos",
                                        "player_id": "pid"})

        #  Bench players that are in the wrong position
        move_back = []
        for row in target.itertuples():
            name = row.Index

            # If the player's current position and target position are the same, no need to do anything
            if row.c_pos == row.t_pos:
                continue

            # If the player is on the IL and needs to be moved to NA (or vice versa), do it in
            # one step, otherwise YFA gets mad about too many players on a given list.
            if row.c_pos in ["NA", "IL"] and row.t_pos in ["NA", "IL"]:
                try:
                    swap_dict = [{"player_id": int(row.pid), "selected_position": row.t_pos}]
                    self.team.change_positions(self.when, swap_dict)  # Bench them first
                    self.logger.info("Success: Switched {} {} -> {}".format(name, row.c_pos, row.t_pos))
                except RuntimeError as e:
                    self.logger.warning("Failed: Switched {} {} -> {}".format(name, row.c_pos, row.t_pos))
                    self.logger.warning(e)
            else:
                try:
                    # For all of the players that need to move, start by moving them to the bench
                    bench_dict = [{"player_id": int(row.pid), "selected_position": "BN"}]
                    self.team.change_positions(self.when, bench_dict)  # Bench them first
                    # Keep a list of the players that need to be moved back from the bench
                    move_back.append((name, row.pid, row.c_pos, row.t_pos))
                    self.logger.info("Success: {} ({} -> {}) to BN".format(name, row.c_pos, row.t_pos))
                except RuntimeError as e:
                    self.logger.warning("Failed: {} ({} -> {}) to BN".format(name, row.c_pos, row.t_pos))
                    self.logger.warning(e)

        # For the players that we moved to the bench, move them back to the target position
        for move in move_back:
            name, pid, c_pos, t_pos = move
            if t_pos == "BN":
                continue
            try:
                move_dict = [{"player_id": int(pid), "selected_position": t_pos}]
                self.team.change_positions(self.when, move_dict)  # Bench them first
                self.logger.info("Success: {} ({}) to {}".format(name, c_pos, t_pos))
            except RuntimeError as e:
                self.logger.warning("Failed: {} ({}) to {}".format(name, c_pos, t_pos))
                self.logger.warning(e)
        self.logger.info("Finished setting lineup!")

    def value_players(self, how="magic", log = True):
        if log:
            self.logger.info('Valuing players by "{}" method...'.format(how))
        # Value players based on their 2020 Steamer Projections
        if how == "steamer":
            # WAR projections for each player that are used to break ties
            # Define where to find WAR projections for each player
            batter_value_path = "data/proj_steamer_2020_b.csv"
            pitcher_value_path = "data/proj_steamer_2020_p.csv"

            player_values = pd.read_csv(
                batter_value_path  # Batter projections
            ).append(pd.read_csv(
                pitcher_value_path))  # Pitcher projections

            # If there are two players with the same name, only keep the
            # the player with the most projected ABs or IPs
            player_values = player_values.sort_values(by=['AB', 'IP'])
            player_values = player_values.drop_duplicates(subset=['Name'], keep='last')

            # Clean up the names
            player_values['name'] = player_values['Name'].map(self.cleanup_name)
            player_values['WAR'] = player_values['WAR'].fillna(0.1)  # Value unknowns slightly more than known nothings

            return player_values['WAR'][player_values['name'].isin(self.roster["name"])].tolist()

        if how == "lastmonth":
            pids = [pid for pid in self.roster['player_id']]
            stats = pd.DataFrame(self.league.player_stats(pids, req_type='lastmonth'))
            values = []
            for ops, era in zip(stats['OPS'], stats['ERA']):
                if not np.isnan(ops):
                    values.append(ops)
                elif era == 0:
                    values.append(100)
                else:
                    values.append(1/era)
            return values

        if how == "season":
            pids = [pid for pid in self.roster['player_id']]
            stats = pd.DataFrame(self.league.player_stats(pids, req_type='season'))
            values = []
            for wRAA, fip in zip(stats['wRAA'], stats['FIP']):
                if not np.isnan(wRAA):
                    values.append(wRAA)
                elif fip == 0:
                    values.append(100)
                else:
                    values.append(1/fip)
            return values

        if how == "magic":

            def mad(x):
                """
                Median absolute deviation
                (like a standard deviation except for non-parametric data)
                """
                x = np.array(x)
                return np.median(abs(x - np.median(x)))

            def norm_np(x):
                """
                Normalize a vector non-parametrically
                (distance from the median in MAD units)
                """
                x = np.array(x)
                return (x - np.median(x))/mad(x)

            week = self.league.current_week()
            total_weeks = 9  # Only valid for shortened 2020 season
            weight_season = (week/total_weeks * 0.75 + 0.25) * 1/2
            weight_month = (week/total_weeks * 0.75 + 0.25) * 1/2
            weight_proj = 1 - weight_season - weight_month

            # Calculate weights for season stats, this month stats, and steamer projections
            this_season = norm_np(self.value_players("season", log=False)) * weight_season
            this_month = norm_np(self.value_players("lastmonth", log=False)) * weight_month
            projections = norm_np(self.value_players("steamer", log=False)) * weight_proj

            return this_season + this_month + projections

        else:
            self.logger.info('Don\'t know how to value players by "{}"'.format(how))
            return None


if __name__ == "__main__":
    LEAGUE = "Chemical Hydrolysis League"
    token = update_oauth()
    key = find_league_key(token, 'mlb', LEAGUE)
    ros = Roster(key, values="magic")
    opt = ros.optimize_lineup()
    ros.set_lineup(opt)
