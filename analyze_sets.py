import os
import re
from collections import Counter

# Configuration: supported file extensions
FILE_EXTENSIONS = {'.txt', '.md'}

def get_files(directory):
    """Recursively find all text files in the directory."""
    file_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in FILE_EXTENSIONS:
                file_list.append(os.path.join(root, file))
    return file_list

def clean_text(text):
    """Normalize text by stripping whitespace and converting to lowercase."""
    return text.strip().lower()

def parse_line(line):
    """
    Attempts to parse a line into (Artist, Track).
    Assumes standard formats like: 'Artist - Track' or 'Artist -- Track'
    """
    # clear out any timestamps (e.g., [00:00], 10:30, etc) if they exist at the start
    line = re.sub(r'^\[?\d{1,2}:\d{2}\]?\s*', '', line)
    
    # Common separators
    separators = [" -- ", " - ", " – "] 
    
    for sep in separators:
        if sep in line:
            parts = line.split(sep, 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                track = parts[1].strip()
                # formatting for consistency (Title Case)
                return artist.title(), track.title()
    
    return None, None

def analyze_setlists(directory):
    artist_counter = Counter()
    track_counter = Counter()
    
    files = get_files(directory)
    print(f"Found {len(files)} files to analyze...")

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    
                    artist, track = parse_line(line)
                    if artist and track:
                        artist_counter[artist] += 1
                        # We track the specific combo of Artist - Track to avoid generic track names
                        full_track_name = f"{artist} - {track}"
                        track_counter[full_track_name] += 1
        except Exception as e:
            print(f"Could not read {file_path}: {e}")

    return artist_counter, track_counter

if __name__ == "__main__":
    # Use the current directory where the script is running
    target_directory = os.getcwd()
    
    top_artists, top_tracks = analyze_setlists(target_directory)

    print("\n" + "="*30)
    print("TOP 20 ARTISTS")
    print("="*30)
    for i, (artist, count) in enumerate(top_artists.most_common(20), 1):
        print(f"{i}. {artist} ({count} plays)")

    print("\n" + "="*30)
    print("TOP 20 TRACKS")
    print("="*30)
    for i, (track, count) in enumerate(top_tracks.most_common(20), 1):
        print(f"{i}. {track} ({count} plays)")