"""
scraper.py - Moteur de scraping (Playwright + Requests).
"""

import time
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from app.scrapers.scraper_Home_in_Tunisia.parsers import is_valid_record, parse_number, build_record
from app.scrapers.scraper_Home_in_Tunisia.config import BASE_URL, LISTING_URL, USER_AGENT, HEADERS, TYPES_VOULUS


def fetch_listing_items_with_playwright(page, max_scrolls=10):
    print(f"Navigation vers : {LISTING_URL}")
    page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=30000)
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
        article = li.find("article")
        if article:
            for sub_li in article.find_all("li"):
                span = sub_li.find("span")
                if span and span.get("class"):
                    field = span["class"][0]
                    value = sub_li.get_text(strip=True)
                    if value:
                        card_infos[field] = value

        type_tag = li.find("h3")
        results.append({
            "url": url,
            "id": prop_id,
            "type_liste": type_tag.get_text(strip=True).split(",")[0] if type_tag else None,
            "nombre_pieces_liste": parse_number(card_infos.get("rooms")),
            "nombre_chambres_liste": parse_number(card_infos.get("bedrooms")),
            "nombre_salles_bain_liste": parse_number(card_infos.get("bathrooms")),
            "superficie_liste": parse_number(card_infos.get("area")),
        })

    return results


def scrape_all(max_properties=None, delay=1.0, headless=True):
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
            all_items = fetch_listing_items_with_playwright(page, max_scrolls=8)
            print(f"\nTotal des annonces capturées dans le DOM : {len(all_items)}")
        except PlaywrightTimeoutError:
            print("Erreur : Temps d'attente dépassé lors du chargement de la page listing.")
        finally:
            browser.close()

    if not all_items:
        print("Aucune annonce trouvée.")
        return []

    if max_properties:
        all_items = all_items[:max_properties]

    records = []
    skipped_type = 0

    for i, item in enumerate(all_items, 1):
        try:
            resp = requests.get(item["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            record = build_record(resp.text, item["url"], listing_extra=item)

            # Validation centralisée (Type, Pays, Devise)
            is_valid, reason = is_valid_record(record)
            if not is_valid:
                print(f"[{i}/{len(all_items)}] {item['url']} -> Ignoré ({reason})")
                continue

            records.append(record)
            print(f"[{i}/{len(all_items)}] {item['url']} -> OK ({record['bien']['type']})")
        except requests.RequestException as e:
            print(f"Erreur lors du fetch de la fiche {item['url']}: {e}")

        time.sleep(delay)

    print(f"\n{len(records)} biens retenus, {skipped_type} ignorés (type non voulu)")
    return records