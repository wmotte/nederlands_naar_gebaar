#!/usr/bin/env python3
"""
Preek naar Nederlands met Gebaren (NmG) Conversie

Dit script converteert een geschreven preektekst naar een versie die geoptimaliseerd is
voor Nederlands met Gebaren (NmG). Het gebruikt Gemini 3 Flash om de conversie uit te voeren.

De output is een JSON bestand met per zin:
- De originele tekst
- De NmG-geoptimaliseerde versie
- Lijst van te gebruiken glossen
- Specifieke instructies voor gebaren, lokalisatie, classifiers, etc.

W.M. Otte (w.m.otte@umcutrecht.nl)
"""

# Model configuratie
MODEL_NAME = "gemini-3-pro-preview"
MODEL_NAME_FALLBACK = "gemini-2.5-flash"

# Batch configuratie
BATCH_SIZE = 25  # Aantal zinnen per batch

import os
import sys
import re
import json
import argparse
from typing import Optional
from pathlib import Path
from datetime import datetime

# Laad .env bestand als het bestaat
try:
    from dotenv import load_dotenv
    # Zoek .env in script directory
    _script_dir = Path(__file__).parent.resolve()
    _env_file = _script_dir / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        print(f"✓ .env bestand geladen: {_env_file}")
    else:
        # Probeer ook huidige directory
        load_dotenv()
except ImportError:
    print("WAARSCHUWING: 'python-dotenv' niet geïnstalleerd. .env wordt niet geladen.")
    print("Installeer met: pip install python-dotenv")

# Importeer de nieuwe SDK
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("FOUT: De 'google-genai' library is niet geïnstalleerd.")
    print("Installeer deze met: pip install google-genai")
    sys.exit(1)

# Configuratie
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "output"
PROMPTS_DIR = SCRIPT_DIR / "prompts"
MISC_DIR = SCRIPT_DIR / "misc"
INPUT_DIR = SCRIPT_DIR / "input"


def get_gemini_client() -> genai.Client:
    """Initialiseer de Gemini Client."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        print("\nFOUT: Geen API key gevonden.")
        print("Stel de GEMINI_API_KEY of GOOGLE_API_KEY environment variable in.")
        sys.exit(1)

    return genai.Client(api_key=api_key)


def load_prompt(filename: str) -> str:
    """Laad een prompt uit een markdown bestand."""
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Prompt bestand niet gevonden: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def load_preek(filepath: str) -> str:
    """Laad de preektekst uit een bestand."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Preek bestand niet gevonden: {filepath}")

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_glossen_lijst() -> str:
    """Laad de lijst met beschikbare glossen.

    Probeert eerst de schone/ontdubbelde versie te laden,
    valt terug op het originele bestand indien nodig.
    """
    # Probeer eerst de schone versie
    clean_filepath = MISC_DIR / "lijst_met_glossen_clean.txt"
    original_filepath = MISC_DIR / "lijst_met_glossen.txt"

    if clean_filepath.exists():
        filepath = clean_filepath
        print(f"  Gebruik ontdubbelde glossen lijst")
    elif original_filepath.exists():
        filepath = original_filepath
        print(f"  Gebruik originele glossen lijst (niet ontdubbeld)")
    else:
        print(f"WAARSCHUWING: Glossen lijst niet gevonden")
        return "Geen glossen lijst beschikbaar."

    glossen = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Voor clean bestand: regel is al de glos
            # Voor origineel bestand: verwijder .mp4 extensie
            if line.endswith(".mp4"):
                line = line[:-4]

            # Verwijder trailing dots en underscores
            glos = line.rstrip(".").rstrip("_")

            # Skip lege of te korte entries
            if len(glos) < 2:
                continue

            # Alleen toevoegen als het nog niet in de lijst staat
            if glos not in glossen:
                glossen.append(glos)

    # Sorteer alfabetisch
    glossen.sort()

    # Formatteer als leesbare lijst
    return "\n".join(glossen)


def split_preek_into_sentences(preek_tekst: str) -> list[dict]:
    """Splits de preektekst in individuele zinnen met nummering.

    Returns:
        list van dicts met 'nummer' en 'tekst' keys
    """
    lines = preek_tekst.strip().split('\n')
    sentences = []
    nummer = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        nummer += 1
        sentences.append({
            'nummer': nummer,
            'tekst': line
        })

    return sentences


def create_batch_prompt(prompt_template: str, glossen_lijst: str, sentences: list[dict], batch_start: int) -> str:
    """Maak een prompt voor een specifieke batch van zinnen.

    Args:
        prompt_template: De volledige prompt template
        glossen_lijst: De lijst met beschikbare glossen
        sentences: Lijst van zinnen in deze batch
        batch_start: Het startnummer van deze batch (voor zin_nummer)

    Returns:
        De aangepaste prompt voor deze batch
    """
    # Formatteer de zinnen met nummering
    preek_deel = "\n".join([f"[Zin {s['nummer']}] {s['tekst']}" for s in sentences])

    # Voeg batch-specifieke instructies toe
    batch_instructie = f"""
---

## BATCH VERWERKING

Dit is een batch van zinnen {sentences[0]['nummer']} t/m {sentences[-1]['nummer']}.
- Verwerk ALLE zinnen in deze batch
- Behoud de originele zin_nummers zoals aangegeven met [Zin X]
- Zinnen mogen samengevoegd worden als dat logischer is, maar geef dan alle originele zinnummers aan
- ALLE informatie uit elke zin moet behouden blijven

"""

    # Bouw de prompt op
    full_prompt = prompt_template.replace("{{GLOSSEN_LIJST}}", glossen_lijst)
    full_prompt = full_prompt.replace("{{PREEK_TEKST}}", batch_instructie + preek_deel)

    return full_prompt


def merge_batch_results(all_batch_results: list[dict]) -> dict:
    """Voeg de resultaten van alle batches samen tot één geheel.

    Args:
        all_batch_results: Lijst van JSON resultaten per batch

    Returns:
        Samengevoegd resultaat
    """
    if not all_batch_results:
        return {"error": "Geen batch resultaten om samen te voegen"}

    # Gebruik de metadata van de eerste batch als basis
    merged = {
        "metadata": all_batch_results[0].get("metadata", {}),
        "zinnen": [],
        "ruimtelijke_opbouw": all_batch_results[0].get("ruimtelijke_opbouw", {}),
        "algemene_adviezen": []
    }

    # Verzamel unieke adviezen
    adviezen_set = set()

    # Combineer zinnen en adviezen uit alle batches
    for batch_result in all_batch_results:
        if "zinnen" in batch_result:
            merged["zinnen"].extend(batch_result["zinnen"])

        if "algemene_adviezen" in batch_result:
            for advies in batch_result["algemene_adviezen"]:
                if advies not in adviezen_set:
                    adviezen_set.add(advies)
                    merged["algemene_adviezen"].append(advies)

        # Merge ruimtelijke_opbouw (locaties en personages)
        if "ruimtelijke_opbouw" in batch_result:
            ro = batch_result["ruimtelijke_opbouw"]
            if "locaties" in ro and isinstance(ro["locaties"], list):
                existing_names = {l.get("naam") for l in merged["ruimtelijke_opbouw"].get("locaties", []) if isinstance(l, dict) and l.get("naam")}
                for loc in ro["locaties"]:
                    if isinstance(loc, dict) and loc.get("naam") and loc.get("naam") not in existing_names:
                        merged["ruimtelijke_opbouw"].setdefault("locaties", []).append(loc)
                        existing_names.add(loc.get("naam"))
            if "personages" in ro and isinstance(ro["personages"], list):
                existing_names = {p.get("naam") for p in merged["ruimtelijke_opbouw"].get("personages", []) if isinstance(p, dict) and p.get("naam")}
                for pers in ro["personages"]:
                    if isinstance(pers, dict) and pers.get("naam") and pers.get("naam") not in existing_names:
                        merged["ruimtelijke_opbouw"].setdefault("personages", []).append(pers)
                        existing_names.add(pers.get("naam"))

    # Sorteer zinnen op zin_nummer
    merged["zinnen"].sort(key=lambda x: x.get("zin_nummer", 0))

    # Update totaal zinnen in metadata
    merged["metadata"]["totaal_zinnen"] = len(merged["zinnen"])

    return merged


def verify_completeness(original_sentences: list[dict], result: dict) -> dict:
    """Controleer of alle zinnen zijn verwerkt en geef een rapport.

    Args:
        original_sentences: De oorspronkelijke lijst van zinnen
        result: Het samengevoegde resultaat

    Returns:
        dict met verificatie informatie
    """
    original_count = len(original_sentences)
    processed_zinnen = result.get("zinnen", [])

    # Verzamel alle verwerkte zinnummers
    processed_numbers = set()
    for zin in processed_zinnen:
        zin_nummer = zin.get("zin_nummer")
        if isinstance(zin_nummer, int):
            processed_numbers.add(zin_nummer)
        elif isinstance(zin_nummer, list):
            # Als meerdere zinnen zijn samengevoegd
            processed_numbers.update(zin_nummer)
        elif isinstance(zin_nummer, str) and "-" in zin_nummer:
            # Format "1-3" voor samengevoegde zinnen
            try:
                start, end = map(int, zin_nummer.split("-"))
                processed_numbers.update(range(start, end + 1))
            except ValueError:
                pass

    # Vind ontbrekende zinnen
    expected_numbers = set(s['nummer'] for s in original_sentences)
    missing_numbers = expected_numbers - processed_numbers

    verification = {
        "origineel_aantal_zinnen": original_count,
        "verwerkte_zinnen": len(processed_zinnen),
        "unieke_zinnummers_verwerkt": len(processed_numbers),
        "ontbrekende_zinnummers": sorted(list(missing_numbers)),
        "compleet": len(missing_numbers) == 0,
        "percentage_verwerkt": round((len(processed_numbers) / original_count) * 100, 1) if original_count > 0 else 0
    }

    return verification


def extract_json(text: str) -> dict:
    """Extraheer JSON uit de response, ook als deze in markdown is gewrapt."""
    if not text or not text.strip():
        return {"error": "Lege response ontvangen", "raw_response": ""}

    # Poging 1: Direct parsen
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Poging 2: JSON binnen markdown code block
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Poging 3: Zoek naar eerste { tot laatste }
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Poging 3b: Fix trailing comma's
            try:
                json_str_fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)
                return json.loads(json_str_fixed)
            except json.JSONDecodeError:
                pass

    return {"error": "Kon geen valide JSON extraheren", "raw_response": text[:2000]}


def run_conversion(client: genai.Client, prompt: str, model: str = None) -> dict:
    """Voer de NmG conversie uit met het taalmodel.

    Args:
        client: De Gemini client
        prompt: De volledige prompt
        model: Model om te gebruiken (default: MODEL_NAME)

    Returns:
        dict met de conversie resultaten
    """
    current_model = model or MODEL_NAME

    print(f"\n{'─' * 50}")
    print(f"Conversie uitvoeren met {current_model}")
    print(f"{'─' * 50}")

    max_retries = 3
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"Poging {attempt + 1}/{max_retries + 1}...")
        else:
            print("Bezig met analyseren en converteren...")

        try:
            config_params = {
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 65536,
                "safety_settings": [
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                ]
            }

            # Forceer JSON output na eerste mislukte poging
            if attempt > 0:
                config_params["response_mime_type"] = "application/json"
                print(f"  → JSON-mode geactiveerd voor betere betrouwbaarheid")

            response = client.models.generate_content(
                model=current_model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_params)
            )

            if response.text:
                result = extract_json(response.text)
                if "error" in result:
                    print(f"\033[91m⚠ Conversie voltooid maar JSON parsing mislukt (poging {attempt + 1})\033[0m")
                    if attempt < max_retries:
                        print(f"  → Retry met strengere JSON-validatie...")
                        continue
                else:
                    print(f"\033[92m✓ Conversie voltooid (valide JSON)\033[0m")
                    return result
            else:
                print(f"✗ Geen tekst ontvangen (poging {attempt + 1})")
                if attempt < max_retries:
                    continue

        except Exception as e:
            error_msg = f"Fout bij conversie: {str(e)}"
            print(f"✗ {error_msg}")
            if attempt < max_retries:
                continue

    # Fallback naar ander model als alle pogingen mislukken
    if current_model == MODEL_NAME and MODEL_NAME_FALLBACK:
        print(f"\n⚠ Alle pogingen met {MODEL_NAME} mislukt. Fallback naar {MODEL_NAME_FALLBACK}...")
        return run_conversion(client, prompt, model=MODEL_NAME_FALLBACK)

    return {"error": f"Conversie mislukt na alle pogingen", "model": current_model}


def save_batch_result(batch_dir: Path, batch_num: int, result: dict):
    """Sla een individueel batch resultaat op.

    Args:
        batch_dir: Directory voor batch bestanden
        batch_num: Batch nummer
        result: Het batch resultaat
    """
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_file = batch_dir / f"batch_{batch_num:03d}.json"

    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  → Batch opgeslagen: {batch_file.name}")


def load_existing_batches(batch_dir: Path) -> list[dict]:
    """Laad bestaande batch resultaten uit een directory.

    Args:
        batch_dir: Directory met batch bestanden

    Returns:
        Lijst van batch resultaten, gesorteerd op batch nummer
    """
    if not batch_dir.exists():
        return []

    batch_files = sorted(batch_dir.glob("batch_*.json"))
    results = []

    for batch_file in batch_files:
        try:
            with open(batch_file, "r", encoding="utf-8") as f:
                result = json.load(f)
                if "zinnen" in result:
                    results.append(result)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠ Kon {batch_file.name} niet laden: {e}")

    return results


def get_processed_sentence_numbers(batch_dir: Path) -> set[int]:
    """Bepaal welke zinnummers al verwerkt zijn in bestaande batches.

    Args:
        batch_dir: Directory met batch bestanden

    Returns:
        Set van al verwerkte zinnummers
    """
    existing_batches = load_existing_batches(batch_dir)
    processed = set()

    for batch in existing_batches:
        for zin in batch.get("zinnen", []):
            zin_nummer = zin.get("zin_nummer")
            if isinstance(zin_nummer, int):
                processed.add(zin_nummer)
            elif isinstance(zin_nummer, list):
                processed.update(zin_nummer)
            elif isinstance(zin_nummer, str) and "-" in zin_nummer:
                try:
                    start, end = map(int, zin_nummer.split("-"))
                    processed.update(range(start, end + 1))
                except ValueError:
                    pass

    return processed


def run_batch_conversion(
    client: genai.Client,
    prompt_template: str,
    glossen_lijst: str,
    sentences: list[dict],
    batch_size: int = BATCH_SIZE,
    model: str = None,
    output_dir: Path = None,
    resume: bool = True
) -> tuple[dict, dict]:
    """Verwerk de preek in batches en voeg de resultaten samen.

    Args:
        client: De Gemini client
        prompt_template: De prompt template
        glossen_lijst: De lijst met beschikbare glossen
        sentences: Alle zinnen uit de preek
        batch_size: Aantal zinnen per batch
        model: Model om te gebruiken
        output_dir: Directory voor tussentijdse opslag
        resume: Hervat vanaf bestaande batches indien beschikbaar

    Returns:
        tuple van (samengevoegd resultaat, verificatie rapport)
    """
    total_sentences = len(sentences)
    num_batches = (total_sentences + batch_size - 1) // batch_size

    # Setup batch directory voor tussentijdse opslag
    batch_dir = None
    if output_dir:
        batch_dir = output_dir / "batches"
        batch_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"BATCH VERWERKING")
    print(f"{'=' * 60}")
    print(f"Totaal zinnen: {total_sentences}")
    print(f"Batch grootte: {batch_size}")
    print(f"Aantal batches: {num_batches}")
    if batch_dir:
        print(f"Tussentijdse opslag: {batch_dir}")

    all_batch_results = []
    failed_batches = []

    # Check voor bestaande batches om te hervatten
    already_processed = set()
    if batch_dir and resume:
        existing_batches = load_existing_batches(batch_dir)
        if existing_batches:
            already_processed = get_processed_sentence_numbers(batch_dir)
            print(f"\n\033[94m→ Gevonden: {len(existing_batches)} bestaande batches ({len(already_processed)} zinnen)\033[0m")
            all_batch_results.extend(existing_batches)

    for batch_num in range(num_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_sentences)
        batch_sentences = sentences[start_idx:end_idx]

        # Check of deze batch al verwerkt is
        batch_sentence_nums = {s['nummer'] for s in batch_sentences}
        if batch_sentence_nums.issubset(already_processed):
            print(f"\n\033[94m→ Batch {batch_num + 1}/{num_batches} (zinnen {batch_sentences[0]['nummer']} - {batch_sentences[-1]['nummer']}) - al verwerkt, overslaan\033[0m")
            continue

        print(f"\n{'─' * 50}")
        print(f"Batch {batch_num + 1}/{num_batches} (zinnen {batch_sentences[0]['nummer']} - {batch_sentences[-1]['nummer']})")
        print(f"{'─' * 50}")

        # Maak de batch-specifieke prompt
        batch_prompt = create_batch_prompt(
            prompt_template, glossen_lijst, batch_sentences, start_idx + 1
        )

        # Voer de conversie uit voor deze batch
        result = run_conversion(client, batch_prompt, model=model)

        if "error" in result and "zinnen" not in result:
            print(f"\033[91m✗ Batch {batch_num + 1} mislukt\033[0m")
            failed_batches.append({
                "batch": batch_num + 1,
                "zinnen": f"{batch_sentences[0]['nummer']}-{batch_sentences[-1]['nummer']}",
                "error": result.get("error", "Onbekende fout")
            })
        else:
            zinnen_count = len(result.get("zinnen", []))
            print(f"\033[92m✓ Batch {batch_num + 1} voltooid ({zinnen_count} zinnen verwerkt)\033[0m")
            all_batch_results.append(result)

            # Sla batch direct op
            if batch_dir:
                save_batch_result(batch_dir, batch_num + 1, result)

    # Voeg alle resultaten samen
    print(f"\n{'─' * 50}")
    print("Resultaten samenvoegen...")

    if not all_batch_results:
        return {"error": "Alle batches zijn mislukt", "failed_batches": failed_batches}, {
            "origineel_aantal_zinnen": total_sentences,
            "verwerkte_zinnen": 0,
            "compleet": False,
            "failed_batches": failed_batches
        }

    merged_result = merge_batch_results(all_batch_results)

    # Voeg informatie over mislukte batches toe indien van toepassing
    if failed_batches:
        merged_result["_failed_batches"] = failed_batches

    # Verificatie
    verification = verify_completeness(sentences, merged_result)
    verification["failed_batches"] = failed_batches

    print(f"\033[92m✓ Resultaten samengevoegd\033[0m")

    return merged_result, verification


def retry_missing_sentences(
    client: genai.Client,
    prompt_template: str,
    glossen_lijst: str,
    sentences: list[dict],
    missing_numbers: list[int],
    current_result: dict,
    model: str = None
) -> tuple[dict, dict]:
    """Probeer ontbrekende zinnen opnieuw te verwerken.

    Args:
        client: De Gemini client
        prompt_template: De prompt template
        glossen_lijst: De lijst met beschikbare glossen
        sentences: Alle originele zinnen
        missing_numbers: Lijst van ontbrekende zinnummers
        current_result: Het huidige resultaat
        model: Model om te gebruiken

    Returns:
        tuple van (bijgewerkt resultaat, nieuwe verificatie)
    """
    if not missing_numbers:
        return current_result, verify_completeness(sentences, current_result)

    print(f"\n{'=' * 60}")
    print(f"RETRY ONTBREKENDE ZINNEN")
    print(f"{'=' * 60}")
    print(f"Ontbrekende zinnen: {missing_numbers}")

    # Verzamel de ontbrekende zinnen
    missing_sentences = [s for s in sentences if s['nummer'] in missing_numbers]

    # Verwerk in kleinere batches
    retry_batch_size = min(15, len(missing_sentences))  # Kleinere batches voor retry
    num_batches = (len(missing_sentences) + retry_batch_size - 1) // retry_batch_size

    retry_results = []

    for batch_num in range(num_batches):
        start_idx = batch_num * retry_batch_size
        end_idx = min(start_idx + retry_batch_size, len(missing_sentences))
        batch_sentences = missing_sentences[start_idx:end_idx]

        print(f"\nRetry batch {batch_num + 1}/{num_batches}...")

        batch_prompt = create_batch_prompt(
            prompt_template, glossen_lijst, batch_sentences, 0
        )

        result = run_conversion(client, batch_prompt, model=model)

        if "zinnen" in result:
            retry_results.append(result)
            print(f"\033[92m✓ Retry batch {batch_num + 1} voltooid\033[0m")
        else:
            print(f"\033[91m✗ Retry batch {batch_num + 1} mislukt\033[0m")

    # Voeg retry resultaten toe aan current_result
    for retry_result in retry_results:
        if "zinnen" in retry_result:
            current_result["zinnen"].extend(retry_result["zinnen"])

    # Sorteer en update
    current_result["zinnen"].sort(key=lambda x: x.get("zin_nummer", 0) if isinstance(x.get("zin_nummer"), int) else 0)
    current_result["metadata"]["totaal_zinnen"] = len(current_result["zinnen"])

    # Nieuwe verificatie
    new_verification = verify_completeness(sentences, current_result)

    return current_result, new_verification


def save_output(output_path: Path, result: dict, preek_naam: str):
    """Sla het resultaat op als JSON bestand."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Voeg metadata toe
    result["_metadata"] = {
        "bron_preek": preek_naam,
        "conversie_datum": datetime.now().isoformat(),
        "model": MODEL_NAME
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\033[92m✓ Resultaat opgeslagen: {output_path}\033[0m")


def create_readable_output(result: dict, output_path: Path):
    """Maak een leesbare markdown versie van het resultaat."""
    md_path = output_path.with_suffix(".md")

    lines = []
    lines.append("# Preek Conversie naar Nederlands met Gebaren (NmG)\n")

    if "metadata" in result:
        meta = result["metadata"]
        lines.append(f"**Titel:** {meta.get('titel', 'Onbekend')}")
        lines.append(f"**Datum conversie:** {meta.get('datum_conversie', 'Onbekend')}")
        lines.append(f"**Totaal zinnen:** {meta.get('totaal_zinnen', 'Onbekend')}")
        if meta.get('samenvatting'):
            lines.append(f"\n**Samenvatting:** {meta['samenvatting']}\n")

    lines.append("\n---\n")

    if "zinnen" in result:
        for zin in result["zinnen"]:
            nr = zin.get("zin_nummer", "?")
            lines.append(f"## Zin {nr}\n")

            lines.append(f"**Origineel:**")
            lines.append(f"> {zin.get('origineel', '')}\n")

            lines.append(f"**NmG versie:**")
            lines.append(f"> {zin.get('nmg_versie', '')}\n")

            if zin.get("glossen"):
                lines.append(f"**Glossen:** {', '.join(zin['glossen'])}\n")

            if zin.get("glossen_niet_gevonden"):
                lines.append(f"**Glossen niet gevonden:** {', '.join(zin['glossen_niet_gevonden'])}\n")

            if zin.get("nmg_instructies"):
                instr = zin["nmg_instructies"]
                lines.append("**NmG Instructies:**")
                if instr.get("lokalisatie"):
                    lines.append(f"- *Lokalisatie:* {instr['lokalisatie']}")
                if instr.get("classifiers"):
                    lines.append(f"- *Classifiers:* {instr['classifiers']}")
                if instr.get("rolwisseling"):
                    lines.append(f"- *Rolwisseling:* {instr['rolwisseling']}")
                if instr.get("tempo_pauzes"):
                    lines.append(f"- *Tempo/Pauzes:* {instr['tempo_pauzes']}")
                if instr.get("non_manueel"):
                    lines.append(f"- *Non-manueel:* {instr['non_manueel']}")
                lines.append("")

            if zin.get("toelichting"):
                lines.append(f"**Toelichting:** {zin['toelichting']}\n")

            lines.append("---\n")

    if "algemene_adviezen" in result:
        lines.append("## Algemene Adviezen\n")
        for advies in result["algemene_adviezen"]:
            lines.append(f"- {advies}")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\033[92m✓ Leesbare versie opgeslagen: {md_path}\033[0m")


def main():
    """Hoofdfunctie voor de NmG conversie."""
    parser = argparse.ArgumentParser(
        description="Converteer een preektekst naar Nederlands met Gebaren (NmG)"
    )
    parser.add_argument(
        "preek_bestand",
        nargs="?",
        default="input/preek.txt",
        help="Pad naar het preek bestand (default: input/preek.txt)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Pad voor output bestand (default: output/<preek_naam>_nmg.json)"
    )
    parser.add_argument(
        "--model",
        default=MODEL_NAME,
        help=f"Model om te gebruiken (default: {MODEL_NAME})"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Aantal zinnen per batch (default: {BATCH_SIZE})"
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Geen retry van ontbrekende zinnen"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximaal aantal retry pogingen voor ontbrekende zinnen (default: 2)"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start vers, negeer bestaande batch resultaten"
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("PREEK NAAR NEDERLANDS MET GEBAREN (NmG) CONVERSIE")
    print("=" * 60 + "\n")

    # Laad de preektekst
    preek_path = Path(args.preek_bestand)
    if not preek_path.is_absolute():
        preek_path = SCRIPT_DIR / preek_path

    print(f"Preek bestand: {preek_path}")
    try:
        preek_tekst = load_preek(preek_path)
        print(f"\033[92m✓ Preek geladen ({len(preek_tekst)} karakters)\033[0m")
    except FileNotFoundError as e:
        print(f"\033[91m✗ {e}\033[0m")
        sys.exit(1)

    # Laad de prompt template
    print("\nPrompt template laden...")
    try:
        prompt_template = load_prompt("nmg_preek_conversie.md")
        print(f"\033[92m✓ Prompt template geladen\033[0m")
    except FileNotFoundError as e:
        print(f"\033[91m✗ {e}\033[0m")
        sys.exit(1)

    # Laad de glossen lijst
    print("\nGlossen lijst laden...")
    glossen_lijst = load_glossen_lijst()
    glossen_count = len(glossen_lijst.split("\n"))
    print(f"\033[92m✓ {glossen_count} unieke glossen geladen\033[0m")

    # Split preek in zinnen
    print("\nPreek analyseren...")
    sentences = split_preek_into_sentences(preek_tekst)
    print(f"\033[92m✓ {len(sentences)} zinnen geïdentificeerd\033[0m")

    # Initialiseer client
    print("\nGoogle GenAI Client initialiseren...")
    client = get_gemini_client()
    print(f"\033[92m✓ Client geïnitialiseerd\033[0m")

    # Bepaal output directory voor tussentijdse opslag
    preek_naam = preek_path.stem
    batch_output_dir = OUTPUT_DIR / preek_naam

    # Voer batch conversie uit
    result, verification = run_batch_conversion(
        client=client,
        prompt_template=prompt_template,
        glossen_lijst=glossen_lijst,
        sentences=sentences,
        batch_size=args.batch_size,
        model=args.model,
        output_dir=batch_output_dir,
        resume=not args.fresh
    )

    # Toon verificatie
    print(f"\n{'=' * 60}")
    print("VERIFICATIE")
    print(f"{'=' * 60}")
    print(f"Origineel aantal zinnen: {verification['origineel_aantal_zinnen']}")
    print(f"Verwerkte zinnen: {verification['verwerkte_zinnen']}")
    print(f"Unieke zinnummers verwerkt: {verification.get('unieke_zinnummers_verwerkt', 'N/A')}")
    print(f"Percentage verwerkt: {verification.get('percentage_verwerkt', 0)}%")

    # Retry ontbrekende zinnen indien nodig
    if not verification['compleet'] and not args.no_retry:
        missing = verification.get('ontbrekende_zinnummers', [])
        print(f"\n\033[93m⚠ {len(missing)} zinnen ontbreken: {missing[:20]}{'...' if len(missing) > 20 else ''}\033[0m")

        retry_count = 0
        while missing and retry_count < args.max_retries:
            retry_count += 1
            print(f"\nRetry poging {retry_count}/{args.max_retries}...")

            result, verification = retry_missing_sentences(
                client=client,
                prompt_template=prompt_template,
                glossen_lijst=glossen_lijst,
                sentences=sentences,
                missing_numbers=missing,
                current_result=result,
                model=args.model
            )

            missing = verification.get('ontbrekende_zinnummers', [])

            if not missing:
                print(f"\033[92m✓ Alle zinnen nu verwerkt!\033[0m")
                break

    # Finale verificatie status
    if verification['compleet']:
        print(f"\n\033[92m✓ COMPLEET: Alle {verification['origineel_aantal_zinnen']} zinnen zijn verwerkt\033[0m")
    else:
        missing = verification.get('ontbrekende_zinnummers', [])
        print(f"\n\033[91m⚠ INCOMPLEET: {len(missing)} zinnen ontbreken nog\033[0m")
        print(f"  Ontbrekende zinnen: {missing[:30]}{'...' if len(missing) > 30 else ''}")

    # Voeg verificatie toe aan resultaat
    result["_verificatie"] = verification

    # Bepaal output pad
    if args.output:
        output_path = Path(args.output)
    else:
        preek_naam = preek_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"{preek_naam}_nmg_{timestamp}.json"

    # Sla resultaat op
    save_output(output_path, result, preek_path.name)

    # Maak leesbare versie
    create_readable_output(result, output_path)

    # Toon samenvatting
    print("\n" + "=" * 60)
    print("CONVERSIE VOLTOOID")
    print("=" * 60)

    if "metadata" in result:
        meta = result["metadata"]
        print(f"\nTitel: {meta.get('titel', 'Onbekend')}")
        print(f"Totaal zinnen: {meta.get('totaal_zinnen', 'Onbekend')}")

    if "zinnen" in result:
        zinnen = result["zinnen"]
        print(f"Geconverteerde zinnen: {len(zinnen)}")

        # Tel glossen statistieken
        alle_glossen = set()
        niet_gevonden = set()
        for zin in zinnen:
            glossen = zin.get("glossen") or []
            alle_glossen.update(glossen)
            niet_gev = zin.get("glossen_niet_gevonden") or []
            niet_gevonden.update(niet_gev)

        print(f"Unieke glossen gebruikt: {len(alle_glossen)}")
        if niet_gevonden:
            print(f"Woorden zonder gebaar: {len(niet_gevonden)}")

    # Verificatie samenvatting
    if "_verificatie" in result:
        v = result["_verificatie"]
        print(f"\nVerificatie:")
        print(f"  Origineel: {v.get('origineel_aantal_zinnen', 'N/A')} zinnen")
        print(f"  Verwerkt: {v.get('percentage_verwerkt', 0)}%")
        if v.get('compleet'):
            print(f"  \033[92mStatus: COMPLEET\033[0m")
        else:
            missing = v.get('ontbrekende_zinnummers', [])
            print(f"  \033[93mStatus: {len(missing)} zinnen ontbreken\033[0m")

    print(f"\nOutput: {output_path}")
    print(f"Leesbaar: {output_path.with_suffix('.md')}")


if __name__ == "__main__":
    main()
