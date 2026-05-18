import pandas as pd
import numpy as np

# Create synthetic absorbance data matching indices used in bca code.py
# The original script uses iloc slices - we'll create a 9x11 sheet so indexing works
rows = 9
cols = 11
np.random.seed(0)
# Generate baseline absorbance values for standards decreasing with conc
standards = np.linspace(0.2, 0.02, 9)
# Create a matrix with small random noise
mat = np.random.normal(loc=0.05, scale=0.01, size=(rows, cols))
# Insert standard-like values in columns 1-2 (B-C) rows 0-7 and D-E row 0 entries
for i in range(8):
    mat[i,1] = standards[i] + np.random.normal(0, 0.005)
    mat[i,2] = standards[i] + np.random.normal(0, 0.005)
mat[0,3] = standards[8] + np.random.normal(0, 0.005)
mat[0,4] = standards[8] + np.random.normal(0, 0.005)

# Save as DataFrame without headers so iloc coordinates match
df = pd.DataFrame(mat)

df.to_excel('/Users/visakkumar/Downloads/example_absorbance.xlsx', index=False, header=False)

# Create a config file with default parameters, standard concentrations, and sample names
# We'll build a DataFrame with enough rows to hold the longest column (standards or sample names)
stds = [2000, 1750, 1500, 1250, 1000, 750, 500, 250, 0]
sample_names = ['Sample_' + str(i + 1) for i in range(20)]
nrows = max(len(stds), len(sample_names), 3)
config = pd.DataFrame(index=range(nrows))

# Fill the standard concentrations column (pad with NaN)
config['Standard Concentration (µg/ml)'] = stds + [None] * (nrows - len(stds))

# Fill sample names
config['Sample Names'] = sample_names + [None] * (nrows - len(sample_names))

# Put the parameters (first rows) and leave the rest NaN so the script can read them
params = ['dilution_factor', 'loading_protein', 'loading_volume']
values = [8.0, 30.0, 40.0]
config['Parameter'] = params + [None] * (nrows - len(params))
config['Value'] = values + [None] * (nrows - len(values))

config.to_excel('/Users/visakkumar/Downloads/example_config.xlsx', index=False)

print('Wrote example_absorbance.xlsx and example_config.xlsx to /Users/visakkumar/Downloads')