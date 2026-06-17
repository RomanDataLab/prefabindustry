# Prefab Project - Architecture & Data Schema

## CSV Schema (`prefabworldfin_reducedby_7.csv`)

| # | Column | Type | Example |
|---|--------|------|---------|
| 1 | `id` | int | `11` |
| 2 | `brand` | string | `Casas Parana` |
| 3 | `head_office_legal_name` | string | `Construtora Casas Parana Ltda.` |
| 4 | `address` | string | `Rua da Industria, 348, Curitiba...` |
| 5 | `country` | string | `Brazil` |
| 6 | `country_code` | string | `BRA` |
| 7 | `region` | string | `Parana` |
| 8 | `webpage` | url | `https://www.casasparana.com.br` |
| 9 | `configurator` | url | online home configurator link |
| 10 | `models_amount` | int | `67` |
| 11 | `min_sqm` | float | `45` |
| 12 | `max_sqm` | float | `120` |
| 13 | `main_structure_material` | string | `wood`, `steel`, `concrete` |
| 14 | `min_home_price` | float | `16155.34` |
| 15 | `median_home_price` | float | `31360` |
| 16 | `latitude` | float | `-25.494963` |
| 17 | `longitude` | float | `-49.235489` |
| 18 | `type` | string | `homes` |
| 19 | `viz` | json[] | array of image URLs |
| 20 | `plans` | string | floor plan data |
| 21 | `sqm_ranges` | json[] | `[45,120]` |
| 22 | `median_u_price` | float | `380` (price per sqm) |
| 23 | `desc` | string | description (original language) |
| 24 | `desc_en` | string | description (English) |

---

## Project Architecture

```mermaid
graph TB
    subgraph ROOT["prefab/"]
        direction TB

        subgraph PIPELINE["Data Pipeline (root scripts)"]
            G1[02_geocode_from_webpage_ai.py]
            G2[03_verify_webpage_ai.py]
            G3[04_classify_type_ai.py]
            G4[05_classify_type_ai.py]
            G5[geocode_addresses.py]
            G6[geocode_with_openai.py]
            G7[normalize_materials.py]
            G8[show_materials.py]
            G9[verify_sweden.py]
        end

        subgraph CORE["core/ - Research & Enrichment"]
            direction TB
            C_RES["Research Scripts"]
            C_ENR["Enrichment Scripts"]
            C_UTIL["Utilities"]

            C_RES --- res1[researchBrazilPrefabCompanies.py]
            C_RES --- res2[researchUSAPrefabCompanies.py]
            C_RES --- res3[researchEuropePrefabCompanies.py]
            C_RES --- res4[researchRussiaPrefabCompanies.py]
            C_RES --- res5[research...PrefabCompanies.py<br/>x14 countries]

            C_ENR --- enr1[enrichCompanyData.py]
            C_ENR --- enr2[enrichCompanyDataGemini.py]
            C_ENR --- enr3[deepSearchAndFillRequisites.py]
            C_ENR --- enr4[deepResearchAssociationCompanies.py]
            C_ENR --- enr5[verifyAndEnrichCSVData.py]
            C_ENR --- enr6[verifyCompanyData.py]

            C_UTIL --- u1[mergeAndEnrichCSV.py]
            C_UTIL --- u2[geocodeCoordinates.py]
            C_UTIL --- u3[convertUSAToCSV.py]
            C_UTIL --- u4[createCountryScripts.py]
        end

        subgraph CONFIGIX["configix/ - API Config"]
            CFG1[apiManager.py]
            CFG2[apiManager.js]
            CFG3[check_mapbox.py]
        end

        subgraph RESEARCH["research_output/ - Raw Data"]
            RO1["{country}_prefab_core.csv/.json<br/>x14 countries"]
            RO2["{country}_progress_backup.json"]
            RO3["{country}_prefab_core_enriched.csv"]
            RO4[association_research_progress.json]
        end

        subgraph MAPS["maps/ - Next.js Web App"]
            direction TB

            subgraph PAGES["pages/"]
                P1[index.tsx - main map]
                P2[map-dots.tsx - dot map]
                P3[map-dashboard.tsx]
                P4[api/mapbox-config.ts]
                P5[api/ors-isochrone.ts]
            end

            subgraph COMPONENTS["components/"]
                CO1[Map.tsx]
                CO2[MapDashboard.tsx]
                CO3[PopupStyleInject.tsx]
            end

            subgraph PUBLIC["public/ - Static Data"]
                PUB1["prefabworldfin_reducedby_{1-7}.csv"]
                PUB2[prefab-dashboard-data.json]
                PUB3[isochrones_all.geojson]
                PUB4[old/ - CSV backups]
            end

            subgraph SCRIPTS["scripts/ - Build Tools"]
                S1[research-companies.ts]
                S2[research-viz-images.ts]
                S3[translate-desc.ts]
                S4[build-dashboard-company-data.ts]
                S5[generate-missing-isochrones.ts]
            end
        end
    end

    CORE -->|"generates"| RESEARCH
    RESEARCH -->|"merged into"| PUBLIC
    PIPELINE -->|"transforms"| PUBLIC
    SCRIPTS -->|"enriches"| PUBLIC
    PUBLIC -->|"serves"| PAGES
    CONFIGIX -.->|"API keys"| CORE
    CONFIGIX -.->|"API keys"| MAPS
```

---

## Data Flow

```mermaid
flowchart LR
    A["core/ research scripts<br/>(per-country)"] -->|JSON/CSV| B["research_output/"]
    B -->|merge + enrich| C["Pipeline scripts<br/>(geocode, verify, classify)"]
    C -->|cleaned CSV| D["maps/public/<br/>prefabworldfin_reducedby_*.csv"]
    E["maps/scripts/<br/>(translate, viz, dashboard)"] -->|enrich| D
    D -->|read at runtime| F["Next.js Map App<br/>(Mapbox GL)"]
```
