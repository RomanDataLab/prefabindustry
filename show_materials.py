import pandas as pd

# Read the CSV
df = pd.read_csv('maps/public/prefabworld.csv')

# Get unique materials with counts
materials = df['main_structure_material'].value_counts().sort_index()

print('Filtered Materials List:')
print('=' * 50)
for material, count in materials.items():
    print(f'{str(material):20s} : {count:4d} entries')
print('=' * 50)
print(f'\nTotal unique materials: {len(materials)}')
print(f'Total entries with material: {materials.sum()}')
print(f'Empty/NaN entries: {df["main_structure_material"].isna().sum()}')
