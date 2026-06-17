#!/usr/bin/env python3
# Deep continuous research of EU prefab home companies using OpenAI
import sys
import os
import json
import csv
import time
import re
from pathlib import Path
from typing import List, Dict, Optional

# Fix Windows encoding issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path to import apiManager
sys.path.insert(0, str(Path(__file__).parent.parent))
from configix.apiManager import get_ai_provider

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

# Initialize OpenAI with API key from configix
openai_config = get_ai_provider('ai_openai')
openai_client = OpenAI(api_key=openai_config['api_key'])

# Output directory
output_dir = Path(__file__).parent.parent / 'research_output'
output_dir.mkdir(exist_ok=True)
csv_path = output_dir / 'prefab_core.csv'

# Store all companies
all_companies = []
company_id = 1

# EU countries with their local languages for research
EU_COUNTRIES = [
    {'code': 'DE', 'name': 'Germany', 'language': 'German', 'native_name': 'Deutschland'},
    {'code': 'FR', 'name': 'France', 'language': 'French', 'native_name': 'France'},
    {'code': 'IT', 'name': 'Italy', 'language': 'Italian', 'native_name': 'Italia'},
    {'code': 'ES', 'name': 'Spain', 'language': 'Spanish', 'native_name': 'España'},
    {'code': 'NL', 'name': 'Netherlands', 'language': 'Dutch', 'native_name': 'Nederland'},
    {'code': 'BE', 'name': 'Belgium', 'language': 'Dutch/French', 'native_name': 'België/Belgique'},
    {'code': 'AT', 'name': 'Austria', 'language': 'German', 'native_name': 'Österreich'},
    {'code': 'SE', 'name': 'Sweden', 'language': 'Swedish', 'native_name': 'Sverige'},
    {'code': 'DK', 'name': 'Denmark', 'language': 'Danish', 'native_name': 'Danmark'},
    {'code': 'FI', 'name': 'Finland', 'language': 'Finnish', 'native_name': 'Suomi'},
    {'code': 'PL', 'name': 'Poland', 'language': 'Polish', 'native_name': 'Polska'},
    {'code': 'CZ', 'name': 'Czech Republic', 'language': 'Czech', 'native_name': 'Česká republika'},
    {'code': 'PT', 'name': 'Portugal', 'language': 'Portuguese', 'native_name': 'Portugal'},
    {'code': 'GR', 'name': 'Greece', 'language': 'Greek', 'native_name': 'Ελλάδα'},
    {'code': 'IE', 'name': 'Ireland', 'language': 'English', 'native_name': 'Ireland'},
    {'code': 'RO', 'name': 'Romania', 'language': 'Romanian', 'native_name': 'România'},
    {'code': 'HU', 'name': 'Hungary', 'language': 'Hungarian', 'native_name': 'Magyarország'},
    {'code': 'SK', 'name': 'Slovakia', 'language': 'Slovak', 'native_name': 'Slovensko'},
    {'code': 'BG', 'name': 'Bulgaria', 'language': 'Bulgarian', 'native_name': 'България'},
    {'code': 'HR', 'name': 'Croatia', 'language': 'Croatian', 'native_name': 'Hrvatska'},
    {'code': 'SI', 'name': 'Slovenia', 'language': 'Slovenian', 'native_name': 'Slovenija'},
    {'code': 'LT', 'name': 'Lithuania', 'language': 'Lithuanian', 'native_name': 'Lietuva'},
    {'code': 'LV', 'name': 'Latvia', 'language': 'Latvian', 'native_name': 'Latvija'},
    {'code': 'EE', 'name': 'Estonia', 'language': 'Estonian', 'native_name': 'Eesti'},
    {'code': 'LU', 'name': 'Luxembourg', 'language': 'Luxembourgish/French', 'native_name': 'Lëtzebuerg'},
    {'code': 'MT', 'name': 'Malta', 'language': 'Maltese', 'native_name': 'Malta'},
    {'code': 'CY', 'name': 'Cyprus', 'language': 'Greek', 'native_name': 'Κύπρος'}
]

def call_openai(messages: List[Dict], max_retries: int = 3) -> str:
    """Call OpenAI API with retry logic"""
    for i in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )
            return response.choices[0].message.content
        except Exception as error:
            print(f"Attempt {i + 1} failed: {error}")
            if i == max_retries - 1:
                raise
            time.sleep(2 * (i + 1))

def get_companies_for_country(country: Dict) -> List[Dict]:
    """Get companies for a specific country using local language"""
    language = country['language'].split('/')[0]
    country_name_native = country['native_name'].split('/')[0]
    
    # Build prompt based on language
    prompts = {
        'German': f"""Du bist ein Forschungsexperte für vorgefertigte/modulare Hausunternehmen in {country_name_native}.

Bitte erstelle eine umfassende Liste ALLER Unternehmen in {country_name_native}, die vorgefertigte Häuser (Fertighäuser, Modulhäuser, Bausatzhäuser, Plattenhäuser usw.) herstellen.

Schließe ein:
- Große Hersteller
- Mittlere Unternehmen
- Regionale Hersteller
- Spezialisierte Anbieter (Luxus, ökologisch, etc.)

Gib NUR ein JSON-Array zurück: [{{"name": "Firmenname", "country": "{country['name']}"}}, ...]""",
        
        'French': f"""Vous êtes un expert en recherche spécialisé dans les entreprises de maisons préfabriquées/modulaires en {country_name_native}.

Veuillez fournir une liste complète de TOUTES les entreprises en {country_name_native} qui fabriquent des maisons préfabriquées (maisons préfabriquées, maisons modulaires, maisons en kit, maisons panneaux, etc.).

Incluez:
- Grands fabricants
- Entreprises de taille moyenne
- Fabricants régionaux
- Constructeurs spécialisés (luxe, écologique, etc.)

Retournez UNIQUEMENT un tableau JSON: [{{"name": "Nom de l'entreprise", "country": "{country['name']}"}}, ...]""",
        
        'Italian': f"""Sei un esperto di ricerca specializzato in aziende di case prefabbricate/modulari in {country_name_native}.

Fornisci un elenco completo di TUTTE le aziende in {country_name_native} che producono case prefabbricate (case prefabbricate, case modulari, case in kit, case pannelli, ecc.).

Includi:
- Grandi produttori
- Aziende di medie dimensioni
- Produttori regionali
- Costruttori specializzati (lusso, ecologico, ecc.)

Restituisci SOLO un array JSON: [{{"name": "Nome azienda", "country": "{country['name']}"}}, ...]""",
        
        'Spanish': f"""Eres un experto en investigación especializado en empresas de casas prefabricadas/modulares en {country_name_native}.

Proporciona una lista completa de TODAS las empresas en {country_name_native} que fabrican casas prefabricadas (casas prefabricadas, casas modulares, casas kit, casas panelizadas, etc.).

Incluye:
- Grandes fabricantes
- Empresas medianas
- Fabricantes regionales
- Constructores especializados (lujo, ecológico, etc.)

Devuelve SOLO un array JSON: [{{"name": "Nombre de empresa", "country": "{country['name']}"}}, ...]""",
        
        'Dutch': f"""Je bent een onderzoeksdeskundige gespecialiseerd in geprefabriceerde/modulaire woningbouwbedrijven in {country_name_native}.

Geef een uitgebreide lijst van ALLE bedrijven in {country_name_native} die geprefabriceerde woningen (prefabwoningen, modulaire woningen, bouwpakketwoningen, paneelwoningen, etc.) produceren.

Inclusief:
- Grote fabrikanten
- Middelgrote bedrijven
- Regionale fabrikanten
- Gespecialiseerde bouwers (luxe, ecologisch, etc.)

Geef ALLEEN een JSON-array terug: [{{"name": "Bedrijfsnaam", "country": "{country['name']}"}}, ...]""",
        
        'Swedish': f"""Du är en forskningsexpert specialiserad på prefabricerade/modulära husföretag i {country_name_native}.

Ge en omfattande lista över ALLA företag i {country_name_native} som tillverkar prefabricerade hus (prefabhus, modulhus, kithus, panelhus, etc.).

Inkludera:
- Stora tillverkare
- Medelstora företag
- Regionala tillverkare
- Specialiserade byggare (lyx, miljövänliga, etc.)

Returnera ENDAST en JSON-array: [{{"name": "Företagsnamn", "country": "{country['name']}"}}, ...]""",
        
        'Polish': f"""Jesteś ekspertem badawczym specjalizującym się w firmach domów prefabrykowanych/modularnych w {country_name_native}.

Podaj kompleksową listę WSZYSTKICH firm w {country_name_native}, które produkują domy prefabrykowane (domy prefabrykowane, domy modułowe, domy z zestawów, domy panelowe itp.).

Uwzględnij:
- Dużych producentów
- Średnie firmy
- Regionalnych producentów
- Specjalistycznych budowniczych (luksusowe, ekologiczne itp.)

Zwróć TYLKO tablicę JSON: [{{"name": "Nazwa firmy", "country": "{country['name']}"}}, ...]""",
        
        'Portuguese': f"""És um especialista em investigação especializado em empresas de casas pré-fabricadas/modulares em {country_name_native}.

Fornece uma lista abrangente de TODAS as empresas em {country_name_native} que fabricam casas pré-fabricadas (casas pré-fabricadas, casas modulares, casas kit, casas painelizadas, etc.).

Inclui:
- Grandes fabricantes
- Empresas de médio porte
- Fabricantes regionais
- Construtores especializados (luxo, ecológico, etc.)

Retorna APENAS um array JSON: [{{"name": "Nome da empresa", "country": "{country['name']}"}}, ...]"""
    }
    
    local_prompt = prompts.get(language, f"""You are a research expert specializing in prefabricated/modular home companies in {country['name']}.

Please provide a comprehensive list of ALL companies in {country['name']} that manufacture prefab homes (prefabricated homes, modular homes, kit homes, panelized homes, etc.).

Include:
- Large manufacturers
- Medium-sized companies
- Regional manufacturers
- Specialized builders (luxury, eco-friendly, etc.)

Return ONLY a JSON array: [{{"name": "Company Name", "country": "{country['name']}"}}, ...]""")
    
    try:
        response = call_openai([{'role': 'user', 'content': local_prompt}])
        
        # Extract JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                companies = json.loads(json_match.group(0))
                return [{'name': c.get('name', ''), 'country': country['name']} for c in companies]
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON for {country['name']}: {e}")
                return extract_company_names(response, country['name'])
        return extract_company_names(response, country['name'])
    except Exception as error:
        print(f"  ❌ Error researching {country['name']}: {error}")
        return []

def extract_company_names(text: str, country: str) -> List[Dict]:
    """Extract company names from text response"""
    companies = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for line in lines:
        match = re.match(r'(?:^|\d+\.\s*)(.+?)(?:\s*[-–]\s*)?([A-Z][a-z]+)?$', line)
        if match:
            companies.append({
                'name': match.group(1).strip(),
                'country': match.group(2) if match.group(2) else country
            })
    
    return companies

def check_configurator(company_name: str, webpage: str) -> Optional[str]:
    """Check if company has an online configurator and get direct link"""
    if not webpage:
        return None
    
    prompt = f"""You are checking if a prefab home company has an online configurator tool where users can model or configure homes online.

Company: {company_name}
Website: {webpage}

Check if this company has ANY online tool where customers can:
- Configure or customize their home online
- Model their home online
- Design their home online
- Use an interactive configurator
- Select options/features for their home online

This includes tools like:
- Home configurators
- Design tools
- Customization tools
- Interactive planners
- Online builders

This does NOT include:
- Simple contact forms
- Image galleries
- PDF downloads
- Static product pages
- Request a quote forms (unless they include configuration)

If a configurator exists, return ONLY the direct URL to the configurator page (must be a full URL starting with http:// or https://).
If no configurator exists, return exactly: NaN

Return ONLY the URL or NaN, nothing else."""

    try:
        response = call_openai([{'role': 'user', 'content': prompt}])
        result = response.strip()
        
        # Check if it's a valid URL
        if result and result != 'NaN' and result != 'null' and (result.startswith('http://') or result.startswith('https://')):
            return result
        
        return None  # Will be converted to NaN in CSV
    except Exception as error:
        print(f"  ⚠️  Error checking configurator for {company_name}: {error}")
        return None

def research_company(company_name: str, country: str, country_info: Dict) -> Dict:
    """Research detailed information about a single company using local language but returning English results"""
    global company_id
    print(f"\n📊 Researching: {company_name} ({country})")
    
    language = country_info['language'].split('/')[0] if country_info else 'English'
    
    # Build prompts in local language but request English output
    # Note: Full prompts for all languages would be very long, using key languages and English fallback
    prompts = {
        'German': f"""Du bist ein professioneller Forscher, der detaillierte Informationen über ein Unternehmen für vorgefertigte/modulare Häuser in {country_info['native_name']} sammelt.

Zu recherchierendes Unternehmen: {company_name}
Land: {country}

Führe gründliche Recherchen durch und gib umfassende, genaue Informationen zurück. Gib NUR gültiges JSON in diesem exakten Format zurück (verwende null für fehlende Daten, NaN für numerische Felder, die nicht bestimmt werden können):

{{
  "brand": "Markenname oder Handelsname (der Name, unter dem Kunden sie kennen)",
  "head_office_legal_name": "vollständiger rechtlicher Firmenname",
  "address": "vollständige Adresse: Straßennummer, Straßenname, Stadt, Postleitzahl, Land",
  "webpage": "Hauptwebsite-URL (https://...)",
  "configurator": "direkte URL zur Online-Konfigurator-/Kombinatortool-Seite, falls vorhanden (z.B. /configurator, /design-your-home, /home-configurator), sonst null",
  "models_amount": Anzahl der verschiedenen vorgefertigten Hausmodelle/Designs, die sie derzeit anbieten (Ganzzahl, zähle tatsächliche Modelle),
  "min_sqm": Mindestquadratmeter ihres kleinsten verfügbaren Modells (Zahl, Wohnfläche),
  "max_sqm": Höchstquadratmeter ihres größten verfügbaren Modells (Zahl, Wohnfläche),
  "main_structure_material": "Hauptbaumaterial: Holz/Holz/Beton/Stahl/Verbundwerkstoff/CLT/Kreuzlagenholz/etc",
  "min_home_price": Mindestpreis in EUR für ihr günstigstes Modell (Zahl, bei Bedarf von anderen Währungen umrechnen, Grundpreis ohne Grundstück),
  "average_price_sqm": Durchschnittspreis pro Quadratmeter in EUR über ihre Modelle (Zahl, berechnet aus ihren Preisen)
}}

KRITISCHE ANFORDERUNGEN:
- Alle Antworten müssen auf ENGLISCH sein, auch wenn die Recherche auf Deutsch durchgeführt wird
- Für "configurator": Nur URL angeben, wenn sie ein Online-Tool haben, mit dem Kunden Hausoptionen konfigurieren/kombinieren können
- Alle Preise in EUR umrechnen
- Nur verifizierte, faktische Informationen einbeziehen
- Gib NUR das JSON-Objekt zurück, keine Erklärungen oder zusätzlichen Text""",
        
        'French': f"""Vous êtes un chercheur professionnel recueillant des informations détaillées sur une entreprise de maisons préfabriquées/modulaires en {country_info['native_name']}.

Entreprise à rechercher: {company_name}
Pays: {country}

Effectuez des recherches approfondies et fournissez des informations complètes et précises. Retournez UNIQUEMENT un JSON valide dans ce format exact (utilisez null pour les données manquantes, NaN pour les champs numériques qui ne peuvent pas être déterminés):

{{
  "brand": "nom de marque ou nom commercial (le nom sous lequel les clients les connaissent)",
  "head_office_legal_name": "nom légal complet de l'entreprise",
  "address": "adresse complète: numéro de rue, nom de rue, ville, code postal, pays",
  "webpage": "URL de la page d'accueil du site web principal (https://...)",
  "configurator": "URL directe vers la page de l'outil configurateur/combinateur en ligne s'ils en ont un (ex: /configurator, /design-your-home, /home-configurator), sinon null",
  "models_amount": nombre de modèles/designs de maisons préfabriquées différents qu'ils proposent actuellement (entier, compter les modèles réels),
  "min_sqm": mètres carrés minimum de leur plus petit modèle disponible (nombre, surface habitable),
  "max_sqm": mètres carrés maximum de leur plus grand modèle disponible (nombre, surface habitable),
  "main_structure_material": "matériau de construction principal: bois/bois/béton/acier/composite/CLT/bois lamellé-croisé/etc",
  "min_home_price": prix minimum en EUR pour leur modèle le moins cher (nombre, convertir d'autres devises si nécessaire, prix de base sans terrain),
  "average_price_sqm": prix moyen par mètre carré en EUR sur leurs modèles (nombre, calculé à partir de leurs prix)
}}

EXIGENCES CRITIQUES:
- Toutes les réponses doivent être en ANGLAIS, même si la recherche est effectuée en français
- Pour "configurator": Fournir l'URL uniquement s'ils ont un outil en ligne permettant aux clients de configurer/combiner des options de maison
- Convertir tous les prix en EUR
- N'inclure que des informations vérifiées et factuelles
- Retourner UNIQUEMENT l'objet JSON, aucune explication ou texte supplémentaire""",
    }
    
    local_prompt = prompts.get(language, f"""You are a professional researcher gathering detailed information about a prefabricated/modular home company in {country}.

Company to research: {company_name}
Country: {country}

Conduct thorough research and provide comprehensive, accurate information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{{
  "brand": "brand name or trading name (the name customers know them by)",
  "head_office_legal_name": "full legal registered company name",
  "address": "complete address: street number, street name, city, postal code, country",
  "webpage": "main website homepage URL (https://...)",
  "configurator": "direct URL to online configurator/combinator tool page if they have one (e.g., /configurator, /design-your-home, /home-configurator), else null",
  "models_amount": number of different prefab home models/designs they currently offer (integer, count actual models),
  "min_sqm": minimum square meters of their smallest available model (number, living area),
  "max_sqm": maximum square meters of their largest available model (number, living area),
  "main_structure_material": "primary construction material: wood/timber/concrete/steel/composite/CLT/cross-laminated timber/etc",
  "min_home_price": minimum starting price in EUR for their cheapest model (number, convert from other currencies if needed, base price without land),
  "average_price_sqm": average price per square meter in EUR across their models (number, calculate from their pricing)
}}

CRITICAL REQUIREMENTS:
- For "configurator": Only provide URL if they have an online tool where customers can configure/combine home options. If it's just a contact form or gallery, use null. Must be direct link to the configurator page.
- Convert ALL prices to EUR (use current exchange rates)
- "models_amount" should be the actual count of different home models/designs they offer
- "min_sqm" and "max_sqm" refer to living area/square meters of the homes
- Be precise with addresses - include full street address when possible
- For "main_structure_material", use the most common material (wood, concrete, steel, etc.)
- Only include verified, factual information
- Return ONLY the JSON object, no explanations or additional text before/after""")
    
    try:
        response = call_openai([{'role': 'user', 'content': local_prompt}])
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                
                # Validate and clean data (configurator will be checked separately)
                def safe_int(value):
                    try:
                        return int(value) if value is not None and value != 'null' and value != 'NaN' else None
                    except (ValueError, TypeError):
                        return None
                
                def safe_float(value):
                    try:
                        return float(value) if value is not None and value != 'null' and value != 'NaN' else None
                    except (ValueError, TypeError):
                        return None
                
                result = {
                    'id': company_id,
                    'brand': data.get('brand') or company_name,
                    'head_office_legal_name': data.get('head_office_legal_name') or None,
                    'address': data.get('address') or None,
                    'webpage': data.get('webpage') or None,
                    'configurator': None,  # Will be set by check_configurator function
                    'models_amount': safe_int(data.get('models_amount')),
                    'min_sqm': safe_float(data.get('min_sqm')),
                    'max_sqm': safe_float(data.get('max_sqm')),
                    'main_structure_material': data.get('main_structure_material') or None,
                    'min_home_price': safe_float(data.get('min_home_price')),
                    'average_price_sqm': safe_float(data.get('average_price_sqm'))
                }
                
                # Check for configurator using OpenAI
                if result['webpage']:
                    print(f"  🔍 Checking configurator for {company_name}...")
                    configurator_url = check_configurator(company_name, result['webpage'])
                    result['configurator'] = configurator_url or None  # None will be written as NaN in CSV
                    time.sleep(0.5)  # Small delay
                else:
                    result['configurator'] = None  # No webpage, so no configurator
                
                company_id += 1
                return result
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Error parsing JSON for {company_name}: {e}")
                print(f"  Response snippet: {response[:200]}...")
                return create_default_entry(company_name, country)
        
        return create_default_entry(company_name, country)
    except Exception as error:
        print(f"  ❌ Error researching {company_name}: {error}")
        return create_default_entry(company_name, country)

def create_default_entry(company_name: str, country: str) -> Dict:
    """Create default entry when research fails"""
    global company_id
    entry = {
        'id': company_id,
        'brand': company_name,
        'head_office_legal_name': None,
        'address': None,
        'webpage': None,
        'configurator': None,
        'models_amount': None,
        'min_sqm': None,
        'max_sqm': None,
        'main_structure_material': None,
        'min_home_price': None,
        'average_price_sqm': None
    }
    company_id += 1
    return entry

def save_progress():
    """Save progress to JSON backup"""
    backup_path = output_dir / 'progress_backup.json'
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(all_companies, f, indent=2, ensure_ascii=False)
    print(f"💾 Progress saved: {len(all_companies)} companies")

def load_progress() -> bool:
    """Load existing progress if available"""
    global company_id
    backup_path = output_dir / 'progress_backup.json'
    if backup_path.exists():
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                # Migrate old data: rename 'combinator' to 'configurator' if present
                for company in data:
                    if 'combinator' in company and 'configurator' not in company:
                        company['configurator'] = company.pop('combinator')
                all_companies.extend(data)
                company_id = max([c.get('id', 0) for c in data], default=0) + 1
                print(f"📂 Loaded {len(data)} companies from previous session")
                return True
        except Exception as e:
            print(f'⚠️  Could not load previous progress: {e}')
    return False

def save_csv():
    """Save results to CSV"""
    fieldnames = [
        'id', 'brand', 'head_office_legal_name', 'address', 'webpage',
        'configurator', 'models_amount', 'min_sqm', 'max_sqm',
        'main_structure_material', 'min_home_price', 'average_price_sqm'
    ]
    
    # Convert None configurator to 'NaN' string for CSV
    csv_data = []
    for company in all_companies:
        csv_company = company.copy()
        csv_company['configurator'] = company.get('configurator') or 'NaN'
        csv_data.append(csv_company)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)

def main():
    """Main research function - country by country"""
    global all_companies, company_id
    
    print('🚀 Starting deep continuous research of EU prefab home companies...\n')
    print(f"Using OpenAI API ({openai_config['name']})\n")
    print(f"Researching {len(EU_COUNTRIES)} EU countries one by one using local languages\n")
    
    # Check for existing progress
    has_progress = load_progress()
    
    # Track which countries have been processed
    processed_countries = set()
    if has_progress:
        for company in all_companies:
            address = company.get('address') or ''
            if address:
                for country in EU_COUNTRIES:
                    if country['name'] in address:
                        processed_countries.add(country['code'])
                        break
    
    try:
        # Process each country
        for i, country in enumerate(EU_COUNTRIES, 1):
            if country['code'] in processed_countries:
                print(f"\n⏭️  Skipping {country['name']} (already processed)")
                continue
            
            print(f"\n{'=' * 60}")
            print(f"🌍 Country {i}/{len(EU_COUNTRIES)}: {country['name']} ({country['language']})")
            print(f"{'=' * 60}\n")
            
            # Step 1: Get companies for this country using local language
            print(f"🔍 Discovering companies in {country['name']}...")
            companies = get_companies_for_country(country)
            
            if not companies:
                print(f"  ⚠️  No companies found for {country['name']}")
                time.sleep(1)
                continue
            
            print(f"  ✅ Found {len(companies)} companies in {country['name']}\n")
            
            # Step 2: Research each company for this country
            processed = 0
            total = len(companies)
            
            for company in companies:
                try:
                    company_data = research_company(company['name'], company['country'], country)
                    all_companies.append(company_data)
                    processed += 1
                    
                    print(f"  ✅ [{processed}/{total}] Completed: {company_data['brand']}")
                    
                    # Save progress every 5 companies
                    if len(all_companies) % 5 == 0:
                        save_progress()
                    
                    # Small delay to avoid rate limits
                    time.sleep(1.5)
                except Exception as error:
                    print(f"  ❌ Failed to process {company['name']}: {error}")
            
            print(f"\n✅ Completed {country['name']}: {processed}/{total} companies researched")
            
            # Save progress after each country
            save_progress()
            
            # Delay between countries
            if i < len(EU_COUNTRIES):
                time.sleep(2)
        
        # Step 3: Save final results
        print(f"\n{'=' * 60}")
        print(f"💾 Saving {len(all_companies)} companies to CSV...")
        save_csv()
        print(f"✅ Data saved to: {csv_path}")
        
        # Also save as JSON
        json_path = output_dir / 'prefab_core.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_companies, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON backup saved to: {json_path}")
        
        # Print summary
        print(f"\n📊 Summary:")
        print(f"   Total companies: {len(all_companies)}")
        print(f"   With webpage: {sum(1 for c in all_companies if c.get('webpage'))}")
        print(f"   With configurator: {sum(1 for c in all_companies if c.get('configurator'))}")
        print(f"   With pricing: {sum(1 for c in all_companies if c.get('min_home_price'))}")
        
        # Country breakdown
        country_counts = {}
        for company in all_companies:
            address = company.get('address') or ''
            found = False
            if address:
                for country in EU_COUNTRIES:
                    if country['name'] in address:
                        country_counts[country['name']] = country_counts.get(country['name'], 0) + 1
                        found = True
                        break
            if not found:
                country_counts['Unknown'] = country_counts.get('Unknown', 0) + 1
        
        print(f"\n📈 Companies by country:")
        for country, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {country}: {count}")
        
        print(f"\n🎉 Research complete! Processed {len(all_companies)} companies across {len(EU_COUNTRIES)} countries.")
        
    except Exception as error:
        print(f'❌ Fatal error: {error}')
        save_progress()
        sys.exit(1)

if __name__ == '__main__':
    main()
