# Depth validation set

22 openly licensed flood photos (all from Wikimedia Commons), each with a human-judged depth range in inches.
`manifest.json` has each photo's Commons file-page URL, its license and author, `true_low_in` / `true_high_in`,
and a one-sentence `basis` that names the reference object and where the waterline sits on it.

**The "truth" is approximate.** No depth in this set was measured. Each range is a person's estimate, made by
looking at a reference object in the photo (tire / wheel-hub height, bumper or number-plate height, an adult's
ankle / knee / waist). Ranges are deliberately conservative, usually 4–10 in wide; the two deepest scenes are
wider (10 in). Treat error numbers as "agreement with a careful human estimate", not as accuracy against ground truth.

Spread of judged midpoints: 8 shallow (≤8 in), 8 mid (8.5–18 in), 6 deep (>18 in; the deepest is judged at 32–42 in). Most photos show
roads or streets. Three are not on a road: two Houston apartment parking lots and one rural yard (the `basis`
says so).

Run the validation with

    DEMO_OFFLINE=false backend/.venv/bin/python scripts/validate_depth.py

which writes `results.json`: the mean absolute error against the judged midpoint, and how often the judged
midpoint fell inside the model's range. Report the sample size (n=22) honestly.

## Licenses

| License | Count | Sources |
|---|---|---|
| Public domain | 7 | FEMA (Del Vecchio, Quesada, Booher, Bahamonde, Nauman ×2), U.S. Army (1st Lt. Zachary West) |
| CC BY 2.0 | 7 | R. Crap Mariner ×3, McKay Savage ×2, edenpictures, US Army Africa |
| CC0 | 3 | Gary Houston, MarkBuckawicki, Vijayingarsal |
| CC BY-SA 4.0 | 3 | Paasikivi, Soulmender (Chinomso Nzenwa), Michael Slaten |
| CC BY-SA 2.0 | 2 | Philip Halling (Geograph), John Dal |

The images are 1280px-wide Commons thumbnails (one is 720px, the original's size). CC BY / BY-SA images need
attribution if redistributed: credit the author named in `manifest.json` and link the Commons URL. CC BY-SA
derivatives must keep the same license.
