import mlbgame
import yahoo_fantasy_api as yfa
import pandas as pd
from unidecode import unidecode
from datetime import datetime


class Roster:
    def __init__(self, oauth, league_key):

        # Confirm that oauth is valid
        assert oauth.token_is_valid()
        self.oauth = oauth

        # Parameters that map a Roster to a YFA object
        self.league_key = league_key
        self.league = yfa.league.League(self.oauth, league_key)
        self.team = yfa.team.Team(self.oauth, self.league.team_key())

        # A "roster" is all of the players that are on a team
        self.roster = pd.DataFrame(self.team.roster())

        # Define where to find WAR projections for each player
        batter_values = pd.read_csv("data/proj_steamer_2020_b.csv")
        pitcher_values = pd.read_csv("data/proj_steamer_2020_p.csv")
        self.player_values = batter_values.append(pitcher_values)

        # If there are two players with the same name, only keep the
        # the player with the most projected ABs or IPs
        self.player_values = self.player_values.sort_values(by=['AB', 'IP'])
        self.player_values = self.player_values.drop_duplicates(subset=['Name'], keep='last')

        # Clean up the player names for easier joins
        self.roster['name'] = self.roster['name'].map(self.cleanup_name)
        self.player_values['Name'] = self.player_values['Name'].map(self.cleanup_name)[['name', 'WAR']]

        self.projected_war = self.roster.join(self.player_values.set_index('Name'), on=['name'], how='left')
        self.projected_war = self.projected_war[['name', 'WAR']].set_index('name').to_dict('index')

        self.positions = self.league.positions()
        self.batter_positions = []
        self.pitcher_positions = []
        self.probables = self.fetch_probables(datetime.today().year, datetime.today().month, datetime.today().day + 1)

        for entry in self.positions.items():
            position, info = entry
            if position in ['NA', 'BN', 'IL']:  # Don't have position_type
                pass
            elif info['position_type'] == 'B':
                for _ in range(info['count']):
                    self.batter_positions.append(position)
            elif info['position_type'] == 'P':
                for _ in range(info['count']):
                    self.pitcher_positions.append(position)

        self.potential_batters = {position: [] for position in self.batter_positions}

    def make_ineligible(self, name):
        '''
        Removes a batter from the list of potential batters,
        so they aren't assigned to multiple positions

        :param name: the name of the player
        :return: None
        '''

        for key in self.potential_batters.keys():
            if name in self.potential_batters[key]:
                self.potential_batters[key].remove(name)

    def fetch_probables(self, year: int, month: int, day: int) -> dict:
        '''
        Gets a list of probable starters for a given date
        from MLB GameDay API

        :param year: integer year of given date
        :param month: integer month of given date
        :param day: integer day of given date
        :return: a dict with keys "pitchers" containing probable pitchers
            and "teams" containing teams that are playing
        '''

        # Get probable starters
        pitchers = []
        teams = []
        for game in mlbgame.day(year, month, day):
            if game.game_status == 'PRE_GAME':
                if len(game.p_pitcher_home) > 2:
                    pitchers.append(game.p_pitcher_home)
                if len(game.p_pitcher_away) > 2:
                    pitchers.append(game.p_pitcher_away)
        teams.append(game.home_team)
        teams.append(game.away_team)
        pitchers = map(self.cleanup_name, pitchers)
        out = dict()
        out["pitchers"] = pitchers
        out["teams"] = teams
        return out

    @staticmethod
    def cleanup_name(x: str) -> str:
        '''
        Removes accents/hyphens/periods from a player's name for easier joins
        '''
        o = unidecode(x)
        o = o.replace('-', ' ')
        o = o.replace('.', '')
        return o






# # Figure out positions in the league
# positions = league.positions()
#
#
#
# # Get a list of the players, including whether they're playing
#
# roster['name'] = roster['name'].map(cleanup_name)
#

#
# # Determine the potential batters for each position
#
# batters_final     = {position: [] for position in batter_positions}
# for position in batter_positions:
#     for name in roster.index:
#         if position in roster.loc[name, ]['eligible_positions']:
#             batters_potential[position].append(name)
#
# # Function to remove an assigned batter from all other positions
#
#
#
# while 1 in list(map(len, batters_potential.values())):
#     for position in batter_positions:
#         # If there's only one valid player in that position
#         if len(batters_potential[position]) == 1:
#             name = batters_potential[position][0]
#             # Add that player to the final roster
#             batters_final[position] = name
#             # Remove the player from potential other positions
#             make_ineligible(name)

