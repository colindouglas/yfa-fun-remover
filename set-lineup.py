from Roster import Roster

roster = Roster('398.l.29377')

lineup = roster.optimize_lineup()

roster.set_lineup(lineup)