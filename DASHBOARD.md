# Dashboard guide

This is the one guide to the dashboard. Live site: https://kushal-satya.github.io/pxd-sts-dashboard/
Repository: https://github.com/kushal-satya/pxd-sts-dashboard (branch `main`, published by GitHub Pages)

The dashboard is plain HTML, CSS and JavaScript with no framework and no build step. All the work happens in the browser on data files stored in this repository.

## 1. Files

| File | What it does |
|---|---|
| `index.html` | Page layout and fixed text: header, intro, filters, table, detail panel, the "About the data" and "Data and code" sections |
| `script.js` | Everything that moves: loads the data, fills the filters, filters and sorts the table, opens the detail panel, downloads CSV |
| `style.css` | Colours, layout, light and dark theme |
| `PxD_logo.png` | Logo and browser-tab icon |
| `data/index.json` | List of data parts, record count and build date. The page reads this first. |
| `data/final_varieties_hyperlinked.partN.json` | The records, split into parts small enough for GitHub |
| `data/coverage.json` | Which CSC minutes are held, for the minutes filter and coverage page |
| `tables/` | CSV and Excel downloads for analysts (`STS_India_varieties_FINAL.xlsx`; `STS_India_data_dictionary.csv` explains every column). The page does not read them. |
| `.github/build/` | Copies of the Python scripts that make `data/` and `tables/`. The site does not use them; the maintained copies are in the handover package, `02_code/dashboard/`. |

## 2. How the page works (`script.js`)

1. **Load.** `loadData()` reads `data/index.json`, fetches every part listed there, and `normalizeRecord()` turns each record into what the table needs.
2. **Filters.** `populateFilters()` fills the drop-downs from the data, so new crops, states or years appear by themselves. `applyFilters()` runs on every change.
3. **Default view.** The page opens on varieties whose stress tolerance is supported by at least one source (`DEFAULT_VIEW = { evidence: 'Supported' }`). "Show all varieties" clears it.
4. **Shareable links.** Every filter is kept in the address bar (`URL_KEYS`), so a filtered view can be shared as a link. Keys: `q` (search), `crop`, `state`, `stress`, `evidence`, `outcome`, `source`, `institution`, `contact`, `researched`, `seednet`, `from`, `to`, `minutes`, `disease`, `disease_basis`, `pest`, `pest_basis`, `yield`. Example: `?crop=Rice&stress=Drought&evidence=Supported`.
5. **Table.** Columns are in `COLUMNS`. Crop, Variety, Year, Stress tolerance and States are shown by default. Decision, Source, Seednet record, Developing institution, Publications, Disease resistance, Pest resistance and Yield can be switched on under "Columns".
6. **Detail panel.** Clicking a variety opens four tabs: **Record** (official CSC and Seednet data), **Stress and resistance** (grade per stress with numbered sources), **Contacts**, and **Publications and sources**. Each record has its own link (`#` + record id).
7. **Download CSV** saves the rows currently filtered.

What the stress grades mean is explained on the page under "About the data" and in `tables/STS_India_data_dictionary.csv` (`stress_confirmation_level`).

## 3. View it on your computer

```powershell
cd C:\Users\kd475\s\dashboard
python -m http.server 8000
```

Open http://localhost:8000 and stop the server with Ctrl+C. Opening `index.html` by double-clicking does not work: the browser will not let it load the data files.

## 4. Change the page

1. Edit `index.html` (text), `style.css` (look) or `script.js` (behaviour). Small text edits can also be made on GitHub in the browser.
2. If you changed `script.js` or `style.css`, raise the `?v=` value on their tags in `index.html` (for example `?v=20261111r2` to `?v=20261120r1`), so visitors' browsers fetch the new file.
3. Check it locally (section 3), then publish (section 6).

## 5. Update the data

The data is built in the handover package, not here. Full commands with explanations are in `01_docs/PIPELINE_RUNBOOK.md`, section 9. In short, from `STS_INDIA\02_code` with the virtual environment active and the build arguments `$a` set:

```powershell
python @a --stage build                                   # combine all research (free)
python @a --stage confirm --confirm-budget-usd 2          # only after new research (paid, about USD 0.001 per variety)
python @a --stage validate                                # must end with RESULT: PASS
python dashboard\export_final_tables.py C:\Users\kd475\s\work\final_varieties_hyperlinked.json C:\Users\kd475\s\work\tables --dictionary ..\01_docs\data_dictionary.csv
python dashboard\reshard.py C:\Users\kd475\s\work\final_varieties_hyperlinked.json C:\Users\kd475\s\dashboard
Copy-Item C:\Users\kd475\s\work\tables\* C:\Users\kd475\s\dashboard\tables -Force
```

**Copying `final_varieties_hyperlinked.json` into this folder does nothing.** The page reads only `data/`, which `reshard.py` writes. Data files need no `?v=` change: `index.json` is always fetched fresh.

## 6. Publish

```powershell
cd C:\Users\kd475\s\dashboard
git pull --rebase          # take any edits made on GitHub first
git add -A
git commit -m "Describe the change"
git push
```

The live site updates 1–2 minutes later. Press Ctrl+F5 if you still see the old version.

Check after publishing: the record count in the intro matches the build, there is no error banner, the year filter shows the expected range, and a few detail panels look right.

## 7. If something goes wrong

| Symptom | Cause and fix |
|---|---|
| "Loading the records." never finishes, or an error about `data/index.json` | The page was opened as a file, or `data/` is missing. Use the local server, or re-run `reshard.py`. |
| New data does not appear | You copied the JSON instead of running `reshard.py`, or forgot to push `data/`. |
| Style or behaviour change does not appear | Raise the `?v=` value in `index.html`; press Ctrl+F5. |
| `git push` rejected | Someone edited on GitHub. Run `git pull --rebase`, then push again. |
| GitHub warns a file is over 50 MB | Only a warning; files up to 100 MB are accepted. If one part exceeds 100 MB, `reshard.py` needs more parts. |
