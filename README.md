![Banner](misc/banner.png)

# Nederlands naar Gebaar (NmG) Conversie Tool

**[View Project Website](https://wmotte.github.io/nederlands_naar_gebaar/)**

Een Python-gebaseerde tool voor het converteren van Nederlandse teksten (met name preken en bijbelteksten) naar een versie die geoptimaliseerd is voor **Nederlands met Gebaren (NmG)**.

## Overzicht

Deze tool gebruikt taalmodellen om automatisch Nederlandse teksten te analyseren en om te zetten naar een gebarentaal-vriendelijke vorm. Het genereert:

- NmG-geoptimaliseerde tekstversies
- Lijsten met te gebruiken glossen (gebaren)
- Specifieke instructies voor gebaren, lokalisatie, classifiers, rolwisseling, etc.
- Gestructureerde JSON- en leesbare Markdown-output

## Functionaliteiten

- **Batch Processing**: Verwerkt lange teksten in kleinere batches voor betere betrouwbaarheid
- **Resume Capability**: Kan onderbroken conversies hervatten zonder opnieuw te beginnen
- **Automatische Retry**: Probeert ontbrekende zinnen automatisch opnieuw te verwerken
- **Glossen Database**: Gebruikt een woordenlijst van beschikbare gebaren
- **Verificatie**: Controleert of alle zinnen correct zijn verwerkt
- **Dual Output**: Genereert zowel gestructureerde JSON als leesbare Markdown

## Vereisten

### Software
- Python 3.7 of hoger
- Google Gemini API key

### Python Libraries
```bash
pip install google-genai python-dotenv
```

## Installatie

1. Clone of download dit project
2. Installeer de benodigde libraries:
   ```bash
   pip install google-genai python-dotenv
   ```
3. Maak een `.env` bestand aan in de hoofdmap met je API key:
   ```
   GEMINI_API_KEY=jouw_api_key_hier
   ```
   Of gebruik:
   ```
   GOOGLE_API_KEY=jouw_api_key_hier
   ```

## Gebruik

### Basis Gebruik

```bash
./00__tekst_naar_nmg.py input/tekst.txt
```

Of:

```bash
python3 00__tekst_naar_nmg.py input/tekst.txt
```

## Projectstructuur

```
nederlands_naar_gebaar/
├── 00__tekst_naar_nmg.py      # Hoofdscript
├── .env                        # API configuratie (niet in git)
├── .gitignore
├── README.md                   # Deze file
│
├── input/                      # Input tekstbestanden
│   ├── tekst_*.txt
│   └── schriftgedeelte_*.txt
│
├── output/                     # Gegenereerde bestanden
│   ├── *_nmg_*.json           # JSON output
│   ├── *_nmg_*.md             # Markdown output
│   └── [naam]/batches/        # Tussentijdse batch resultaten
│
├── prompts/                    # AI prompt templates
│   └── nmg_preek_conversie.md
│
└── misc/                       # Hulpbestanden
    └── lijst_met_glossen_clean.txt  # Database van beschikbare gebaren
```

## Output Formaat

### JSON Output
Het JSON bestand bevat:
- **metadata**: Titel, datum, samenvatting
- **zinnen**: Array van zinnen met:
  - `zin_nummer`: Origineel zinnummer
  - `origineel`: Originele tekst
  - `nmg_versie`: Geoptimaliseerde versie voor NmG
  - `glossen`: Lijst van te gebruiken gebaren
  - `glossen_niet_gevonden`: Woorden zonder beschikbaar gebaar
  - `nmg_instructies`: Specifieke instructies (lokalisatie, classifiers, rolwisseling, etc.)
  - `toelichting`: Uitleg van de conversie
- **ruimtelijke_opbouw**: Locaties en personages in de tekst
- **algemene_adviezen**: Tips voor de vertolking
- **_verificatie**: Compleetheid statistieken

### Markdown Output
Een leesbare versie met alle conversie-informatie per zin.

## Werking

1. **Input Verwerking**: De tekst wordt gesplitst in individuele zinnen
2. **Batch Conversie**: Zinnen worden in batches verwerkt (standaard 25 per batch)
3. **AI Analyse**: Gemini analyseert en converteert elke zin naar NmG-vorm
4. **Tussentijdse Opslag**: Elke batch wordt opgeslagen (mogelijk om te hervatten)
5. **Samenvoegen**: Alle batches worden samengevoegd tot één geheel
6. **Verificatie**: Controleert of alle zinnen zijn verwerkt
7. **Retry**: Ontbrekende zinnen worden automatisch opnieuw geprobeerd
8. **Output**: Genereert JSON en Markdown bestanden

## Configuratie

### Model Instellingen
In `00__tekst_naar_nmg.py`:
- `MODEL_NAME`: Primair model (standaard: "gemini-3-flash-preview")
- `MODEL_NAME_FALLBACK`: Fallback model (standaard: "gemini-3-flash-preview")
- `BATCH_SIZE`: Aantal zinnen per batch (standaard: 25)

### API Instellingen
De tool gebruikt deze parameters voor Gemini:
- Temperature: 0.3 (lagere waarde voor consistentere output)
- Top-P: 0.95
- Top-K: 40
- Max output tokens: 65536

## Tips en Best Practices

1. **Batch Grootte**: Voor zeer lange teksten, overweeg een kleinere batch grootte (15-20)
2. **Resume Functie**: Bij een onderbreking kun je het script gewoon opnieuw draaien; het pikt automatisch op waar het gestopt was
3. **Glossen Database**: Zorg dat `misc/lijst_met_glossen_clean.txt` up-to-date is
4. **Input Formaat**: Elke regel in het input bestand wordt als een aparte zin behandeld
5. **API Kosten**: Let op het gebruik; batch processing helpt kosten te beheersen

## Probleemoplossing

### "Geen API key gevonden"
Zorg dat je `.env` bestand correct is ingesteld met `GEMINI_API_KEY` of `GOOGLE_API_KEY`.

### "Conversie mislukt"
De tool probeert automatisch opnieuw met JSON-mode en eventueel een fallback model.

### "Ontbrekende zinnen"
De tool probeert automatisch 2x opnieuw. Pas `--max-retries` aan voor meer pogingen.

### Bestaande batches hergebruiken
Bij default worden bestaande batches hergebruikt. Gebruik `--fresh` om opnieuw te beginnen.

## Auteur

W.M. Otte (w.m.otte@umcutrecht.nl)

