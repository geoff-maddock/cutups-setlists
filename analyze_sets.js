const fs = require('fs');
const path = require('path');

// Configuration: supported file extensions
const FILE_EXTENSIONS = new Set(['.txt', '.md']);

function getFiles(directory) {
    let fileList = [];
    const files = fs.readdirSync(directory);

    for (const file of files) {
        const fullPath = path.join(directory, file);
        const stat = fs.statSync(fullPath);

        if (stat.isDirectory()) {
            fileList = fileList.concat(getFiles(fullPath));
        } else {
            if (FILE_EXTENSIONS.has(path.extname(file).toLowerCase())) {
                fileList.push(fullPath);
            }
        }
    }
    return fileList;
}

function parseLine(line) {
    // clear out any timestamps (e.g., [00:00], 10:30, etc) if they exist at the start
    line = line.replace(/^\[?\d{1,2}:\d{2}\]?\s*/, '');

    // Common separators
    const separators = [" -- ", " - ", " – "];

    for (const sep of separators) {
        if (line.includes(sep)) {
            const parts = line.split(sep);
            // We only take the first split as the separator between artist and track
            // But wait, python code did: parts = line.split(sep, 1)
            // JS split limit works differently (it truncates the array), so we need to be careful.
            // Actually, if we just find the index of the first separator, we can slice.

            const sepIndex = line.indexOf(sep);
            if (sepIndex !== -1) {
                const artist = line.substring(0, sepIndex).trim();
                const track = line.substring(sepIndex + sep.length).trim();

                if (artist && track) {
                    return {
                        artist: toTitleCase(artist),
                        track: toTitleCase(track)
                    };
                }
            }
        }
    }
    return null;
}

function toTitleCase(str) {
    return str.replace(
        /\w\S*/g,
        function (txt) {
            return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
        }
    );
}

function analyzeSetlists(directory, startYear = null, endYear = null) {
    const artistCounter = {};
    const trackCounter = {};

    let files = getFiles(directory);

    if (startYear !== null || endYear !== null) {
        files = files.filter(filePath => {
            const fileName = path.basename(filePath);
            const match = fileName.match(/^(\d{4})/);
            if (match) {
                const fileYear = parseInt(match[1], 10);
                if (startYear !== null && fileYear < startYear) return false;
                if (endYear !== null && fileYear > endYear) return false;
                return true;
            }
            return false;
        });
        
        let msg = "Filtering for files";
        if (startYear) msg += ` from ${startYear}`;
        if (endYear) msg += ` to ${endYear}`;
        console.log(msg + "...");
    }

    console.log(`Found ${files.length} files to analyze...`);

    for (const filePath of files) {
        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const lines = content.split(/\r?\n/);

            for (let line of lines) {
                line = line.trim();
                if (!line) continue;

                const result = parseLine(line);
                if (result) {
                    const { artist, track } = result;
                    if (artist.startsWith('#Artist')) continue;

                    artistCounter[artist] = (artistCounter[artist] || 0) + 1;

                    const fullTrackName = `${artist} - ${track}`;
                    trackCounter[fullTrackName] = (trackCounter[fullTrackName] || 0) + 1;
                }
            }
        } catch (e) {
            console.log(`Could not read ${filePath}: ${e.message}`);
        }
    }

    return { artistCounter, trackCounter };
}

// Helper to sort and get top N
function getTop(counter, n) {
    return Object.entries(counter)
        .sort((a, b) => b[1] - a[1])
        .slice(0, n);
}

// Main execution
const targetDirectory = process.cwd();

// Parse arguments
const args = process.argv.slice(2);

let startYear = null;
const startYearIndex = args.indexOf('--start-year');
if (startYearIndex !== -1 && args[startYearIndex + 1]) {
    startYear = parseInt(args[startYearIndex + 1], 10);
}

let endYear = null;
const endYearIndex = args.indexOf('--end-year');
if (endYearIndex !== -1 && args[endYearIndex + 1]) {
    endYear = parseInt(args[endYearIndex + 1], 10);
}

let limit = 20;
const limitIndex = args.indexOf('--limit');
if (limitIndex !== -1 && args[limitIndex + 1]) {
    limit = parseInt(args[limitIndex + 1], 10);
}

const { artistCounter, trackCounter } = analyzeSetlists(targetDirectory, startYear, endYear);

console.log("\n" + "=".repeat(30));
console.log(`TOP ${limit} ARTISTS`);
console.log("=".repeat(30));

const topArtists = getTop(artistCounter, limit);
topArtists.forEach((item, index) => {
    console.log(`${index + 1}. ${item[0]} (${item[1]} plays)`);
});

console.log("\n" + "=".repeat(30));
console.log(`TOP ${limit} TRACKS`);
console.log("=".repeat(30));

const topTracks = getTop(trackCounter, limit);
topTracks.forEach((item, index) => {
    console.log(`${index + 1}. ${item[0]} (${item[1]} plays)`);
});
