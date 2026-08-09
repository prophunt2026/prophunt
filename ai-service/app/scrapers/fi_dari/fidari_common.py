import os
import json
import re
from playwright.async_api import async_playwright
from app.scrapers.fi_dari.fidari_mapper import map_to_standard_schema

SINGLE_OUTPUT_FILE = "fidari_standard.json"


def save_or_update_json(new_items: list, file_path: str = SINGLE_OUTPUT_FILE):
    """
    Lit le fichier JSON et MET À JOUR les annonces existantes avec les nouvelles
    données enrichies de la page de détail, ou AJOUTE les nouvelles annonces.
    """
    if not new_items:
        return

    dataset = {}

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
            dataset[key] = item

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(list(dataset.values()), f, ensure_ascii=False, indent=2)

    print(f"  [DISQUE] Fichier mis à jour : {updated_count} mis à jour, {added_count} ajoutés. (Total: {len(dataset)})")


# ---------------------------------------------------------------------------
# EXTRACTION DES DONNÉES STRUCTURÉES
# Fi-Dari est en Next.js "App Router" : il n'y a PAS de #__NEXT_DATA__.
# Les données sont disponibles à deux endroits :
#   1) des blocs <script type="application/ld+json"> (fiable, toujours présent)
#   2) le payload React Server Components injecté via
#      self.__next_f.push([1, "...json échappé..."]) (plus riche : détail
#      unité par unité pour les programmes neufs, promoteur, amenities brutes)
# ---------------------------------------------------------------------------

_RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')
_RSC_OBJECT_KEYS = ('"project":{', '"property":{', '"annonce":{', '"listing":{')


def _extract_balanced_json(text: str, start: int) -> str:
    """Retourne la sous-chaîne JSON équilibrée (accolades) démarrant à `start`."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _extract_rsc_object(html: str) -> dict:
    """
    Concatène tous les chunks self.__next_f.push(...), les dé-échappe,
    puis retrouve l'objet métier principal (project / property / annonce).
    """
    chunks = _RSC_CHUNK_RE.findall(html)
    if not chunks:
        return {}

    full_text = "".join(chunks)
    try:
        # Les chunks sont des chaînes JS échappées (\" , \\n, \uXXXX...)
        full_text = full_text.encode("utf-8").decode("unicode_escape").encode("latin1").decode("utf-8")
    except Exception:
        full_text = full_text.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

    for key in _RSC_OBJECT_KEYS:
        idx = full_text.find(key)
        if idx == -1:
            continue
        start = idx + len(key) - 1  # position de l'accolade ouvrante
        obj_str = _extract_balanced_json(full_text, start)
        if obj_str:
            try:
                return json.loads(obj_str)
            except json.JSONDecodeError:
                continue
    return {}


def _extract_description_dom(html: str) -> str:
    """
    Le texte de description complet est toujours présent dans le DOM (le
    'line-clamp' est purement visuel en CSS, pas une troncature du HTML).
    Plus fiable que le champ RSC qui est parfois juste un pointeur "$1c"
    vers un chunk résolu ailleurs dans le flux.
    """
    m = re.search(r'<p lang="fr"[^>]*>(.*?)</p>', html, re.DOTALL)
    if not m:
        return ""
    text = re.sub(r'<[^>]+>', '', m.group(1))
    return text.strip()


def _extract_ld_json(html: str) -> dict:
    """
    Retourne le premier bloc JSON-LD de type produit immobilier
    (ApartmentComplex / RealEstateListing / House / Apartment / Product).
    """
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("@type") in (
            "ApartmentComplex", "RealEstateListing", "House", "Apartment",
            "Product", "SingleFamilyResidence",
        ):
            return data
    return {}


async def _wait_for_proximites(page, timeout_ms: int = 8000):
    """
    Les blocs 'Commodités' et 'Transport' se chargent en asynchrone côté client
    (skeleton gris 'bg-gray-100' pendant le chargement). On attend leur
    résolution (données réelles OU 'Aucune information disponible') avant
    d'extraire, en best-effort : si le timeout est dépassé, on continue quand
    même avec ce qu'on a.
    """
    try:
        await page.wait_for_function(
            """() => {
                const headings = Array.from(document.querySelectorAll('span'))
                    .filter(el => el.textContent.trim() === 'Transport' || el.textContent.trim() === 'Commodités');
                if (headings.length === 0) return true;
                return headings.every(h => {
                    const card = h.closest('[class*="rounded-xl"], [class*="bg-card"]');
                    return card && !card.querySelector('.bg-gray-100');
                });
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        pass


async def _extract_proximites(page) -> list:
    """
    Extrait les proximités depuis les cartes 'Commodités' et 'Transport'
    (div[class*="bg-card"][class*="rounded-xl"] contenant l'intitulé).
    Structure confirmée sur une page réelle (résidence Eddiar) :
      div[class*="divide-y"] > lignes, chacune avec :
        - le libellé dans div[class*="font-medium"][class*="text-gray-900"][class*="truncate"]
        - la distance dans div[class*="text-xs"][class*="text-muted-foreground"]
    Retourne une liste de {"categorie", "libelle", "valeur"}.
    Retourne [] si les cartes sont absentes, vides, ou encore en squelette.
    """
    proximites = []
    for label, categorie in (("Transport", "transport"), ("Commodités", "commodite")):
        card = page.locator(
            'div[class*="bg-card"][class*="rounded-xl"]'
        ).filter(has=page.locator(f"span:text-is('{label}')")).first
        if await card.count() == 0:
            continue

        if await card.locator("text=Aucune information disponible").count() > 0:
            continue
        if await card.locator(".bg-gray-100").count() > 0:
            continue  # toujours en squelette : pas de donnée exploitable

        # Cas 1 (structure réelle confirmée) : div[class*="divide-y"] avec
        # libellé + distance dans des divs dédiés
        divide = card.locator('div[class*="divide-y"]').first
        if await divide.count() > 0:
            names = divide.locator('div[class*="font-medium"][class*="text-gray-900"][class*="truncate"]')
            distances = divide.locator('div[class*="text-xs"][class*="text-muted-foreground"]')
            n = await names.count()
            m = await distances.count()
            for i in range(n):
                libelle = (await names.nth(i).inner_text()).strip()
                valeur = (await distances.nth(i).inner_text()).strip() if i < m else None
                if libelle:
                    proximites.append({"categorie": categorie, "libelle": libelle, "valeur": valeur or None})
            if n > 0:
                continue

        # Cas 2 (repli) : lignes en paires de <div> (libellé + badge), vu sur
        # certaines variantes/squelettes de la page
        content = card.locator('div[class*="p-6"][class*="pt-0"]').last
        rows = content.locator("div.flex.items-center.justify-between")
        n = await rows.count()
        if n > 0:
            for i in range(n):
                row_text = (await rows.nth(i).inner_text()).strip()
                if not row_text:
                    continue
                parts = [p.strip() for p in row_text.split("\n") if p.strip()]
                libelle = parts[0] if parts else None
                valeur = parts[1] if len(parts) > 1 else None
                if libelle:
                    proximites.append({"categorie": categorie, "libelle": libelle, "valeur": valeur})
            continue

        # Cas 3 (repli) : contenu en <p>/<span> directement
        texts = content.locator("p, span")
        n = await texts.count()
        raw_texts = []
        for i in range(n):
            t = (await texts.nth(i).inner_text()).strip()
            if t:
                raw_texts.append(t)
        for i in range(0, len(raw_texts), 2):
            libelle = raw_texts[i]
            valeur = raw_texts[i + 1] if i + 1 < len(raw_texts) else None
            proximites.append({"categorie": categorie, "libelle": libelle, "valeur": valeur})
    return proximites


_TYPE_KEYWORDS = [
    "Appartement", "Villa", "Maison", "Studio", "Duplex", "Terrain",
    "Local commercial", "Bureau", "Chalet", "Ferme", "Immeuble",
]
_USAGE_KEYWORDS = ["Habitation", "Commercial", "Professionnel", "Mixte", "Agricole", "Industriel"]


async def _extract_characteristics_bar(page) -> list:
    """
    Barre de caractéristiques du bien (prix affiché, type exact, usage,
    surface, pièces, étage...), un texte par bloc
    div[class*="h-[60px]"][class*="bg-[#F3F4F6]"] > p.font-semibold.truncate
    """
    items = page.locator(
        'div[class*="h-[60px]"][class*="bg-[#F3F4F6]"] > p[class*="font-semibold"][class*="truncate"]'
    )
    n = await items.count()
    texts = []
    for i in range(n):
        t = (await items.nth(i).inner_text()).strip()
        if t:
            texts.append(t)
    return texts


def _classify_characteristics(texts: list) -> dict:
    """
    Classe les textes de la barre de caractéristiques en champs exploitables :
    - prix_text : ce qui suit "Prix" tel quel (ex: "sur demande", "375 100 TND")
    - type / sous_type : ex "Appartement S+1" -> type=Appartement, sous_type=S+1
    - usage : ex "Habitation"
    """
    result = {"prix_text": None, "type": None, "sous_type": None, "usage": None}
    for t in texts:
        if t.lower().startswith("prix"):
            result["prix_text"] = t[4:].strip()
            continue
        if result["usage"] is None and t.strip() in _USAGE_KEYWORDS:
            result["usage"] = t.strip()
            continue
        if result["type"] is None:
            for kw in _TYPE_KEYWORDS:
                if t.lower().startswith(kw.lower()):
                    result["type"] = kw
                    remainder = t[len(kw):].strip()
                    result["sous_type"] = remainder or None
                    break
    return result


async def _extract_equipment_grid_spans(page) -> list:
    """
    Récupère tous les libellés d'équipements affichés dans les grilles
    "Les équipements privatifs" ET "Les atouts" (même classe de grille,
    plusieurs blocs possibles sur une même page).
    """
    grids = page.locator(
        'div[class*="grid-cols-1"][class*="md:grid-cols-3"][class*="gap-x-8"][class*="gap-y-4"]'
    )
    n = await grids.count()
    labels = []
    for i in range(n):
        spans = grids.nth(i).locator(
            'span[class*="text-sm"][class*="font-medium"][class*="text-foreground"]'
        )
        m = await spans.count()
        for j in range(m):
            t = (await spans.nth(j).inner_text()).strip()
            if t:
                labels.append(t)
    return labels


async def _extract_contact_card(page) -> dict:
    """
    Bloc contact (promoteur/agence) : logo (image dans l'avatar rond) + nom.
    """
    result = {"nom": None, "logo": None}
    card = page.locator('div[class*="flex"][class*="items-center"][class*="gap-4"]').filter(
        has=page.locator("h4")
    ).first
    if await card.count() == 0:
        card = page.locator('div[class*="flex"][class*="items-center"][class*="gap-6"]').filter(
            has=page.locator("h4")
        ).first
    if await card.count() == 0:
        return result

    h4 = card.locator("h4").first
    if await h4.count() > 0:
        result["nom"] = (await h4.inner_text()).strip() or None

    avatar_img = card.locator("img").first
    if await avatar_img.count() > 0:
        src = await avatar_img.get_attribute("src")
        if src:
            result["logo"] = src if src.startswith("http") else f"https://fi-dari.tn{src}"
    return result


async def collect_unit_urls_from_project(page, project_url: str) -> list:
    """
    Depuis la page d'une résidence (/projet/...), récupère les liens 'Voir
    détails' de la section 'Sélection de logements' vers chaque logement
    individuel. Une résidence type SUN CITY contient plusieurs biens
    (appartements) qu'il faut scraper un par un pour avoir prix/superficie/
    équipements par logement.
    """
    try:
        await page.goto(project_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(800)
    except Exception as e:
        print(f"  [X] Erreur chargement résidence {project_url} : {e}")
        return []

    links = page.locator("a[name='view-details-button']")
    n = await links.count()
    urls = []
    for i in range(n):
        href = await links.nth(i).get_attribute("href")
        if href:
            full = href if href.startswith("http") else f"https://fi-dari.tn{href}"
            if full not in urls:
                urls.append(full)
    return urls


async def extract_detail_page_data(page, url: str) -> dict:
    """
    Visite la page de détail et extrait l'objet complet en combinant :
      - le JSON-LD (fiable, prix / adresse / geo / amenities / images)
      - le payload RSC (le plus riche : détail par unité, promoteur, brut)
      - le DOM (numéros de téléphone, équipements en dernier recours)
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

    html = await page.content()

    # 1. JSON-LD
    try:
        ld = _extract_ld_json(html)
        if ld:
            data_obj["_ld"] = ld
    except Exception as e:
        print(f"  [WARN] JSON-LD non exploitable sur {url}: {e}")

    # 2. Payload RSC (project / property / annonce)
    try:
        rsc = _extract_rsc_object(html)
        if rsc:
            data_obj["_rsc"] = rsc
    except Exception as e:
        print(f"  [WARN] Payload RSC non exploitable sur {url}: {e}")

    # 3. Description complète (DOM, plus fiable que le pointeur RSC "$xx")
    try:
        desc_dom = _extract_description_dom(html)
        if desc_dom:
            data_obj["_description_dom"] = desc_dom
    except Exception as e:
        print(f"  [WARN] Description DOM non exploitable sur {url}: {e}")

    # 4. Proximités (Commodités / Transport) — chargées en async, on attend leur résolution
    try:
        await _wait_for_proximites(page)
        proximites = await _extract_proximites(page)
        if proximites:
            data_obj["_proximites"] = proximites
    except Exception as e:
        print(f"  [WARN] Proximités non exploitables sur {url}: {e}")

    # 5. Barre de caractéristiques (prix affiché tel quel, type exact, usage)
    try:
        carac_texts = await _extract_characteristics_bar(page)
        if carac_texts:
            data_obj["_characteristics"] = _classify_characteristics(carac_texts)
    except Exception as e:
        print(f"  [WARN] Barre de caractéristiques non exploitable sur {url}: {e}")

    # 6. Grilles d'équipements ("équipements privatifs" + "atouts")
    try:
        grid_labels = await _extract_equipment_grid_spans(page)
        if grid_labels:
            data_obj["_equipment_grid"] = grid_labels
    except Exception as e:
        print(f"  [WARN] Grille d'équipements non exploitable sur {url}: {e}")

    # 7. Carte contact (logo + nom du promoteur/agence)
    try:
        contact_card = await _extract_contact_card(page)
        if contact_card.get("nom") or contact_card.get("logo"):
            data_obj["_contact_card"] = contact_card
    except Exception as e:
        print(f"  [WARN] Carte contact non exploitable sur {url}: {e}")

    data_obj["url"] = url
    if not data_obj.get("id") and not data_obj.get("_id"):
        rsc_id = data_obj.get("_rsc", {}).get("id")
        data_obj["id"] = rsc_id or url.rstrip('/').split('/')[-1]

    # 8. Téléphones via le DOM (fiable, indépendant du JS-rendering)
    phones = []
    phone_btns = page.locator(
        "button:has-text('Afficher'), button:has-text('Voir'), "
        "button:has-text('Téléphone'), a[href^='tel:']"
    )
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

    # 9. Équipements DOM en dernier recours (si ni JSON-LD ni RSC n'en donnent)
    if not data_obj.get("_ld", {}).get("amenityFeature") and not data_obj.get("_rsc", {}).get("amenities"):
        eq_elements = await page.locator(
            "div[class*='equipment'] span, div[class*='feature'] span, div[class*='amenity'] span"
        ).all()
        dom_eqs = []
        for el in eq_elements:
            txt = (await el.inner_text()).strip()
            if txt and len(txt) < 35 and '\n' not in txt:
                dom_eqs.append(txt)
        if dom_eqs:
            data_obj["_dom_equipments"] = dom_eqs

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

        detail_urls = await collect_detail_urls_from_category(page, base_target_url)

        # La rubrique "neuf" liste des RÉSIDENCES (/projet/...), pas des biens
        # individuels. Contrairement à "acheter"/"louer" où chaque annonce est
        # directement un logement, il faut ici descendre dans chaque résidence
        # et scraper chaque appartement/villa un par un via "Voir détails".
        if category_key == "neuf":
            expanded_urls = []
            for project_url in detail_urls:
                unit_urls = await collect_unit_urls_from_project(page, project_url)
                if unit_urls:
                    expanded_urls.extend(unit_urls)
                else:
                    # Résidence sans logements listés (rare) : on garde la page projet telle quelle
                    expanded_urls.append(project_url)
            print(f"  -> {len(detail_urls)} résidences -> {len(expanded_urls)} logements individuels à scraper")
            detail_urls = expanded_urls

        print(f"\n--- ÉTAPE 2 : Extraction détaillée des {len(detail_urls)} fiches ---")

        for idx, detail_url in enumerate(detail_urls, start=1):
            print(f"[{idx}/{len(detail_urls)}] Scraping détail : {detail_url}")

            raw_detail = await extract_detail_page_data(page, detail_url)
            if raw_detail:
                standard_item = map_to_standard_schema(raw_detail, category_key, detail_url)
                save_or_update_json([standard_item], SINGLE_OUTPUT_FILE)

        await browser.close()
        print(f"\n[OK] Fin du traitement de la rubrique {category_key.upper()}.")