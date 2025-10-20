# Cutups - Setlists

Repository of setlists for live sets and recorded mixes.

## Formatting
A mix of txt, csv and other.

**Headers** delineated with
```
#column1, #column2, #column3 ...
```

**Title** formated such as 
```
YYYY-MM-DD-EVENT-TYPE
ex. 2018-01-01-Lazercrunk_Ft_Starkey-Club.txt
```

https://linktr.ee/cutups

## Notes
This is an archive of setlists from mixes and live gigs by dj Cutups (Geoff Maddock)
As a DJ, I want to spread the word about music that I love, and that involves giving credit to the artists who create the music.
This archive is far from complete, but contains everything that I've managed to keep track of.  
Big shouts to the history function in Serato DJ.

## Enhanced setlists

Use `enhance_setlists.py` to generate versions of each setlist with helpful search links. Running the script will create `<setlist>_enhanced.tsv` with Bandcamp, YouTube, SoundCloud and artist site search URLs as well as `<setlist>_suggestions.txt` containing links to explore more music from each artist.

```bash
python3 enhance_setlists.py
```
