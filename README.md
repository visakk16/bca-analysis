# Automatic BCA Plate Analyzer

This project automates the analysis of BCA protein assay data directly from Excel files.  
It reads plate reader absorbance data and an optional configuration file, calculates the standard curve, and outputs a results table and regression plot.

---

## Features
- Reads raw plate reader absorbance data (`.xlsx`)
- Reads optional configuration file for:
  - Standard concentrations
  - Sample names
  - Parameters (dilution factor, loading protein, loading volume)
- Automatically performs:
  - Linear regression for standard curve
  - R² and regression equation display
  - Sample concentration calculations
  - Volume calculations for loading and buffer
- Plots the standard curve
- Outputs a complete results DataFrame

---

## Requirements
- Python 3.9+
- Required packages (see `requirements.txt`):
  ```
  pandas
  numpy
  matplotlib
  scipy
  openpyxl
  ```

Install with:
```bash
pip install -r requirements.txt
```

---

## File Structure
```
bca_analysis/
│
├── analyze_bca_plate.py        # Main script
├── example_data/
│   ├── example_absorbance.xlsx
│   └── example_config.xlsx
├── README.md
├── requirements.txt
└── .gitignore
```

---

## Example Usage

```bash
python analyze_bca_plate.py
```

You can update the paths inside the script:
```python
absorbance_file = '/Users/visakkumar/Downloads/20251021_BCA_L1RIME_NC.xlsx'
config_file = '/Users/visakkumar/Downloads/bca_config.xlsx'
```

After running, the program will:
1. Print the regression equation and R².
2. Display the standard curve.
3. Print the full concentration results table.

---

## Example Config File Format
**Columns:**
- `Parameter` — possible values: `dilution_factor`, `loading_protein`, `loading_volume`
- `Value` — numeric value for that parameter  
- `Standard Concentration (µg/ml)` — optional list of known standards  
- `Sample Names` — optional list of sample names

Example:

| Parameter         | Value | Standard Concentration (µg/ml) | Sample Names   |
|-------------------|--------|-------------------------------|----------------|
| dilution_factor   | 8      | 2000                          | Sample 1       |
| loading_protein   | 30     | 1750                          | Sample 2       |
| loading_volume    | 40     | 1500                          | Sample 3       |
|                   |        | 1250                          | Sample 4       |
|                   |        | 1000                          | Sample 5       |
|                   |        | 750                           | Sample 6       |
|                   |        | 500                           | Sample 7       |
|                   |        | 250                           | Sample 8       |
|                   |        | 0                             | Sample 9       |

---

## Output Example

After running, you’ll see:

```
Configuration Parameters:
Dilution Factor: 8.0
Loading Protein (µg): 30.0
Loading Volume (µl): 40.0

Concentration (µg/ml) = (absorbance - intercept) / slope
R² = 0.9987
```

…and a plotted standard curve followed by a DataFrame of results.

---

## 🧠 Author
**Visak Kumar**  
Created to streamline analysis of BCA protein assays using Python.

---
