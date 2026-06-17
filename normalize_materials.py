import pandas as pd
import re

# Read the CSV
df = pd.read_csv('maps/public/prefabworld.csv')

# Function to normalize materials
def normalize_material(material):
    if pd.isna(material) or material == '':
        return material
    
    material_str = str(material).strip()
    
    # Convert to lowercase for comparison (ignore case)
    material_lower = material_str.lower()
    
    # First, check for "cross-laminated timber" and convert to "CLT"
    if 'cross-laminated timber' in material_lower or material_lower == 'clt':
        return 'CLT'
    
    # Check if it contains wood or timber (case-insensitive)
    has_wood = 'wood' in material_lower
    has_timber = 'timber' in material_lower
    
    # Reassemble: concatenate all wood and timber variants via '/' into "wood/timber"
    if has_wood or has_timber:
        return 'wood/timber'
    # Otherwise, keep as is (but normalize case for consistency)
    else:
        # Keep original but normalize common variations
        if material_lower == 'aac blocks':
            return 'AAC blocks'
        else:
            return material_str

# Apply normalization
df['main_structure_material'] = df['main_structure_material'].apply(normalize_material)

# Save the updated CSV
df.to_csv('maps/public/prefabworld.csv', index=False)

# Show summary
print("Normalization complete!")
print("\nUnique materials after normalization:")
materials = df['main_structure_material'].value_counts()
print(materials.to_string())
print(f"\nTotal entries with material: {materials.sum()}")
print(f"Empty/NaN entries: {df['main_structure_material'].isna().sum()}")
