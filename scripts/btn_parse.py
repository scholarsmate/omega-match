import re
import os
import logging
from bs4 import BeautifulSoup
from collections import defaultdict
from unidecode import unidecode

def strip_number_suffix(name: str) -> str:
    return re.sub(r"\s+\d+$", "", name)

def parse_btn_names_with_variants(cache_dir="btn_cache"):
    results = defaultdict(set)

    for filename in sorted(os.listdir(cache_dir)):
        if not filename.endswith(".html"):
            continue

        filepath = os.path.join(cache_dir, filename)
        logging.info(f"Parsing {filepath}")
        with open(filepath, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        for entry in soup.select("div.browsename"):
            canonical_tag = entry.find("a", href=True)
            if not canonical_tag:
                continue

            canonical_raw = canonical_tag.text.strip()
            canonical = strip_number_suffix(canonical_raw)
            if not canonical:
                continue

            results[canonical]  # initialize set

            sibling = entry.find_next_sibling()
            if sibling and sibling.name == "span" and "listname" in sibling.get("class", []):
                for alt_tag in sibling.find_all("a", href=True):
                    alt_raw = alt_tag.text.strip()
                    alt = strip_number_suffix(alt_raw)
                    if alt and alt != canonical:
                        results[canonical].add(alt)

    return results

def save_name_variant_map(name_map, output_file="name_variants.tsv"):
    with open(output_file, "w", encoding="utf-8") as f:
        for name in sorted(name_map):
            variants = sorted(name_map[name])
            f.write(f"{name}\t" + "\t".join(variants) + "\n")

    with open("names_utf8.txt", "w", encoding="utf-8") as f_utf8, open("names_ascii.txt", "w", encoding="utf-8") as f_ascii:
        for name in sorted(name_map):
            f_utf8.write(name + "\n")
            f_ascii.write(unidecode(name) + "\n")

# set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("btn_parse.log"),
        logging.StreamHandler()
    ]
)
# Run both:
name_variants = parse_btn_names_with_variants()
save_name_variant_map(name_variants)

