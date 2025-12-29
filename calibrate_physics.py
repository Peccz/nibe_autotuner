import pandas as pd
import numpy as np
import glob
import os

def load_data():
    data_dir = 'data_input'
    
    def find_file(pattern):
        files = glob.glob(os.path.join(data_dir, pattern))
        return files[0] if files else None

    # More robust patterns to handle weird characters in filenames
    f_indoor = find_file('*Room*temp*.csv')
    f_outdoor = find_file('*Outdoor*temp*.csv')
    f_freq = find_file('*Current*freq*.csv')
    
    if not all([f_indoor, f_outdoor, f_freq]):
        print(f"Missing files! Found:\n In={f_indoor}\n Out={f_outdoor}\n Freq={f_freq}")
        return None

    print(f"Loading:\n {f_indoor}\n {f_outdoor}\n {f_freq}")

    def read_csv(path, col_name):
        try:
            # Skip first row which is often empty or metadata in Nibe exports sometimes, 
            # but header=0 usually works if format is standard.
            # We assume ';' sep.
            df = pd.read_csv(path, sep=';', header=0, usecols=[0, 1], names=['timestamp', col_name])
            
            # coerce errors to handle potential garbage lines
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
            df.dropna(subset=['timestamp'], inplace=True)
            
            # Ensure value is numeric
            df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
            
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            print(f"Error reading {path}: {e}")
            return pd.DataFrame()

    df_in = read_csv(f_indoor, 'indoor')
    df_out = read_csv(f_outdoor, 'outdoor')
    df_freq = read_csv(f_freq, 'freq')

    # Merge
    print("Merging data...")
    # Join on index
    df = df_in.join(df_out, how='inner').join(df_freq, how='inner')
    
    if df.empty:
        print("No overlapping timestamps found! Trying outer join to debug dates.")
        print(f"In range: {df_in.index.min()} - {df_in.index.max()}")
        print(f"Out range: {df_out.index.min()} - {df_out.index.max()}")
        print(f"Freq range: {df_freq.index.min()} - {df_freq.index.max()}")
        return None

    # Resample to 1 hour averages
    df_1h = df.resample('1h').mean().interpolate()
    return df_1h

def analyze_physics(df):
    print("\n--- ANALYS AV HUSFYSIK ---")
    
    df['delta_in'] = df['indoor'].diff()
    df['diff_out'] = df['indoor'] - df['outdoor']
    
    # --- COOLING RATE ---
    # Freq < 5Hz (Off), Outdoor < 15C
    df_cool = df[(df['freq'] < 5) & (df['outdoor'] < 15)].copy()
    
    avg_k = -0.005 # Default
    cooling_rate_0c = -0.1
    
    if len(df_cool) > 5:
        # k = Delta / Diff
        df_cool['k_factor'] = df_cool['delta_in'] / df_cool['diff_out']
        
        # Filter realistic values (-0.2 to 0.0)
        # Losing 2 degrees in an hour with 10 degree diff -> -0.2. That's a tent.
        # Losing 0.1 degree in an hour with 20 degree diff -> -0.005. That's a passive house.
        df_cool_filtered = df_cool[df_cool['k_factor'].between(-0.2, 0.001)]
        
        if not df_cool_filtered.empty:
            avg_k = df_cool_filtered['k_factor'].mean()
            cooling_rate_0c = avg_k * 21.0
            
            print(f"Avsvalningsdata: {len(df_cool_filtered)} timmar")
            print(f"K-faktor: {avg_k:.5f}")
            print(f"Avsvalning vid 0°C ute: {cooling_rate_0c:.4f} °C/h")
        else:
            print("Kylningsdata orimlig.")
    else:
        print(f"För lite data med avstängd kompressor ({len(df_cool)} timmar).")

    # --- HEATING RATE ---
    # Freq > 40Hz
    df_heat = df[df['freq'] > 40].copy()
    
    avg_heating_power = 0.5 # Default
    
    if len(df_heat) > 5:
        df_heat['natural_loss'] = avg_k * df_heat['diff_out']
        # Heating = Change - Loss (where Loss is negative)
        df_heat['heating_power'] = df_heat['delta_in'] - df_heat['natural_loss']
        
        # Filter realistic (0.1 to 3.0 degrees per hour)
        df_heat_filtered = df_heat[df_heat['heating_power'].between(0.05, 3.0)]
        
        if not df_heat_filtered.empty:
            avg_heating_power = df_heat_filtered['heating_power'].mean()
            print(f"Uppvärmningsdata: {len(df_heat_filtered)} timmar")
            print(f"Kompressorns Värmekraft: {avg_heating_power:.4f} °C/h")
        else:
            print("Ingen realistisk uppvärmningsdata hittad.")
    else:
        print("För lite data med aktiv kompressor.")

    print("\n--- REKOMMENDERADE KONSTANTER (STRIKT NUMERISKT) ---")
    print(f"cooling_rate_0c = {cooling_rate_0c:.2f}")
    print(f"COMPRESSOR_HEAT_OUTPUT_C_PER_H = {avg_heating_power:.2f}")

if __name__ == "__main__":
    df = load_data()
    if df is not None:
        analyze_physics(df)