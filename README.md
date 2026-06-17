# BCA Plate Analyzer

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://bca-analysis-vk.streamlit.app/)

A web app for automated BCA protein assay analysis directly from plate reader output.
No installation required — runs in the browser.

## Usage

1. Open the app: [bca-analysis-vk.streamlit.app](https://bca-analysis-vk.streamlit.app/)
2. Upload your absorbance Excel file (`.xlsx`) exported from your plate reader
3. Set your parameters:
   - **Dilution factor** — how much your samples were diluted before the assay
   - **Total loading volume (µl)** — sum of sample + buffer per lane
   - **Target protein to load (µg)** — the app back-calculates the sample volume needed
   - **Sample names** — paste one per line to label your samples (optional)
4. Click **Run analysis**
5. Download the results as a CSV

## What it does

- Reads a 96-well plate layout from your `.xlsx` file
- Fits a linear standard curve to the BCA standards (columns B & C)
- Calculates protein concentration for each sample with dilution correction
- Computes sample and buffer volumes needed to load your target protein amount
- Displays R², slope, intercept, and the standard curve plot

## Expected plate layout

| Column | Contents |
|--------|----------|
| B–C | Standards (rows A–H), 9-point series including blank |
| D–E | Sample set 1 (duplicates) |
| F–G | Sample set 2 (duplicates) |
| H–I | Sample set 3 (duplicates) |
| J–K | Sample set 4 (duplicates) |

## Output columns

| Column | Description |
|--------|-------------|
| Sample | Sample name or well ID |
| Absorbance | Mean absorbance of duplicates |
| Concentration (µg/ml) | From standard curve (undiluted) |
| µg/ml (with dilution) | After applying dilution factor |
| µg/µl | Converted for volume calculation |
| Sample Volume (µl) | Volume needed to hit target protein |
| 2X Sample Volume (µl) | For 2X loading buffer prep |
| Buffer Volume (µl) | Volume of loading buffer to add |

## Author

Visak Kumar