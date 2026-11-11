# Seed Varieties of India — STS Dashboard

**Live dashboard: https://kushal-satya.github.io/pxd-sts-dashboard/**

An interactive catalogue of 13,884 crop varieties released in India, built by Precision Development (PxD). It covers 4,819 varieties from the Central Sub-Committee (CSC) minutes and 9,065 further varieties from Seednet. For each variety it shows official details, stress tolerance with source links, publications and breeder contacts.

## Download the data

The [`tables/`](tables/) folder holds the full dataset as CSV files and as one Excel workbook (`STS_India_varieties_FINAL.xlsx`). `STS_India_data_dictionary.csv` explains every column.

## What is in this repository

| Path | Contents |
|---|---|
| `index.html`, `script.js`, `style.css`, `PxD_logo.png` | The website |
| `data/` | Records the website loads |
| `tables/` | Download tables |
| `.github/build/` | Scripts used to build `data/` and `tables/` (not needed to view the site) |

To view it locally, run `python -m http.server 8000` in this folder and open http://localhost:8000.

## Notes

Stress-tolerance findings come from automated web research and are graded by how many independent sources confirm them. Check the linked sources before relying on a claim.
