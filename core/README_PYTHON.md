# EU Prefab Home Companies Research - Python Version

This Python script performs deep continuous research of all prefab home companies in the EU using OpenAI API.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Or install directly:
```bash
pip install openai
```

2. Ensure your OpenAI API key is configured in `C:\12_CODINGHARD\config\config_openai.json`

## Usage

Run the research script:
```bash
python core/researchPrefabCompanies.py
```

Or on Windows:
```bash
py core/researchPrefabCompanies.py
```

## Output

The script generates:
- `research_output/prefab_core.csv` - Main CSV file with all company data (results in English)
- `research_output/prefab_core.json` - JSON backup
- `research_output/progress_backup.json` - Progress backup (updated every 5 companies)

## Table Columns

- **id**: Unique identifier
- **brand**: Brand/trading name
- **head_office_legal_name**: Full legal company name
- **address**: Complete address
- **webpage**: Main website URL
- **configurator**: Direct link to online configurator page (or NaN if not available)
- **models_amount**: Number of prefab home models offered
- **min_sqm**: Minimum square meters (smallest model)
- **max_sqm**: Maximum square meters (largest model)
- **main_structure_material**: Primary construction material
- **min_home_price**: Minimum price in EUR
- **average_price_sqm**: Average price per square meter in EUR

## Features

- **Country-by-country research**: Processes each EU country systematically
- **Local language research**: Uses local languages for better discovery (German, French, Italian, Spanish, Dutch, Swedish, Polish, Portuguese, etc.)
- **English output**: All results saved in English regardless of research language
- **Progress saving**: Automatically saves progress every 5 companies and after each country
- **Resume capability**: Can resume from previous session (skips already processed countries)
- **Error handling**: Continues even if individual companies fail
- **Rate limiting**: Built-in delays to avoid API rate limits

## Notes

- The research process may take several hours depending on the number of companies found
- Progress is saved automatically, so you can stop and resume the script
- All prices are converted to EUR
- The script uses GPT-4o for comprehensive research
- Compatible with Python 3.7+

## Differences from JavaScript Version

- Uses Python's `openai` library instead of Node.js version
- Uses Python's built-in `csv` module for CSV writing
- Uses Python's `json` module for JSON handling
- Same functionality and output format
