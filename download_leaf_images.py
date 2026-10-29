#!/usr/bin/env python3
"""Download up to three reusable leaf or needle images per tree species."""

import csv
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
OUTPUT = ROOT / "img"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
INATURALIST_API = "https://api.inaturalist.org/v1"
HEADERS = {"User-Agent": "drevesa-leaf-image-downloader/1.0"}


def get_json(url: str, params: dict[str, str | int]) -> dict:
    request = Request(f"{url}?{urlencode(params)}", headers=HEADERS)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code != 429 or attempt == 2:
                raise
            time.sleep(30)
    raise RuntimeError("Unreachable")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip()


def reusable(license_name: str) -> bool:
    license_name = license_name.lower()
    return license_name == "cc0" or license_name.startswith("pd") or (
        license_name.startswith(("cc-by", "cc-by-sa")) and "-nc" not in license_name and "-nd" not in license_name
    )


def commons_candidates(species: str) -> list[dict[str, str]]:
    search_species = species.removesuffix(" sp.").replace(" x ", " ")
    words = "needle" if species.split()[0] in {"Abies", "Picea", "Pinus", "Cedrus", "Larix", "Taxus"} else "leaf"
    data = get_json(
        COMMONS_API,
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f'"{search_species}" {words}',
            "gsrnamespace": 6,
            "gsrlimit": 30,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1200,
            "format": "json",
        },
    )
    candidates = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = page.get("imageinfo", [{}])[0]
        metadata = info.get("extmetadata", {})
        license_name = metadata.get("License", {}).get("value", "")
        text = " ".join(
            [page.get("title", ""), metadata.get("ImageDescription", {}).get("value", ""), metadata.get("Categories", {}).get("value", "")]
        ).lower()
        if not reusable(license_name) or not all(word in text for word in search_species.lower().split()) or not any(word in text for word in ("leaf", "leaves", "needle", "foliage")):
            continue
        thumbnail = info.get("thumburl")
        if thumbnail:
            candidates.append(
                {
                    "url": thumbnail,
                    "source": "Wikimedia Commons",
                    "page": info.get("descriptionurl", ""),
                    "license": clean(metadata.get("LicenseShortName", {}).get("value", license_name)),
                    "license_url": metadata.get("LicenseUrl", {}).get("value", ""),
                    "artist": clean(metadata.get("Artist", {}).get("value", "")),
                }
            )
    return candidates


def inaturalist_candidates(species: str) -> list[dict[str, str]]:
    taxa = get_json(f"{INATURALIST_API}/taxa", {"q": species, "rank": "species", "per_page": 5})
    normalized_species = species.replace("×", "x").casefold()
    taxon = next(
        (item for item in taxa.get("results", []) if item.get("name", "").replace("×", "x").casefold() == normalized_species),
        None,
    )
    if not taxon:
        return []
    observations = get_json(
        f"{INATURALIST_API}/observations",
        {"taxon_id": taxon["id"], "photos": "true", "quality_grade": "research", "per_page": 30},
    )
    candidates = []
    for observation in observations.get("results", []):
        for photo in observation.get("photos", []):
            license_name = photo.get("license_code") or ""
            if reusable(license_name):
                candidates.append(
                    {
                        "url": photo["url"].replace("square", "large"),
                        "source": "iNaturalist",
                        "page": observation.get("uri", ""),
                        "license": license_name,
                        "license_url": "https://www.inaturalist.org/pages/help#photo-licensing",
                        "artist": photo.get("attribution", ""),
                    }
                )
    return candidates


def download(url: str, destination: Path) -> None:
    request = Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response, destination.open("wb") as file:
                file.write(response.read())
            return
        except HTTPError as error:
            if error.code != 429 or attempt == 2:
                raise
            time.sleep(30)


def main() -> None:
    fallback_only = sys.argv[1:2] == ["--inaturalist"]
    requested = {int(value) for value in sys.argv[2 if fallback_only else 1 :]}
    OUTPUT.mkdir(exist_ok=True)
    metadata_rows = []
    missing = []
    with (ROOT / "trees.tsv").open(newline="", encoding="utf-8") as file:
        for tree in csv.DictReader(file, delimiter="\t"):
            number = int(tree["Number"])
            if requested and number not in requested:
                continue
            species = tree["Latin name"]
            directory = OUTPUT / f"{number:02d}_{species.replace(' ', '_')}"
            candidates = [] if fallback_only else commons_candidates(species)
            if not candidates:
                candidates = inaturalist_candidates(species)
            if not candidates:
                missing.append(species)
                continue
            directory.mkdir(exist_ok=True)
            for index, candidate in enumerate(candidates[:3], start=1):
                filename = f"img{index}.jpg"
                destination = directory / filename
                try:
                    if not destination.exists():
                        download(candidate["url"], destination)
                except OSError as error:
                    print(f"Could not download {species}: {error}")
                    continue
                metadata_rows.append({"species": species, "file": str(directory.relative_to(ROOT) / filename), **candidate})
            print(f"{species}: {len(candidates[:3])} candidate(s)")
            time.sleep(1)
    if requested:
        return
    with (OUTPUT / "metadata.tsv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["species", "file", "source", "page", "url", "license", "license_url", "artist"], delimiter="\t")
        writer.writeheader()
        writer.writerows(metadata_rows)
    (OUTPUT / "missing.txt").write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")


if __name__ == "__main__":
    main()
