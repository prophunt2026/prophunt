"""
convert_to_csv.py - Convertit le fichier JSON existant en CSV (compatibilité Excel).
"""

import csv
import json
import os

INPUT_JSON = "properties_schema.json"
OUTPUT_CSV = "properties_schema.csv"


def flatten_record(d, parent_key="", sep="_"):
    """Aplatit la structure JSON imbriquée."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_record(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                items.append((new_key, json.dumps(v, ensure_ascii=False)))
            else:
                items.append((new_key, ", ".join(map(str, v))))
        else:
            items.append((new_key, v))
    return dict(items)


def convert_json_to_csv(json_path=INPUT_JSON, csv_path=OUTPUT_CSV):
    if not os.path.exists(json_path):
        print(f"Erreur : Le fichier '{json_path}' introuvable.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        print("⚠️ Le fichier JSON est vide.")
        return

    flat_records = [flatten_record(r) for r in records]

    # Extraction dynamique de toutes les colonnes
    fieldnames = []
    for r in flat_records:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)

    # Écriture atomique avec encodage UTF-8-SIG pour Excel
    temp_csv = f"{csv_path}.tmp"
    with open(temp_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(flat_records)

    os.replace(temp_csv, csv_path)
    print(f"Conversion réussie ! '{csv_path}' mis à jour ({len(records)} annonces).")


if __name__ == "__main__":
    convert_json_to_csv()