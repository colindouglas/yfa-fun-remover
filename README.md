# YFA Fun Remover

This is a straightforward Python script to optimally set your Yahoo! Fantasy Baseball team's lineup, using the Yahoo
Fantasy API. The only input required is the league name.

The YFA Fun Remover will set your lineup following a few simple rules:
* Players listed as NA/IL stay there
* Positions with only one eligible player are filled by that player always 
    * e.g., you only have one catcher so he plays every day
* Positions that have multiple eligible players are filled:
    * By players who's team is playing that day, then...
    * By the player with the most projected value, using the Steamer 2020 projections

It doesn't necessarily get you to the optimal lineup, but it gets you close.

Edge cases where it fails:
* You have an pretty good 2B, an amazing 2B/SS, and a mediocre SS. This script will play the amazing 2B/SS at 2B, 
forcing you to play the mediocre SS at SS and benching the pretty good 2B.
* A pitcher is listed on the IL but is a probable starter for tomorrow.
* Adding/removing players to the lineup (it doesn't do it)
