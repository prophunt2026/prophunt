import os
import json
import re
from playwright.async_api import async_playwright
from fidari_mapper import map_to_standard_schema

SINGLE_OUTPUT_FILE = "fidari_standard.json"


def save_or_update_json(new_items: list, file_path: str = SINGLE_OUTPUT_FILE):
    """
    Lit le fichier JSON et MET À JOUR les annonces existantes avec les nouvelles
    données enrichies de la page de détail, ou AJOUTE les nouvelles annonces.
    """
    if not new_items:
        return

    dataset = {}

    # 1. Charger l'existant en mémoire (indexé par ID/URL)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_items = json.load(f)
                for item in existing_items:
                    key = (
                        item.get("listing", {}).get("id_universel")
                        or item.get("listing", {}).get("url_canonique")
                    )
                    if key:
                        dataset[key] = item
        except json.JSONDecodeError:
            dataset = {}

    updated_count = 0
    added_count = 0

    # 2. Écraser les anciennes données ou ajouter les nouvelles
    for item in new_items:
        key = (
            item.get("listing", {}).get("id_universel")
            or item.get("listing", {}).get("url_canonique")
        )
        if key:
            if key in dataset:
                updated_count += 1
            else:
                added_count += 1
            dataset[key] = item  # Remplacement avec les nouvelles données détaillées

    # 3. Réécriture propre sur le disque
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(list(dataset.values()), f, ensure_ascii=False, indent=2)

    print(f"  [DISQUE] Fichier mis à jour : {updated_count} mis à jour, {added_count} ajoutés. (Total: {len(dataset)})")


async def extract_detail_page_data(page, url: str) -> dict:
    """
    Visite la page de détail spécifique et extrait l'objet complet depuis __NEXT_DATA__
    et complète avec les boutons du DOM (numéros de téléphone et équipements).
    """
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print(f"  [X] Erreur chargement {url} : {e}")
            return {}

    await page.wait_for_timeout(1000)

    data_obj = {}

    # 1. Scraping via __NEXT_DATA__
    try:
        next_data_el = page.locator("#__NEXT_DATA__")
        if await next_data_el.count() > 0:
            content_str = await next_data_el.inner_text()
            json_data = json.loads(content_str)
            page_props = json_data.get("props", {}).get("pageProps", {})

            # Recherche récursive de l'objet principal du bien
            candidate = (
                page_props.get("property")
                or page_props.get("project")
                or page_props.get("annonce")
                or page_props.get("data")
                or page_props.get("initialProperty")
                or page_props.get("initialProject")
            )
            if isinstance(candidate, dict):
                data_obj = candidate
    except Exception as e:
        print(f"  [WARN] __NEXT_DATA__ non accessible sur {url}: {e}")

    data_obj["url"] = url
    if not data_obj.get("id") and not data_obj.get("_id"):
        data_obj["id"] = url.rstrip('/').split('/')[-1]

    # 2. Récupération des numéros de téléphone via le DOM
    phones = data_obj.get("phones") or []
    if isinstance(phones, str):
        phones = [phones]

    # Clic sur les boutons "Afficher le numéro" si présents
    phone_btns = page.locator("button:has-text('Afficher'), button:has-text('Voir'), button:has-text('Téléphone'), a[href^='tel:']")
    if await phone_btns.count() > 0:
        try:
            await phone_btns.first.click(timeout=1500)
            await page.wait_for_timeout(500)
        except Exception:
            pass

    tel_links = await page.locator("a[href^='tel:']").all()
    for link in tel_links:
        href = await link.get_attribute("href")
        if href:
            num = href.replace("tel:", "").strip()
            if num and num not in phones:
                phones.append(num)

    data_obj["phones"] = phones

    # 3. Récupération des équipements depuis le DOM si absents du JSON
    if not data_obj.get("equipments") and not data_obj.get("equipements") and not data_obj.get("features"):
        eq_elements = await page.locator("ul li, div[class*='equipment'], div[class*='feature'], div[class*='amenity']").all()
        dom_eqs = []
        for el in eq_elements:
            txt = (await el.inner_text()).strip()
            if txt and len(txt) < 35 and '\n' not in txt:
                dom_eqs.append(txt)
        if dom_eqs:
            data_obj["equipments"] = dom_eqs

    return data_obj


async def collect_detail_urls_from_category(page, base_target_url: str, max_pages: int = 50) -> list:
    """Parcourt les pages de la rubrique pour récupérer toutes les URLs individuelles."""
    detail_urls = []
    seen_urls = set()
    page_index = 1

    print(f"\n--- ÉTAPE 1 : Collecte des URLs depuis {base_target_url} ---")

    while page_index <= max_pages:
        current_url = f"{base_target_url}?page={page_index}" if page_index > 1 else base_target_url
        print(f"Page {page_index} : Recherche des liens sur {current_url}...")

        try:
            res = await page.goto(current_url, wait_until="domcontentloaded", timeout=20000)
            if res and res.status == 404:
                break
        except Exception:
            break

        await page.wait_for_timeout(1200)

        cards = await page.locator("a[href*='/detail/'], a[href*='/projet/'], a[href*='/annonce/'], a[href*='/immobilier/']").all()
        new_on_page = 0

        for card in cards:
            href = await card.get_attribute("href")
            if not href:
                continue

            if re.search(r'/(detail|projet|annonce)/|[a-f0-9]{24}$', href, re.I):
                full_url = href if href.startswith("http") else f"https://fi-dari.tn{href}"
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    detail_urls.append(full_url)
                    new_on_page += 1

        print(f"  -> {new_on_page} URLs d'annonces trouvées sur cette page.")

        if new_on_page == 0 and page_index > 1:
            print("Fin des annonces disponibles.")
            break

        page_index += 1

    print(f"TOTAL URLS COLLECTÉES : {len(detail_urls)}")
    return detail_urls


async def scrape_category_with_playwright(base_target_url: str, category_key: str):
    
    print(f" DÉBUT SCRAPING COMPLET : {category_key.upper()}")
    

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # ÉTAPE 1 : Récupération des URLs
        detail_urls = await collect_detail_urls_from_category(page, base_target_url)

        # ÉTAPE 2 : Scraping page par page et mise à jour JSON
        print(f"\n--- ÉTAPE 2 : Extraction détaillée des {len(detail_urls)} fiches ---")
        
        for idx, detail_url in enumerate(detail_urls, start=1):
            print(f"[{idx}/{len(detail_urls)}] Scraping détail : {detail_url}")
            
            raw_detail = await extract_detail_page_data(page, detail_url)
            if raw_detail:
                standard_item = map_to_standard_schema(raw_detail, category_key, detail_url)
                
                # Mise à jour ou remplacement dans le JSON sur le disque
                save_or_update_json([standard_item], SINGLE_OUTPUT_FILE)

        await browser.close()
        print(f"\n[OK] Fin du traitement de la rubrique {category_key.upper()}.")