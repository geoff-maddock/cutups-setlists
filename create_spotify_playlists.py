#!/usr/bin/env python3
"""
create_spotify_playlists.py

Reads DJ setlist files from the cutups-setlists repo and creates
corresponding Spotify playlists via the Spotify Web API.

Usage:
    python create_spotify_playlists.py                       # process all playlists
    python create_spotify_playlists.py --year 2024           # only 2024
    python create_spotify_playlists.py --folder ideas        # only the ideas folder
    python create_spotify_playlists.py --dry-run             # search only, no playlist creation
    python create_spotify_playlists.py --private             # create as private playlists
    python create_spotify_playlists.py --skip-existing       # skip if playlist name exists
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("Missing dependency: spotipy")
    print(f"Run: {sys.executable} -m pip install -r requirements.txt")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("Missing dependency: python-dotenv")
    print(f"Run: {sys.executable} -m pip install -r requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_DIR = Path(__file__).resolve().parent
FILE_EXTENSIONS = {".txt", ".md"}
SEPARATORS = [" -- ", " - ", " – "]
TIMESTAMP_RE = re.compile(r"^\[?\d{1,2}:\d{2}\]?\s*")
# Match numbered prefixes like "1 " or "12 " at start of line
NUMBER_PREFIX_RE = re.compile(r"^\d+\s+")
SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private"
SEARCH_DELAY = 0.1  # seconds between Spotify search calls
BATCH_SIZE = 100  # max tracks per Spotify add-to-playlist call

# Headers that indicate column order is track-first (rare)
TRACK_FIRST_HEADERS = {"#track - #artist"}


class SpotifyAccessError(RuntimeError):
    """Raised when the Spotify app account cannot access the API."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def detect_header(first_line: str) -> dict:
    """Detect the header format and return parsing metadata."""
    lower = first_line.strip().lower()
    info = {"track_first": False, "has_release": False, "is_header": lower.startswith("#")}
    if lower in TRACK_FIRST_HEADERS:
        info["track_first"] = True
    if "#release" in lower:
        info["has_release"] = True
    return info


def parse_line(line: str, track_first: bool = False) -> tuple:
    """
    Parse a single line into (artist, track).
    Returns (None, None) if unparseable.
    """
    # Strip timestamps at start
    line = TIMESTAMP_RE.sub("", line)
    # Strip numbered prefixes
    line = NUMBER_PREFIX_RE.sub("", line)

    for sep in SEPARATORS:
        if sep in line:
            parts = line.split(sep)
            if len(parts) >= 2:
                a = parts[0].strip()
                t = parts[1].strip()
                # For 3-column format (#artist - #track - #release), ignore release
                if track_first:
                    a, t = t, a
                if a and t:
                    return a, t
    return None, None


def parse_setlist_file(filepath: Path) -> tuple:
    """
    Parse a setlist file and return (header_info, tracks).
    tracks is a list of (artist, track) tuples.
    """
    tracks = []
    header_info = {}

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  Could not read {filepath}: {e}")
        return header_info, tracks

    if not lines:
        return header_info, tracks

    # Check first line for header
    header_info = detect_header(lines[0])
    start = 1 if header_info.get("is_header") else 0

    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        # Skip comment-like or metadata lines
        if line.startswith("#") or line.startswith("//"):
            continue
        artist, track = parse_line(line, track_first=header_info.get("track_first", False))
        if artist and track:
            tracks.append((artist, track))

    return header_info, tracks


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def get_setlist_files(
    base_dir: Path,
    year: str | None = None,
    folder: str | None = None,
) -> list[Path]:
    """Collect setlist files, optionally filtered by year or folder."""
    if folder:
        target = base_dir / folder
        if not target.is_dir():
            print(f"Folder not found: {target}")
            sys.exit(1)
        search_dir = target
    elif year:
        target = base_dir / year
        if not target.is_dir():
            print(f"Year folder not found: {target}")
            sys.exit(1)
        search_dir = target
    else:
        search_dir = base_dir

    files = []
    for root, dirs, filenames in os.walk(search_dir):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(filenames):
            if Path(fn).suffix.lower() in FILE_EXTENSIONS:
                files.append(Path(root) / fn)

    # Sort by path for deterministic ordering
    files.sort()
    return files


# ---------------------------------------------------------------------------
# Playlist naming
# ---------------------------------------------------------------------------

def playlist_name_from_file(filepath: Path) -> tuple:
    """
    Derive a Spotify playlist name and date from a setlist filename.
    Returns (name, date_str).
    """
    stem = filepath.stem  # e.g. "2024-04-17-Murderpact-KillAlters-ClubPittsburgh-Livemix"

    # Try to extract date prefix (YYYY-MM-DD)
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", stem)
    if date_match:
        date_str = date_match.group(1)
        event_part = date_match.group(2)
    else:
        date_str = ""
        event_part = stem

    # Convert hyphens to spaces for readability
    event_name = event_part.replace("-", " ")

    # Build the prefixed name
    if date_str:
        name = f"Cutups - {date_str} {event_name}"
    else:
        name = f"Cutups - {event_name}"

    return name, date_str


# ---------------------------------------------------------------------------
# Spotify helpers
# ---------------------------------------------------------------------------

def init_spotify(dry_run: bool = False) -> tuple[spotipy.Spotify, str | None]:
    """Initialize Spotify and return the client plus optional user id."""
    load_dotenv(REPO_DIR / ".env")

    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

    if not client_id or not client_secret:
        print("ERROR: Missing Spotify credentials.")
        print("Copy .env.example to .env and fill in your credentials.")
        print("Get them at https://developer.spotify.com/dashboard")
        sys.exit(1)

    if dry_run:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        return spotipy.Spotify(auth_manager=auth_manager), None

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SPOTIFY_SCOPES,
        cache_path=str(REPO_DIR / ".cache"),
    )

    sp = spotipy.Spotify(auth_manager=auth_manager)

    # Verify authentication
    try:
        user = sp.current_user()
        print(f"Authenticated as: {user['display_name']} ({user['id']})")
        return sp, user["id"]
    except Exception as e:
        if "Active premium subscription required for the owner of the app" in str(e):
            print("Authentication failed: Spotify rejected this app during user auth.")
            print("The Spotify account that owns this developer app needs an active Premium subscription.")
            print("Dry runs use app-only search auth, but live playlist creation still requires a working app owner account.")
            sys.exit(1)
        print(f"Authentication failed: {e}")
        sys.exit(1)


def is_premium_gate_error(error: Exception) -> bool:
    """Return True when Spotify rejects the app due to account subscription state."""
    return "Active premium subscription required for the owner of the app" in str(error)


def search_track(sp: spotipy.Spotify, artist: str, track: str) -> str | None:
    """
    Search Spotify for a track. Returns the track URI if found, else None.
    Tries a structured query first, then falls back to a simple query.
    """
    # Clean up common annotations that hurt search
    clean_track = re.sub(r"\(.*?(remix|refix|edit|vip|bootleg).*?\)", "", track, flags=re.IGNORECASE).strip()
    clean_artist = re.sub(r"\s*/\s*", " ", artist)  # "Nick Cave/Blixa" -> "Nick Cave Blixa"

    # Attempt 1: structured query
    q = f"artist:{clean_artist} track:{clean_track}"
    try:
        results = sp.search(q=q, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"]
    except Exception as e:
        if is_premium_gate_error(e):
            raise SpotifyAccessError(
                "Spotify rejected API access for this developer app. "
                "The app owner account needs an active Premium subscription, "
                "and Spotify may take a few hours to re-enable access after the status changes."
            ) from e
        pass

    time.sleep(SEARCH_DELAY)

    # Attempt 2: simple combined query (catches more loose matches)
    q = f"{clean_artist} {clean_track}"
    try:
        results = sp.search(q=q, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"]
    except Exception as e:
        if is_premium_gate_error(e):
            raise SpotifyAccessError(
                "Spotify rejected API access for this developer app. "
                "The app owner account needs an active Premium subscription, "
                "and Spotify may take a few hours to re-enable access after the status changes."
            ) from e
        pass

    # Attempt 3: try with original track name if we cleaned it
    if clean_track != track:
        time.sleep(SEARCH_DELAY)
        q = f"{clean_artist} {track}"
        try:
            results = sp.search(q=q, type="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            if items:
                return items[0]["uri"]
        except Exception as e:
            if is_premium_gate_error(e):
                raise SpotifyAccessError(
                    "Spotify rejected API access for this developer app. "
                    "The app owner account needs an active Premium subscription, "
                    "and Spotify may take a few hours to re-enable access after the status changes."
                ) from e
            pass

    return None


def get_existing_playlist_names(sp: spotipy.Spotify) -> set[str]:
    """Fetch all playlist names for the current user."""
    names = set()
    offset = 0
    while True:
        playlists = sp.current_user_playlists(limit=50, offset=offset)
        items = playlists.get("items", [])
        if not items:
            break
        for pl in items:
            if pl and pl.get("name"):
                names.add(pl["name"])
        offset += 50
        if offset >= playlists.get("total", 0):
            break
    return names


def create_playlist(
    sp: spotipy.Spotify,
    user_id: str,
    name: str,
    description: str,
    track_uris: list[str],
    public: bool = True,
) -> str | None:
    """Create a Spotify playlist and add tracks. Returns playlist URL."""
    try:
        playlist = sp.user_playlist_create(
            user=user_id,
            name=name,
            public=public,
            description=description,
        )
    except Exception as e:
        print(f"  Failed to create playlist '{name}': {e}")
        return None

    playlist_id = playlist["id"]
    playlist_url = playlist["external_urls"]["spotify"]

    # Add tracks in batches of 100
    for i in range(0, len(track_uris), BATCH_SIZE):
        batch = track_uris[i : i + BATCH_SIZE]
        try:
            sp.playlist_add_items(playlist_id, batch)
        except Exception as e:
            print(f"  Failed to add tracks batch to '{name}': {e}")

    return playlist_url


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create Spotify playlists from cutups-setlists archive."
    )
    parser.add_argument("--year", help="Process only files from this year (e.g. 2024)")
    parser.add_argument("--folder", help="Process only files in this subfolder (e.g. ideas)")
    parser.add_argument("--dry-run", action="store_true", help="Search tracks but don't create playlists")
    parser.add_argument("--private", action="store_true", help="Create playlists as private")
    parser.add_argument("--skip-existing", action="store_true", help="Skip playlists that already exist by name")
    args = parser.parse_args()

    print("=" * 60)
    print("  Cutups Setlists -> Spotify Playlist Creator")
    print("=" * 60)

    # Discover files
    files = get_setlist_files(REPO_DIR, year=args.year, folder=args.folder)
    if not files:
        print("No setlist files found.")
        sys.exit(0)

    print(f"Found {len(files)} setlist files to process.")

    if args.dry_run:
        print("DRY RUN: will search Spotify but not create playlists.\n")
    else:
        print()

    # Init Spotify
    sp, user_id = init_spotify(dry_run=args.dry_run)

    # Pre-fetch existing playlists if skip-existing is set
    existing_names = set()
    if args.skip_existing and not args.dry_run:
        print("Fetching existing playlists...")
        existing_names = get_existing_playlist_names(sp)
        print(f"Found {len(existing_names)} existing playlists.\n")

    # Stats
    total_playlists_created = 0
    total_tracks_found = 0
    total_tracks_missed = 0
    total_playlists_skipped = 0
    report_lines = []

    for idx, filepath in enumerate(files, 1):
        rel_path = filepath.relative_to(REPO_DIR)
        name, date_str = playlist_name_from_file(filepath)
        print(f"[{idx}/{len(files)}] {rel_path}")

        # Parse the file
        header_info, tracks = parse_setlist_file(filepath)
        if not tracks:
            print(f"  No tracks parsed, skipping.")
            report_lines.append(f"\n## {rel_path}\nNo tracks parsed.\n")
            continue

        print(f"  Parsed {len(tracks)} tracks.")

        # Check skip-existing
        if args.skip_existing and name in existing_names:
            print(f"  Playlist '{name}' already exists, skipping.")
            total_playlists_skipped += 1
            continue

        # Search Spotify for each track
        found_uris = []
        missed = []
        for artist, track in tracks:
            try:
                uri = search_track(sp, artist, track)
            except SpotifyAccessError as e:
                print(f"ERROR: {e}")
                sys.exit(1)
            if uri:
                found_uris.append(uri)
                total_tracks_found += 1
            else:
                missed.append(f"{artist} - {track}")
                total_tracks_missed += 1
            time.sleep(SEARCH_DELAY)

        print(f"  Spotify: {len(found_uris)} found, {len(missed)} not found.")

        # Report
        report_entry = f"\n## {rel_path}\n"
        report_entry += f"Playlist: {name}\n"
        report_entry += f"Tracks parsed: {len(tracks)} | Found: {len(found_uris)} | Missed: {len(missed)}\n"
        if missed:
            report_entry += "Not found:\n"
            for m in missed:
                report_entry += f"  - {m}\n"

        # Create playlist (unless dry-run or no tracks found)
        if not args.dry_run:
            assert user_id is not None
            if found_uris:
                description = f"DJ Cutups setlist from {date_str}. Auto-generated from cutups-setlists archive." if date_str else "DJ Cutups setlist. Auto-generated from cutups-setlists archive."
                url = create_playlist(
                    sp,
                    user_id,
                    name,
                    description,
                    found_uris,
                    public=not args.private,
                )
                if url:
                    total_playlists_created += 1
                    report_entry += f"Spotify URL: {url}\n"
                    print(f"  Created: {url}")
                else:
                    print(f"  Failed to create playlist.")
            else:
                print(f"  No tracks found on Spotify, skipping playlist creation.")
        else:
            report_entry += "(dry run - no playlist created)\n"

        report_lines.append(report_entry)

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Files processed:    {len(files)}")
    if not args.dry_run:
        print(f"  Playlists created:  {total_playlists_created}")
        print(f"  Playlists skipped:  {total_playlists_skipped}")
    print(f"  Tracks found:       {total_tracks_found}")
    print(f"  Tracks not found:   {total_tracks_missed}")
    if total_tracks_found + total_tracks_missed > 0:
        hit_rate = total_tracks_found / (total_tracks_found + total_tracks_missed) * 100
        print(f"  Hit rate:           {hit_rate:.1f}%")
    print("=" * 60)

    # Write report
    report_path = REPO_DIR / "spotify_import_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Spotify Import Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'DRY RUN' if args.dry_run else 'LIVE RUN'}\n")
        f.write(f"Files: {len(files)} | Created: {total_playlists_created} | ")
        f.write(f"Found: {total_tracks_found} | Missed: {total_tracks_missed}\n")
        f.write("".join(report_lines))
    print(f"\nDetailed report: {report_path}")


if __name__ == "__main__":
    main()
