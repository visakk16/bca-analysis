import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from typing import Optional, List, Dict, Union, Tuple
try:
    from IPython.display import display
except Exception:
    # Fallback for plain terminal environments
    def display(obj):
        try:
            print(obj.to_string())
        except Exception:
            print(obj)
import argparse

def analyze_bca_plate(absorbance_file: str, config_file: str) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Analyze BCA plate data using absorbance data and configuration parameters from separate Excel files.
    """
    # Read the absorbance data
    df = pd.read_excel(absorbance_file)
    
    # Default values
    conc_list = [2000, 1750, 1500, 1250, 1000, 750, 500, 250, 0]
    sample_names = []
    dilution_factor = 8.0
    loading_protein = 30.0
    loading_volume = 40.0
    
    # Try to read configuration parameters
    try:
        config_df = pd.read_excel(config_file)
        
        # Try to get standard concentrations
        if 'Standard Concentration (µg/ml)' in config_df.columns:
            temp_conc = config_df['Standard Concentration (µg/ml)'].dropna().tolist()
            if temp_conc:  # Only use if we got valid values
                conc_list = temp_conc
                print("Using standard concentrations from config file")
            else:
                print("Warning: Using default concentration list")
                
        # Try to get sample names
        if 'Sample Names' in config_df.columns:
            temp_names = config_df['Sample Names'].dropna().tolist()
            if temp_names:
                sample_names = temp_names
                print("Using sample names from config file")
            else:
                print("Warning: No sample names provided in config file")
        
        # Try to get parameters
        params_df = config_df[config_df['Parameter'].isin(['dilution_factor', 'loading_protein', 'loading_volume'])]
        if not params_df.empty:
            for _, row in params_df.iterrows():
                if row['Parameter'] == 'dilution_factor':
                    dilution_factor = float(row['Value'])
                elif row['Parameter'] == 'loading_protein':
                    loading_protein = float(row['Value'])
                elif row['Parameter'] == 'loading_volume':
                    loading_volume = float(row['Value'])
    
    except Exception as e:
        print(f"Warning: Error reading config file: {e}")
        print("Using default values for all parameters")

    print("\nConfiguration Parameters:")
    print(f"Dilution Factor: {dilution_factor}")
    print(f"Loading Protein (µg): {loading_protein}")
    print(f"Loading Volume (µl): {loading_volume}")
    print(f"Number of standards: {len(conc_list)}")
    if sample_names:
        print(f"Number of sample names: {len(sample_names)}")

    # === Calculate Standards ===
    # Robust detection if first row is a numeric header like 1,2,3,... (some plate exports include it)
    header_like = False
    try:
        first_row_vals = df.iloc[0, 1:20].values.tolist()
        tokens = []
        for v in first_row_vals:
            s = str(v).strip()
            tokens.append(s)
        import re
        int_like = 0
        for t in tokens:
            if re.match(r'^\s*\d+(?:\.0+)?\s*$', t):
                int_like += 1
        if int_like >= max(3, int(0.6 * len(tokens))):
            header_like = True
    except Exception:
        header_like = False

    # also check if row 1 column 0 contains row labels A..H — then row 0 is header
    try:
        first_data_label = str(df.iloc[1, 0]).strip()
        if len(first_data_label) == 1 and first_data_label.isalpha():
            header_like = True
    except Exception:
        pass

    base = 1 if header_like else 0

    # Get averages from B2-B9 & C2-C9 (rows base..base+7, cols 1-2) -- 8 values
    standards_BC = df.iloc[base:base+8, [1, 2]].mean(axis=1).values  # rows base..base+7

    # Get average from D2 & E2 (row base, cols 3-4) -- 1 value
    standard_DE = df.iloc[base, [3, 4]].mean()

    # If the D/E cell looks like a numeric header (e.g., 3 or 4) and BC values are small, shift base
    try:
        avg_bc = np.nanmean(standards_BC)
        if (standard_DE > 1.0 and avg_bc < 1.0 and abs(round(standard_DE) - standard_DE) < 0.01):
            base = base + 1
            standards_BC = df.iloc[base:base+8, [1, 2]].mean(axis=1).values
            standard_DE = df.iloc[base, [3, 4]].mean()
    except Exception:
        pass

    # Combine all standards (should be 9 values)
    standards = np.concatenate([standards_BC, [standard_DE]])
    print("\nStandards Validation:")
    print("conc_list length:", len(conc_list), conc_list)
    print("standards length:", len(standards), standards)
    print("Any NaNs in standards?", np.isnan(standards).any())

    # === Create Standard Curve ===
    # Pair and sort concentrations and standards by concentration before regression
    conc_arr = np.array(conc_list, dtype=float)
    std_arr = np.array(standards, dtype=float)
    if conc_arr.shape != std_arr.shape or np.isnan(std_arr).any():
        raise ValueError('Standards length mismatch or NaNs detected. Check the absorbance and config files.')
    order = np.argsort(conc_arr)
    conc_sorted = conc_arr[order]
    std_sorted = std_arr[order]

    # Use numpy polyfit and explicit R^2 calculation
    coeffs = np.polyfit(conc_sorted, std_sorted, 1)
    slope = float(coeffs[0])
    intercept = float(coeffs[1])
    preds_full = slope * conc_sorted + intercept
    ss_res = np.sum((std_sorted - preds_full) ** 2)
    ss_tot = np.sum((std_sorted - np.mean(std_sorted)) ** 2)
    r_squared = float(1.0 - ss_res / ss_tot) if ss_tot != 0 else 0.0

    # Plot standard curve using sorted data
    plt.figure(figsize=(10, 6))
    plt.scatter(conc_sorted, std_sorted, color='blue', label='Standards')
    x_line = np.linspace(min(conc_sorted), max(conc_sorted), 100)
    y_line = slope * x_line + intercept
    plt.plot(x_line, y_line, '--r', label=f'y = {slope:.6f}x + {intercept:.6f}\nR² = {r_squared:.4f}')
    plt.xlabel('Concentration (µg/ml)')
    plt.ylabel('Absorbance')
    plt.title('BCA Standard Curve')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()

    # Function to calculate concentration from absorbance
    def calc_concentration(abs_value):
        # Formula: (absorbance - intercept) / slope
        return (abs_value - intercept) / slope

    print("\nConcentration calculation formula:")
    print(f"Concentration (µg/ml) = (absorbance - ({intercept:.6f})) / {slope:.6f}")

    # === Process Sample Sets ===
    sample_sets = [
        (df.iloc[1:8, [3, 4]], "Set 1 (D-E)"),  # D3-D9 & E3-E9 (rows 1-7)
        (df.iloc[0:7, [5, 6]], "Set 2 (F-G)"),  # F2-F9 & G2-G9 (rows 0-6)
        (df.iloc[0:7, [7, 8]], "Set 3 (H-I)"),  # H2-H9 & I2-I9 (rows 0-6)
        (df.iloc[0:7, [9, 10]], "Set 4 (J-K)")  # J2-J9 & K2-K9 (rows 0-6)
    ]

    results = []
    sample_index = 0  # Keep track of which sample name to use

    for sample_data, set_name in sample_sets:
        averages = sample_data.mean(axis=1)
        concentrations = calc_concentration(averages)
        
        # Adjust starting number based on the set
        start_num = 3 if set_name == "Set 1 (D-E)" else 2
        
        for i, (abs_val, conc) in enumerate(zip(averages, concentrations)):
            # Use custom sample name if available, otherwise use well ID
            if sample_names and sample_index < len(sample_names):
                sample_name = sample_names[sample_index]
            else:
                sample_name = f"{set_name[5]}{i+start_num}"
            
            # Calculate additional columns
            conc_with_dilution = conc * dilution_factor
            ug_per_ul = conc_with_dilution / 1000
            
            # Calculate loading volumes based on target protein amount
            if ug_per_ul < 1.5:
                sample_vol = min(20, loading_volume)  # Cap at loading_volume
            else:
                sample_vol = min(loading_protein / ug_per_ul, loading_volume)
            
            # Calculate 2X and buffer volumes
            vol_2x = 2 * sample_vol
            buffer_vol = loading_volume - sample_vol

            results.append({
                'Sample': sample_name,
                'Absorbance': round(abs_val, 3),
                'Concentration (µg/ml)': round(conc, 2),
                'µg/ml (with dilution)': round(conc_with_dilution, 2),
                'µg/µl': round(ug_per_ul, 2),
                'Sample Volume (µl)': round(sample_vol, 2),
                '2X Sample Volume (µl)': round(vol_2x, 2),
                'Buffer Volume (µl)': round(buffer_vol, 2)
            })
            sample_index += 1

    results_df = pd.DataFrame(results)
    return results_df, {'slope': slope, 'intercept': intercept, 'r_squared': r_squared}
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze BCA plate data from Excel files')
    parser.add_argument('--absorbance', '-a', default='/Users/visakkumar/Downloads/example_absorbance.xlsx',
                        help='Path to the absorbance Excel file')
    parser.add_argument('--config', '-c', default='/Users/visakkumar/Downloads/example_config.xlsx',
                        help='Path to the config Excel file')

    args = parser.parse_args()

    absorbance_file = args.absorbance
    config_file = args.config

    try:
        # Try to analyze with both files
        results_df, stats = analyze_bca_plate(absorbance_file, config_file)

        print("\nAnalysis Statistics:")
        print(f"Slope: {stats['slope']:.6f}")
        print(f"Intercept: {stats['intercept']:.6f}")
        print(f"R\u00b2: {stats['r_squared']:.6f}")

        print("\nResults by Sample:")
        display(results_df)

    except Exception as e:
        print(f"Error during analysis: {e}")
        print("\nPlease ensure:")
        print("1. The absorbance file exists and contains valid plate reader data")
        print("2. The config file (if provided) has the correct format:")
        print("   - 'Parameter' column with values: dilution_factor, loading_protein, loading_volume")
        print("   - 'Value' column with corresponding numeric values")
        print("   - 'Standard Concentration (\u00b5g/ml)' column (optional)")
        print("   - 'Sample Names' column (optional)")
