"""
scraper_location.py - Moteur de scraping des biens en LOCATION (Playwright + Requests).

Même structure que scraper.py (biens en vente), adapté pour :
- pointer vers LISTING_URL_LOCATION au lieu de LISTING_URL
- récupérer en plus le prix affiché sur la carte-liste (utile en fallback,
  car pour une location le prix est souvent affiché en "X TND / Mois")
- s'appuyer sur build_record/get_transaction_type (parsers.py) qui route
  automatiquement le prix vers transaction.loyer_mensuel pour ces annonces.
"""

import time
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.scrapers.scraper_Home_in_Tunisia.parsers import is_valid_record, parse_number, build_record
from app.scrapers.scraper_Home_in_Tunisia.config import BASE_URL, LISTING_URL_LOCATION, USER_AGENT, HEADERS


def fetch_listing_items_location_with_playwright(page, max_scrolls=10):
    print(f"Navigation vers : {LISTING_URL_LOCATION}")
    page.goto(LISTING_URL_LOCATION, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("ul.listing", timeout=10000)

    previous_count = 0
    for scroll_idx in range(1, max_scrolls + 1):
        current_count = page.locator("ul.listing > li.property").count()
        print(f"Scroll {scroll_idx}/{max_scrolls} - Biens détectés : {current_count}")

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)

        if current_count == previous_count and scroll_idx > 2:
            print("Plus de nouveaux biens chargés via scroll.")
            break
        previous_count = current_count

    html_content = page.content()
    soup = BeautifulSoup(html_content, "lxml")

    results = []
    ul = soup.find("ul", class_="listing")
    if not ul:
        return results

    for li in ul.find_all("li", class_="property"):
        prop_id = li.get("data-property-id")
        link_tag = li.find("a", href=True)
        if link_tag:
            href = link_tag["href"]
            url = BASE_URL + href if href.startswith("/") else href
        elif prop_id:
            url = f"{BASE_URL}/fr/propriété/{prop_id}"
        else:
            continue

        card_infos = {}
        prix_liste_text = None
        article = li.find("article")
        if article:
            for sub_li in article.find_all("li"):
                span = sub_li.find("span")
                if span and span.get("class"):
                    field = span["class"][0]
                    value = sub_li.get_text(strip=True)
                    if value:
                        card_infos[field] = value
            # La ligne de prix n'a pas de <span> interne (contrairement à
            # rooms/bedrooms/bathrooms/area) : elle est directement sur le <li class="price">
            price_tag = article.find("li", class_="price")
            if price_tag:
                prix_liste_text = price_tag.get_text(strip=True)

        type_tag = li.find("h3")
        results.append({
            "url": url,
            "id": prop_id,
            "type_liste": type_tag.get_text(strip=True).split(",")[0] if type_tag else None,
            "nombre_pieces_liste": parse_number(card_infos.get("rooms")),
            "nombre_chambres_liste": parse_number(card_infos.get("bedrooms")),
            "nombre_salles_bain_liste": parse_number(card_infos.get("bathrooms")),
            "superficie_liste": parse_number(card_infos.get("area")),
            "loyer_liste": parse_number(prix_liste_text) if prix_liste_text else None,
        })

    return results


def scrape_all_location(max_properties=None, delay=1.0, headless=True):
    all_items = []

    with sync_playwright() as p:
        print("Lancement du navigateur Chromium (Playwright)...")
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            all_items = fetch_listing_items_location_with_playwright(page, max_scrolls=8)
            print(f"\nTotal des annonces (location) capturées dans le DOM : {len(all_items)}")
        except PlaywrightTimeoutError:
            print("Erreur : Temps d'attente dépassé lors du chargement de la page de recherche.")
        finally:
            browser.close()

    if not all_items:
        print("Aucune annonce de location trouvée.")
        return []

    if max_properties:
        all_items = all_items[:max_properties]

    records = []

    for i, item in enumerate(all_items, 1):
        try:
            resp = requests.get(item["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            record = build_record(resp.text, item["url"], listing_extra=item)

            # Validation centralisée (Type, Pays, Devise, mots-clés exclus)
            is_valid, reason = is_valid_record(record)
            if not is_valid:
                print(f"[{i}/{len(all_items)}] {item['url']} -> Ignoré ({reason})")
                continue

            records.append(record)
            print(
                f"[{i}/{len(all_items)}] {item['url']} -> OK "
                f"({record['bien']['type']}, {record['transaction']['type']})"
            )
        except requests.RequestException as e:
            print(f"Erreur lors du fetch de la fiche {item['url']}: {e}")

        time.sleep(delay)

    print(f"\n{len(records)} biens en location retenus sur {len(all_items)} annonces vues")
    return records