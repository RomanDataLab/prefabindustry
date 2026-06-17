// Deep continuous research of EU prefab home companies using OpenAI
const OpenAI = require('openai');
const apiManager = require('../configix/apiManager');
const fs = require('fs');
const path = require('path');
const createCsvWriter = require('csv-writer').createObjectCsvWriter;

// Initialize OpenAI with API key from configix
const openaiConfig = apiManager.getAIProvider('ai_openai');
const openai = new OpenAI({
  apiKey: openaiConfig.apiKey
});

// Output file
const outputDir = path.join(__dirname, '..', 'research_output');
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}
const csvPath = path.join(outputDir, 'prefab_core.csv');

// CSV Writer configuration
const csvWriter = createCsvWriter({
  path: csvPath,
  header: [
    { id: 'id', title: 'id' },
    { id: 'brand', title: 'brand' },
    { id: 'head_office_legal_name', title: 'head_office_legal_name' },
    { id: 'address', title: 'address' },
    { id: 'webpage', title: 'webpage' },
    { id: 'configurator', title: 'configurator' },
    { id: 'models_amount', title: 'models_amount' },
    { id: 'min_sqm', title: 'min_sqm' },
    { id: 'max_sqm', title: 'max_sqm' },
    { id: 'main_structure_material', title: 'main_structure_material' },
    { id: 'min_home_price', title: 'min_home_price' },
    { id: 'average_price_sqm', title: 'average_price_sqm' }
  ]
});

// Store all companies
let allCompanies = [];
let companyId = 1;

// EU countries with their local languages for research
const euCountries = [
  { code: 'DE', name: 'Germany', language: 'German', nativeName: 'Deutschland' },
  { code: 'FR', name: 'France', language: 'French', nativeName: 'France' },
  { code: 'IT', name: 'Italy', language: 'Italian', nativeName: 'Italia' },
  { code: 'ES', name: 'Spain', language: 'Spanish', nativeName: 'España' },
  { code: 'NL', name: 'Netherlands', language: 'Dutch', nativeName: 'Nederland' },
  { code: 'BE', name: 'Belgium', language: 'Dutch/French', nativeName: 'België/Belgique' },
  { code: 'AT', name: 'Austria', language: 'German', nativeName: 'Österreich' },
  { code: 'SE', name: 'Sweden', language: 'Swedish', nativeName: 'Sverige' },
  { code: 'DK', name: 'Denmark', language: 'Danish', nativeName: 'Danmark' },
  { code: 'FI', name: 'Finland', language: 'Finnish', nativeName: 'Suomi' },
  { code: 'PL', name: 'Poland', language: 'Polish', nativeName: 'Polska' },
  { code: 'CZ', name: 'Czech Republic', language: 'Czech', nativeName: 'Česká republika' },
  { code: 'PT', name: 'Portugal', language: 'Portuguese', nativeName: 'Portugal' },
  { code: 'GR', name: 'Greece', language: 'Greek', nativeName: 'Ελλάδα' },
  { code: 'IE', name: 'Ireland', language: 'English', nativeName: 'Ireland' },
  { code: 'RO', name: 'Romania', language: 'Romanian', nativeName: 'România' },
  { code: 'HU', name: 'Hungary', language: 'Hungarian', nativeName: 'Magyarország' },
  { code: 'SK', name: 'Slovakia', language: 'Slovak', nativeName: 'Slovensko' },
  { code: 'BG', name: 'Bulgaria', language: 'Bulgarian', nativeName: 'България' },
  { code: 'HR', name: 'Croatia', language: 'Croatian', nativeName: 'Hrvatska' },
  { code: 'SI', name: 'Slovenia', language: 'Slovenian', nativeName: 'Slovenija' },
  { code: 'LT', name: 'Lithuania', language: 'Lithuanian', nativeName: 'Lietuva' },
  { code: 'LV', name: 'Latvia', language: 'Latvian', nativeName: 'Latvija' },
  { code: 'EE', name: 'Estonia', language: 'Estonian', nativeName: 'Eesti' },
  { code: 'LU', name: 'Luxembourg', language: 'Luxembourgish/French', nativeName: 'Lëtzebuerg' },
  { code: 'MT', name: 'Malta', language: 'Maltese', nativeName: 'Malta' },
  { code: 'CY', name: 'Cyprus', language: 'Greek', nativeName: 'Κύπρος' }
];

/**
 * Call OpenAI API with retry logic
 */
async function callOpenAI(messages, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await openai.chat.completions.create({
        model: 'gpt-4o',
        messages: messages,
        temperature: 0.7,
        max_tokens: 4000
      });
      return response.choices[0].message.content;
    } catch (error) {
      console.error(`Attempt ${i + 1} failed:`, error.message);
      if (i === maxRetries - 1) throw error;
      await new Promise(resolve => setTimeout(resolve, 2000 * (i + 1)));
    }
  }
}

/**
 * Get companies for a specific country using local language
 */
async function getCompaniesForCountry(country) {
  const language = country.language.split('/')[0]; // Use first language if multiple
  const countryNameNative = country.nativeName.split('/')[0];
  
  // Create prompt in local language
  const prompt = `Du bist ein Forschungsexperte für vorgefertigte/modulare Hausunternehmen.`; // German example
  
  // Build prompt based on language
  let localPrompt = '';
  switch (language) {
    case 'German':
      localPrompt = `Du bist ein Forschungsexperte für vorgefertigte/modulare Hausunternehmen in ${countryNameNative}.

Bitte erstelle eine umfassende Liste ALLER Unternehmen in ${countryNameNative}, die vorgefertigte Häuser (Fertighäuser, Modulhäuser, Bausatzhäuser, Plattenhäuser usw.) herstellen.

Schließe ein:
- Große Hersteller
- Mittlere Unternehmen
- Regionale Hersteller
- Spezialisierte Anbieter (Luxus, ökologisch, etc.)

Gib NUR ein JSON-Array zurück: [{"name": "Firmenname", "country": "${country.name}"}, ...]`;
      break;
    case 'French':
      localPrompt = `Vous êtes un expert en recherche spécialisé dans les entreprises de maisons préfabriquées/modulaires en ${countryNameNative}.

Veuillez fournir une liste complète de TOUTES les entreprises en ${countryNameNative} qui fabriquent des maisons préfabriquées (maisons préfabriquées, maisons modulaires, maisons en kit, maisons panneaux, etc.).

Incluez:
- Grands fabricants
- Entreprises de taille moyenne
- Fabricants régionaux
- Constructeurs spécialisés (luxe, écologique, etc.)

Retournez UNIQUEMENT un tableau JSON: [{"name": "Nom de l'entreprise", "country": "${country.name}"}, ...]`;
      break;
    case 'Italian':
      localPrompt = `Sei un esperto di ricerca specializzato in aziende di case prefabbricate/modulari in ${countryNameNative}.

Fornisci un elenco completo di TUTTE le aziende in ${countryNameNative} che producono case prefabbricate (case prefabbricate, case modulari, case in kit, case pannelli, ecc.).

Includi:
- Grandi produttori
- Aziende di medie dimensioni
- Produttori regionali
- Costruttori specializzati (lusso, ecologico, ecc.)

Restituisci SOLO un array JSON: [{"name": "Nome azienda", "country": "${country.name}"}, ...]`;
      break;
    case 'Spanish':
      localPrompt = `Eres un experto en investigación especializado en empresas de casas prefabricadas/modulares en ${countryNameNative}.

Proporciona una lista completa de TODAS las empresas en ${countryNameNative} que fabrican casas prefabricadas (casas prefabricadas, casas modulares, casas kit, casas panelizadas, etc.).

Incluye:
- Grandes fabricantes
- Empresas medianas
- Fabricantes regionales
- Constructores especializados (lujo, ecológico, etc.)

Devuelve SOLO un array JSON: [{"name": "Nombre de empresa", "country": "${country.name}"}, ...]`;
      break;
    case 'Dutch':
      localPrompt = `Je bent een onderzoeksdeskundige gespecialiseerd in geprefabriceerde/modulaire woningbouwbedrijven in ${countryNameNative}.

Geef een uitgebreide lijst van ALLE bedrijven in ${countryNameNative} die geprefabriceerde woningen (prefabwoningen, modulaire woningen, bouwpakketwoningen, paneelwoningen, etc.) produceren.

Inclusief:
- Grote fabrikanten
- Middelgrote bedrijven
- Regionale fabrikanten
- Gespecialiseerde bouwers (luxe, ecologisch, etc.)

Geef ALLEEN een JSON-array terug: [{"name": "Bedrijfsnaam", "country": "${country.name}"}, ...]`;
      break;
    case 'Swedish':
      localPrompt = `Du är en forskningsexpert specialiserad på prefabricerade/modulära husföretag i ${countryNameNative}.

Ge en omfattande lista över ALLA företag i ${countryNameNative} som tillverkar prefabricerade hus (prefabhus, modulhus, kithus, panelhus, etc.).

Inkludera:
- Stora tillverkare
- Medelstora företag
- Regionala tillverkare
- Specialiserade byggare (lyx, miljövänliga, etc.)

Returnera ENDAST en JSON-array: [{"name": "Företagsnamn", "country": "${country.name}"}, ...]`;
      break;
    case 'Polish':
      localPrompt = `Jesteś ekspertem badawczym specjalizującym się w firmach domów prefabrykowanych/modularnych w ${countryNameNative}.

Podaj kompleksową listę WSZYSTKICH firm w ${countryNameNative}, które produkują domy prefabrykowane (domy prefabrykowane, domy modułowe, domy z zestawów, domy panelowe itp.).

Uwzględnij:
- Dużych producentów
- Średnie firmy
- Regionalnych producentów
- Specjalistycznych budowniczych (luksusowe, ekologiczne itp.)

Zwróć TYLKO tablicę JSON: [{"name": "Nazwa firmy", "country": "${country.name}"}, ...]`;
      break;
    case 'Portuguese':
      localPrompt = `És um especialista em investigação especializado em empresas de casas pré-fabricadas/modulares em ${countryNameNative}.

Fornece uma lista abrangente de TODAS as empresas em ${countryNameNative} que fabricam casas pré-fabricadas (casas pré-fabricadas, casas modulares, casas kit, casas painelizadas, etc.).

Inclui:
- Grandes fabricantes
- Empresas de médio porte
- Fabricantes regionais
- Construtores especializados (luxo, ecológico, etc.)

Retorna APENAS um array JSON: [{"name": "Nome da empresa", "country": "${country.name}"}, ...]`;
      break;
    default:
      // English fallback
      localPrompt = `You are a research expert specializing in prefabricated/modular home companies in ${country.name}.

Please provide a comprehensive list of ALL companies in ${country.name} that manufacture prefab homes (prefabricated homes, modular homes, kit homes, panelized homes, etc.).

Include:
- Large manufacturers
- Medium-sized companies
- Regional manufacturers
- Specialized builders (luxury, eco-friendly, etc.)

Return ONLY a JSON array: [{"name": "Company Name", "country": "${country.name}"}, ...]`;
  }
  
  try {
    const response = await callOpenAI([{ role: 'user', content: localPrompt }]);
    
    // Extract JSON from response
    const jsonMatch = response.match(/\[[\s\S]*\]/);
    if (jsonMatch) {
      try {
        const companies = JSON.parse(jsonMatch[0]);
        // Ensure country is set correctly
        return companies.map(c => ({ ...c, country: country.name }));
      } catch (e) {
        console.error(`  ⚠️  Error parsing JSON for ${country.name}:`, e.message);
        const extracted = extractCompanyNames(response);
        return extracted.map(c => ({ ...c, country: country.name }));
      }
    }
    
    const extracted = extractCompanyNames(response);
    return extracted.map(c => ({ ...c, country: country.name }));
  } catch (error) {
    console.error(`  ❌ Error researching ${country.name}:`, error.message);
    return [];
  }
}

/**
 * Extract company names from text response
 */
function extractCompanyNames(text) {
  const companies = [];
  const lines = text.split('\n').filter(line => line.trim());
  
  for (const line of lines) {
    const match = line.match(/(?:^|\d+\.\s*)(.+?)(?:\s*[-–]\s*)?([A-Z][a-z]+)?$/);
    if (match) {
      companies.push({
        name: match[1].trim(),
        country: match[2] || 'Unknown'
      });
    }
  }
  
  return companies;
}

/**
 * Check if company has an online configurator and get direct link
 */
async function checkConfigurator(companyName, webpage) {
  if (!webpage) {
    return null;
  }
  
  const prompt = `You are checking if a prefab home company has an online configurator tool where users can model or configure homes online.

Company: ${companyName}
Website: ${webpage}

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

Return ONLY the URL or NaN, nothing else.`;

  try {
    const response = await callOpenAI([{ role: 'user', content: prompt }]);
    const result = response.trim();
    
    // Check if it's a valid URL
    if (result && result !== 'NaN' && result !== 'null' && (result.startsWith('http://') || result.startsWith('https://'))) {
      return result;
    }
    
    return null; // Will be converted to NaN in CSV
  } catch (error) {
    console.error(`  ⚠️  Error checking configurator for ${companyName}:`, error.message);
    return null;
  }
}

/**
 * Research detailed information about a single company using local language but returning English results
 */
async function researchCompany(companyName, country, countryInfo) {
  console.log(`\n📊 Researching: ${companyName} (${country})`);
  
  const language = countryInfo ? countryInfo.language.split('/')[0] : 'English';
  
  // Build prompt in local language but request English output
  let localPrompt = '';
  switch (language) {
    case 'German':
      localPrompt = `Du bist ein professioneller Forscher, der detaillierte Informationen über ein Unternehmen für vorgefertigte/modulare Häuser in ${countryInfo.nativeName} sammelt.

Zu recherchierendes Unternehmen: ${companyName}
Land: ${country}

Führe gründliche Recherchen durch und gib umfassende, genaue Informationen zurück. Gib NUR gültiges JSON in diesem exakten Format zurück (verwende null für fehlende Daten, NaN für numerische Felder, die nicht bestimmt werden können):

{
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
}

KRITISCHE ANFORDERUNGEN:
- Alle Antworten müssen auf ENGLISCH sein, auch wenn die Recherche auf Deutsch durchgeführt wird
- Für "configurator": Nur URL angeben, wenn sie ein Online-Tool haben, mit dem Kunden Hausoptionen konfigurieren/kombinieren können
- Alle Preise in EUR umrechnen
- Nur verifizierte, faktische Informationen einbeziehen
- Gib NUR das JSON-Objekt zurück, keine Erklärungen oder zusätzlichen Text`;
      break;
    case 'French':
      localPrompt = `Vous êtes un chercheur professionnel recueillant des informations détaillées sur une entreprise de maisons préfabriquées/modulaires en ${countryInfo.nativeName}.

Entreprise à rechercher: ${companyName}
Pays: ${country}

Effectuez des recherches approfondies et fournissez des informations complètes et précises. Retournez UNIQUEMENT un JSON valide dans ce format exact (utilisez null pour les données manquantes, NaN pour les champs numériques qui ne peuvent pas être déterminés):

{
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
}

EXIGENCES CRITIQUES:
- Toutes les réponses doivent être en ANGLAIS, même si la recherche est effectuée en français
- Pour "configurator": Fournir l'URL uniquement s'ils ont un outil en ligne permettant aux clients de configurer/combiner des options de maison
- Convertir tous les prix en EUR
- N'inclure que des informations vérifiées et factuelles
- Retourner UNIQUEMENT l'objet JSON, aucune explication ou texte supplémentaire`;
      break;
    case 'Italian':
      localPrompt = `Sei un ricercatore professionale che raccoglie informazioni dettagliate su un'azienda di case prefabbricate/modulari in ${countryInfo.nativeName}.

Azienda da ricercare: ${companyName}
Paese: ${country}

Conduci ricerche approfondite e fornisci informazioni complete e accurate. Restituisci SOLO JSON valido in questo formato esatto (usa null per dati mancanti, NaN per campi numerici che non possono essere determinati):

{
  "brand": "nome del marchio o nome commerciale (il nome con cui i clienti li conoscono)",
  "head_office_legal_name": "nome legale completo dell'azienda",
  "address": "indirizzo completo: numero civico, nome della via, città, codice postale, paese",
  "webpage": "URL della homepage del sito web principale (https://...)",
  "configurator": "URL diretto alla pagina dello strumento configuratore/combinatore online se ne hanno uno (es: /configurator, /design-your-home, /home-configurator), altrimenti null",
  "models_amount": numero di modelli/design di case prefabbricate diversi che attualmente offrono (intero, conta i modelli effettivi),
  "min_sqm": metri quadrati minimi del loro modello più piccolo disponibile (numero, superficie abitabile),
  "max_sqm": metri quadrati massimi del loro modello più grande disponibile (numero, superficie abitabile),
  "main_structure_material": "materiale di costruzione principale: legno/legno/cemento/acciaio/composito/CLT/legno lamellare incrociato/ecc",
  "min_home_price": prezzo minimo in EUR per il loro modello più economico (numero, convertire da altre valute se necessario, prezzo base senza terreno),
  "average_price_sqm": prezzo medio per metro quadrato in EUR tra i loro modelli (numero, calcolato dai loro prezzi)
}

REQUISITI CRITICI:
- Tutte le risposte devono essere in INGLESE, anche se la ricerca viene condotta in italiano
- Per "configurator": Fornire l'URL solo se hanno uno strumento online che consente ai clienti di configurare/combinare opzioni di casa
- Convertire tutti i prezzi in EUR
- Includere solo informazioni verificate e fattuali
- Restituire SOLO l'oggetto JSON, nessuna spiegazione o testo aggiuntivo`;
      break;
    case 'Spanish':
      localPrompt = `Eres un investigador profesional que recopila información detallada sobre una empresa de casas prefabricadas/modulares en ${countryInfo.nativeName}.

Empresa a investigar: ${companyName}
País: ${country}

Realiza una investigación exhaustiva y proporciona información completa y precisa. Devuelve SOLO JSON válido en este formato exacto (usa null para datos faltantes, NaN para campos numéricos que no se pueden determinar):

{
  "brand": "nombre de marca o nombre comercial (el nombre por el que los clientes los conocen)",
  "head_office_legal_name": "nombre legal completo de la empresa",
  "address": "dirección completa: número de calle, nombre de calle, ciudad, código postal, país",
  "webpage": "URL de la página de inicio del sitio web principal (https://...)",
  "configurator": "URL directa a la página de la herramienta configurador/combinador en línea si tienen una (ej: /configurator, /design-your-home, /home-configurator), de lo contrario null",
  "models_amount": número de modelos/diseños de casas prefabricadas diferentes que actualmente ofrecen (entero, contar modelos reales),
  "min_sqm": metros cuadrados mínimos de su modelo más pequeño disponible (número, área habitable),
  "max_sqm": metros cuadrados máximos de su modelo más grande disponible (número, área habitable),
  "main_structure_material": "material de construcción principal: madera/madera/hormigón/acero/compuesto/CLT/madera laminada cruzada/etc",
  "min_home_price": precio mínimo en EUR para su modelo más barato (número, convertir de otras monedas si es necesario, precio base sin terreno),
  "average_price_sqm": precio promedio por metro cuadrado en EUR entre sus modelos (número, calculado a partir de sus precios)
}

REQUISITOS CRÍTICOS:
- Todas las respuestas deben estar en INGLÉS, incluso si la investigación se realiza en español
- Para "configurator": Proporcionar la URL solo si tienen una herramienta en línea que permite a los clientes configurar/combinar opciones de casa
- Convertir todos los precios a EUR
- Incluir solo información verificada y factual
- Devolver SOLO el objeto JSON, sin explicaciones o texto adicional`;
      break;
    case 'Dutch':
      localPrompt = `Je bent een professionele onderzoeker die gedetailleerde informatie verzamelt over een bedrijf voor geprefabriceerde/modulaire woningen in ${countryInfo.nativeName}.

Bedrijf om te onderzoeken: ${companyName}
Land: ${country}

Voer grondig onderzoek uit en verstrek uitgebreide, accurate informatie. Geef ALLEEN geldige JSON terug in dit exacte formaat (gebruik null voor ontbrekende gegevens, NaN voor numerieke velden die niet kunnen worden bepaald):

{
  "brand": "merknaam of handelsnaam (de naam waaronder klanten ze kennen)",
  "head_office_legal_name": "volledige juridische bedrijfsnaam",
  "address": "volledig adres: straatnummer, straatnaam, stad, postcode, land",
  "webpage": "hoofdwebsite homepage URL (https://...)",
  "configurator": "directe URL naar de online configurator/combinator tool pagina als ze er een hebben (bijv. /configurator, /design-your-home, /home-configurator), anders null",
  "models_amount": aantal verschillende geprefabriceerde woningmodellen/ontwerpen die ze momenteel aanbieden (geheel getal, tel werkelijke modellen),
  "min_sqm": minimum vierkante meters van hun kleinste beschikbare model (nummer, woonoppervlakte),
  "max_sqm": maximum vierkante meters van hun grootste beschikbare model (nummer, woonoppervlakte),
  "main_structure_material": "hoofdconstructiemateriaal: hout/hout/beton/staal/composiet/CLT/kruislaaghout/etc",
  "min_home_price": minimale startprijs in EUR voor hun goedkoopste model (nummer, converteer van andere valuta's indien nodig, basisprijs zonder grond),
  "average_price_sqm": gemiddelde prijs per vierkante meter in EUR over hun modellen (nummer, berekend uit hun prijzen)
}

KRITIEKE VEREISTEN:
- Alle antwoorden moeten in het ENGELS zijn, zelfs als het onderzoek in het Nederlands wordt uitgevoerd
- Voor "configurator": Geef alleen URL op als ze een online tool hebben waarmee klanten huisopties kunnen configureren/combineren
- Converteer alle prijzen naar EUR
- Neem alleen geverifieerde, feitelijke informatie op
- Geef ALLEEN het JSON-object terug, geen uitleg of aanvullende tekst`;
      break;
    case 'Swedish':
      localPrompt = `Du är en professionell forskare som samlar detaljerad information om ett företag för prefabricerade/modulära hus i ${countryInfo.nativeName}.

Företag att forskning: ${companyName}
Land: ${country}

Genomför noggrann forskning och ge omfattande, korrekt information. Returnera ENDAST giltig JSON i detta exakta format (använd null för saknade data, NaN för numeriska fält som inte kan bestämmas):

{
  "brand": "varumärkesnamn eller handelsnamn (namnet kunderna känner dem under)",
  "head_office_legal_name": "fullständigt juridiskt företagsnamn",
  "address": "fullständig adress: gatunummer, gatunamn, stad, postnummer, land",
  "webpage": "huvudwebbsida hemsida URL (https://...)",
  "configurator": "direkt URL till onlinekonfigurator/kombinatortool-sidan om de har en (t.ex. /configurator, /design-your-home, /home-configurator), annars null",
  "models_amount": antal olika prefabricerade husmodeller/designs de för närvarande erbjuder (heltal, räkna faktiska modeller),
  "min_sqm": minsta kvadratmeter av deras minsta tillgängliga modell (nummer, boyta),
  "max_sqm": maximala kvadratmeter av deras största tillgängliga modell (nummer, boyta),
  "main_structure_material": "huvudkonstruktionsmaterial: trä/trä/betong/stål/komposit/CLT/korslimmat trä/etc",
  "min_home_price": minimistartpris i EUR för deras billigaste modell (nummer, konvertera från andra valutor om nödvändigt, baspris utan mark),
  "average_price_sqm": genomsnittligt pris per kvadratmeter i EUR över deras modeller (nummer, beräknat från deras priser)
}

KRITISKA KRAV:
- Alla svar måste vara på ENGELSKA, även om forskningen utförs på svenska
- För "configurator": Ge endast URL om de har ett onlineverktyg där kunder kan konfigurera/kombinera husalternativ
- Konvertera alla priser till EUR
- Inkludera endast verifierad, faktisk information
- Returnera ENDAST JSON-objektet, inga förklaringar eller ytterligare text`;
      break;
    case 'Polish':
      localPrompt = `Jesteś profesjonalnym badaczem zbierającym szczegółowe informacje o firmie domów prefabrykowanych/modularnych w ${countryInfo.nativeName}.

Firma do zbadania: ${companyName}
Kraj: ${country}

Przeprowadź dokładne badania i dostarcz kompleksowe, dokładne informacje. Zwróć TYLKO prawidłowy JSON w tym dokładnym formacie (użyj null dla brakujących danych, NaN dla pól numerycznych, których nie można określić):

{
  "brand": "nazwa marki lub nazwa handlowa (nazwa, pod którą klienci ich znają)",
  "head_office_legal_name": "pełna prawna nazwa firmy",
  "address": "pełny adres: numer ulicy, nazwa ulicy, miasto, kod pocztowy, kraj",
  "webpage": "główna strona internetowa URL (https://...)",
  "configurator": "bezpośredni URL do strony narzędzia konfiguratora/kombinatora online, jeśli mają (np. /configurator, /design-your-home, /home-configurator), w przeciwnym razie null",
  "models_amount": liczba różnych modeli/projektów domów prefabrykowanych, które obecnie oferują (liczba całkowita, policz rzeczywiste modele),
  "min_sqm": minimalne metry kwadratowe ich najmniejszego dostępnego modelu (liczba, powierzchnia mieszkalna),
  "max_sqm": maksymalne metry kwadratowe ich największego dostępnego modelu (liczba, powierzchnia mieszkalna),
  "main_structure_material": "główny materiał konstrukcyjny: drewno/drewno/beton/stal/kompozyt/CLT/krzyżowo klejone drewno/itp",
  "min_home_price": minimalna cena startowa w EUR dla ich najtańszego modelu (liczba, konwertuj z innych walut w razie potrzeby, cena bazowa bez gruntu),
  "average_price_sqm": średnia cena za metr kwadratowy w EUR w ich modelach (liczba, obliczona z ich cen)
}

KRYTYCZNE WYMAGANIA:
- Wszystkie odpowiedzi muszą być w JĘZYKU ANGIELSKIM, nawet jeśli badania są prowadzone po polsku
- Dla "configurator": Podaj URL tylko wtedy, gdy mają narzędzie online, które pozwala klientom konfigurować/łączyć opcje domów
- Konwertuj wszystkie ceny na EUR
- Uwzględnij tylko zweryfikowane, faktyczne informacje
- Zwróć TYLKO obiekt JSON, bez wyjaśnień lub dodatkowego tekstu`;
      break;
    case 'Portuguese':
      localPrompt = `És um investigador profissional a recolher informações detalhadas sobre uma empresa de casas pré-fabricadas/modulares em ${countryInfo.nativeName}.

Empresa a investigar: ${companyName}
País: ${country}

Realiza uma investigação aprofundada e fornece informações completas e precisas. Retorna APENAS JSON válido neste formato exato (usa null para dados em falta, NaN para campos numéricos que não podem ser determinados):

{
  "brand": "nome da marca ou nome comercial (o nome pelo qual os clientes os conhecem)",
  "head_office_legal_name": "nome legal completo da empresa",
  "address": "endereço completo: número da rua, nome da rua, cidade, código postal, país",
  "webpage": "URL da página inicial do site principal (https://...)",
  "configurator": "URL direta para a página da ferramenta configurador/combinador online se tiverem uma (ex: /configurator, /design-your-home, /home-configurator), caso contrário null",
  "models_amount": número de modelos/designs de casas pré-fabricadas diferentes que atualmente oferecem (inteiro, conta modelos reais),
  "min_sqm": metros quadrados mínimos do seu modelo mais pequeno disponível (número, área habitável),
  "max_sqm": metros quadrados máximos do seu modelo maior disponível (número, área habitável),
  "main_structure_material": "material de construção principal: madeira/madeira/betão/aço/compósito/CLT/madeira laminada cruzada/etc",
  "min_home_price": preço mínimo inicial em EUR para o seu modelo mais barato (número, converte de outras moedas se necessário, preço base sem terreno),
  "average_price_sqm": preço médio por metro quadrado em EUR nos seus modelos (número, calculado a partir dos seus preços)
}

REQUISITOS CRÍTICOS:
- Todas as respostas devem estar em INGLÊS, mesmo que a investigação seja realizada em português
- Para "configurator": Fornecer URL apenas se tiverem uma ferramenta online que permite aos clientes configurar/combinar opções de casa
- Converter todos os preços para EUR
- Incluir apenas informações verificadas e factuais
- Retornar APENAS o objeto JSON, sem explicações ou texto adicional`;
      break;
    default:
      // English fallback
      localPrompt = `You are a professional researcher gathering detailed information about a prefabricated/modular home company in ${country}.

Company to research: ${companyName}
Country: ${country}

Conduct thorough research and provide comprehensive, accurate information. Return ONLY valid JSON in this exact format (use null for missing data, NaN for numeric fields that cannot be determined):

{
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
}

CRITICAL REQUIREMENTS:
- For "configurator": Only provide URL if they have an online tool where customers can configure/combine home options. If it's just a contact form or gallery, use null. Must be direct link to the configurator page.
- Convert ALL prices to EUR (use current exchange rates)
- "models_amount" should be the actual count of different home models/designs they offer
- "min_sqm" and "max_sqm" refer to living area/square meters of the homes
- Be precise with addresses - include full street address when possible
- For "main_structure_material", use the most common material (wood, concrete, steel, etc.)
- Only include verified, factual information
- Return ONLY the JSON object, no explanations or additional text before/after`;
  }

  try {
    const response = await callOpenAI([{ role: 'user', content: localPrompt }]);
    
    // Extract JSON from response
    const jsonMatch = response.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const data = JSON.parse(jsonMatch[0]);
        
        // Validate and clean data (configurator will be checked separately)
        const result = {
          id: companyId++,
          brand: data.brand || companyName,
          head_office_legal_name: data.head_office_legal_name || null,
          address: data.address || null,
          webpage: data.webpage || null,
          configurator: null, // Will be set by checkConfigurator function
          models_amount: (data.models_amount !== null && data.models_amount !== undefined && !isNaN(data.models_amount)) ? parseInt(data.models_amount) : null,
          min_sqm: (data.min_sqm !== null && data.min_sqm !== undefined && !isNaN(data.min_sqm)) ? parseFloat(data.min_sqm) : null,
          max_sqm: (data.max_sqm !== null && data.max_sqm !== undefined && !isNaN(data.max_sqm)) ? parseFloat(data.max_sqm) : null,
          main_structure_material: data.main_structure_material || null,
          min_home_price: (data.min_home_price !== null && data.min_home_price !== undefined && !isNaN(data.min_home_price)) ? parseFloat(data.min_home_price) : null,
          average_price_sqm: (data.average_price_sqm !== null && data.average_price_sqm !== undefined && !isNaN(data.average_price_sqm)) ? parseFloat(data.average_price_sqm) : null
        };
        
        // Replace NaN strings with null (except configurator which will be checked separately)
        Object.keys(result).forEach(key => {
          if (key !== 'configurator' && (result[key] === 'NaN' || result[key] === 'null' || (typeof result[key] === 'number' && isNaN(result[key])))) {
            result[key] = null;
          }
        });
        
        // Check for configurator using OpenAI
        if (result.webpage) {
          console.log(`  🔍 Checking configurator for ${companyName}...`);
          const configuratorUrl = await checkConfigurator(companyName, result.webpage);
          result.configurator = configuratorUrl || null; // null will be written as NaN in CSV
          await new Promise(resolve => setTimeout(resolve, 500)); // Small delay
        } else {
          result.configurator = null; // No webpage, so no configurator
        }
        
        return result;
      } catch (e) {
        console.error(`  ⚠️  Error parsing JSON for ${companyName}:`, e.message);
        console.error(`  Response snippet: ${response.substring(0, 200)}...`);
        return createDefaultEntry(companyName, country);
      }
    }
    
    return createDefaultEntry(companyName, country);
  } catch (error) {
    console.error(`  ❌ Error researching ${companyName}:`, error.message);
    return createDefaultEntry(companyName, country);
  }
}

/**
 * Create default entry when research fails
 */
function createDefaultEntry(companyName, country) {
  return {
    id: companyId++,
    brand: companyName,
    head_office_legal_name: null,
    address: null,
    webpage: null,
    configurator: null,
    models_amount: null,
    min_sqm: null,
    max_sqm: null,
    main_structure_material: null,
    min_home_price: null,
    average_price_sqm: null
  };
}

/**
 * Save progress to JSON backup
 */
function saveProgress() {
  const backupPath = path.join(outputDir, 'progress_backup.json');
  fs.writeFileSync(backupPath, JSON.stringify(allCompanies, null, 2));
  console.log(`💾 Progress saved: ${allCompanies.length} companies`);
}

/**
 * Load existing progress if available
 */
function loadProgress() {
  const backupPath = path.join(outputDir, 'progress_backup.json');
  if (fs.existsSync(backupPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(backupPath, 'utf8'));
      if (Array.isArray(data) && data.length > 0) {
        allCompanies = data;
        companyId = Math.max(...data.map(c => c.id || 0)) + 1;
        console.log(`📂 Loaded ${allCompanies.length} companies from previous session`);
        return true;
      }
    } catch (e) {
      console.log('⚠️  Could not load previous progress:', e.message);
    }
  }
  return false;
}

/**
 * Main research function - country by country
 */
async function main() {
  console.log('🚀 Starting deep continuous research of EU prefab home companies...\n');
  console.log(`Using OpenAI API (${openaiConfig.name})\n`);
  console.log(`Researching ${euCountries.length} EU countries one by one using local languages\n`);
  
  // Check for existing progress
  const hasProgress = loadProgress();
  
  // Track which countries have been processed
  const processedCountries = hasProgress 
    ? new Set(allCompanies.map(c => {
        // Try to extract country from address or use a default
        const address = c.address || '';
        for (const country of euCountries) {
          if (address.includes(country.name)) return country.code;
        }
        return null;
      }).filter(Boolean))
    : new Set();
  
  try {
    // Process each country
    for (let i = 0; i < euCountries.length; i++) {
      const country = euCountries[i];
      
      if (processedCountries.has(country.code)) {
        console.log(`\n⏭️  Skipping ${country.name} (already processed)`);
        continue;
      }
      
      console.log(`\n${'='.repeat(60)}`);
      console.log(`🌍 Country ${i + 1}/${euCountries.length}: ${country.name} (${country.language})`);
      console.log(`${'='.repeat(60)}\n`);
      
      // Step 1: Get companies for this country using local language
      console.log(`🔍 Discovering companies in ${country.name}...`);
      const companies = await getCompaniesForCountry(country);
      
      if (companies.length === 0) {
        console.log(`  ⚠️  No companies found for ${country.name}`);
        await new Promise(resolve => setTimeout(resolve, 1000));
        continue;
      }
      
      console.log(`  ✅ Found ${companies.length} companies in ${country.name}\n`);
      
      // Step 2: Research each company for this country
      let processed = 0;
      const total = companies.length;
      
      for (const company of companies) {
        try {
          const companyData = await researchCompany(company.name, company.country, country);
          allCompanies.push(companyData);
          processed++;
          
          console.log(`  ✅ [${processed}/${total}] Completed: ${companyData.brand}`);
          
          // Save progress every 5 companies
          if (allCompanies.length % 5 === 0) {
            saveProgress();
          }
          
          // Small delay to avoid rate limits
          await new Promise(resolve => setTimeout(resolve, 1500));
        } catch (error) {
          console.error(`  ❌ Failed to process ${company.name}:`, error.message);
        }
      }
      
      console.log(`\n✅ Completed ${country.name}: ${processed}/${total} companies researched`);
      
      // Save progress after each country
      saveProgress();
      
      // Delay between countries
      if (i < euCountries.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    }
    
    // Step 3: Save final results
    console.log(`\n${'='.repeat(60)}`);
    console.log(`💾 Saving ${allCompanies.length} companies to CSV...`);
    
    // Convert null configurator to NaN string for CSV
    const csvData = allCompanies.map(company => ({
      ...company,
      configurator: company.configurator || 'NaN'
    }));
    
    await csvWriter.writeRecords(csvData);
    console.log(`✅ Data saved to: ${csvPath}`);
    
    // Also save as JSON
    const jsonPath = path.join(outputDir, 'prefab_core.json');
    fs.writeFileSync(jsonPath, JSON.stringify(allCompanies, null, 2));
    console.log(`✅ JSON backup saved to: ${jsonPath}`);
    
    // Print summary
    console.log(`\n📊 Summary:`);
    console.log(`   Total companies: ${allCompanies.length}`);
    console.log(`   With webpage: ${allCompanies.filter(c => c.webpage).length}`);
    console.log(`   With configurator: ${allCompanies.filter(c => c.configurator).length}`);
    console.log(`   With pricing: ${allCompanies.filter(c => c.min_home_price).length}`);
    
    // Country breakdown
    const countryCounts = {};
    allCompanies.forEach(c => {
      const address = c.address || '';
      let found = false;
      for (const country of euCountries) {
        if (address.includes(country.name)) {
          countryCounts[country.name] = (countryCounts[country.name] || 0) + 1;
          found = true;
          break;
        }
      }
      if (!found) {
        countryCounts['Unknown'] = (countryCounts['Unknown'] || 0) + 1;
      }
    });
    
    console.log(`\n📈 Companies by country:`);
    Object.entries(countryCounts)
      .sort((a, b) => b[1] - a[1])
      .forEach(([country, count]) => {
        console.log(`   ${country}: ${count}`);
      });
    
    console.log(`\n🎉 Research complete! Processed ${allCompanies.length} companies across ${euCountries.length} countries.`);
    
  } catch (error) {
    console.error('❌ Fatal error:', error);
    saveProgress(); // Save what we have
    process.exit(1);
  }
}

// Run the research
if (require.main === module) {
  main().catch(console.error);
}

module.exports = { main, researchCompany, getCompaniesForCountry };
