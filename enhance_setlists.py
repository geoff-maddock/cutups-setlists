#!/usr/bin/env python3
"""Generate enhanced versions of setlist files.

For each ``*.txt`` file in the repository this script creates two files:
``<name>_enhanced.tsv`` with search links for tracks and artists,
``<name>_suggestions.txt`` listing other tracks to explore.
"""
import os
import re
import urllib.parse


def parse_tracks(path):
    """Return a list of (artist, title) tuples."""
    tracks = []
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            line = re.sub(r'^\d+\s+', '', line)
            parts = [p.strip() for p in line.split(' - ', 2)]
            if len(parts) < 2:
                continue
            artist, title = parts[0], parts[1]
            tracks.append((artist, title))
    return tracks


def search_url(kind, artist, title=''):
    """Return a search URL for the given service."""
    query = f"{artist} {title}".strip()
    q = urllib.parse.quote_plus(query)
    if kind == 'bandcamp':
        return f"https://bandcamp.com/search?q={q}"
    if kind == 'youtube':
        return f"https://www.youtube.com/results?search_query={q}"
    if kind == 'soundcloud':
        return f"https://soundcloud.com/search?q={q}"
    if kind == 'artist':
        q = urllib.parse.quote_plus(f"{artist} official site")
        return f"https://duckduckgo.com/?q={q}"
    return ''


def enhance_file(path):
    tracks = parse_tracks(path)
    if not tracks:
        return
    base, _ = os.path.splitext(path)
    enhanced_path = base + '_enhanced.tsv'
    suggestions_path = base + '_suggestions.txt'

    with open(enhanced_path, 'w', encoding='utf-8') as out:
        out.write('artist\ttitle\tbandcamp\tyoutube\tsoundcloud\tartist_site\n')
        for artist, title in tracks:
            out.write(
                f"{artist}\t{title}\t{search_url('bandcamp', artist, title)}\t"
                f"{search_url('youtube', artist, title)}\t"
                f"{search_url('soundcloud', artist, title)}\t"
                f"{search_url('artist', artist)}\n")

    artists = sorted({a for a, _ in tracks})
    with open(suggestions_path, 'w', encoding='utf-8') as out:
        out.write('Suggested additional tracks:\n')
        for artist in artists:
            out.write(f"Explore more from {artist}: {search_url('bandcamp', artist)}\n")


def main(root='.'):
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith('.txt') and not fname.endswith('_enhanced.txt') and \
               not fname.endswith('_suggestions.txt') and not fname.startswith('.'):
                enhance_file(os.path.join(dirpath, fname))


if __name__ == '__main__':
    main()
