"""
Récupération du numéro de téléphone sur Mubawab.

Mubawab utilise au moins 2 templates différents selon les annonces :
- "nouvelle" variante : <a class="contactPhoneClick">, onclick="sendPhoneLead(...)"
- "ancienne" variante : <div class="phone-number-box contact-box">,
  onclick="showPhoneAdPage(...)"

Dans les deux cas, le clic ouvre une popup (div#phonePopup) contenant le(s)
numéro(s) dans des <p class="phoneText dirLtr darkblue"> à l'intérieur de
div#response. Il peut y avoir plusieurs numéros pour une même annonce.

On simule donc : clic sur le bouton (peu importe la variante) -> attente de
la popup -> lecture de tous les <p class="phoneText"> -> fermeture.
"""

import re
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, InvalidSessionIdException, WebDriverException

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)

PATTERN_TELEPHONE = re.compile(r"^[\d\s\+]{6,}$")

# Mubawab a au moins 2 templates différents selon les annonces :
# - "nouvelle" variante : <a class="contactPhoneClick">, onclick="sendPhoneLead(...)"
# - "ancienne" variante : <div class="phone-number-box contact-box">, onclick="showPhoneAdPage(...)"
SELECTEURS_BOUTON_TELEPHONE = [
    "a.contactPhoneClick",
    "div.phone-number-box.contact-box",
]


def trouver_bouton_telephone(driver, timeout=15):
    """Essaie chaque variante connue jusqu'à ce qu'un bouton visible soit
    trouvé, ou renvoie None après le délai."""

    fin = time.time() + timeout

    while time.time() < fin:

        for selecteur in SELECTEURS_BOUTON_TELEPHONE:

            elements = driver.find_elements(By.CSS_SELECTOR, selecteur)
            visibles = [e for e in elements if e.is_displayed()]

            if visibles:
                return visibles[0]

        time.sleep(0.3)

    return None


def creer_driver(headless: bool = True):

    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1366,900")
    options.add_argument(f"user-agent={USER_AGENT}")

    return webdriver.Chrome(options=options)


def fermer_popup_cookies(driver):
    """Certains sites bloquent les clics tant qu'un bandeau cookies est
    ouvert. On tente plusieurs approches, sans bloquer si absent."""

    selecteurs_possibles = [
        "#didomi-notice-agree-button",
        "button#onetrust-accept-btn-handler",
        ".didomi-continue-without-agreeing",
    ]

    for selecteur in selecteurs_possibles:
        try:
            bouton = driver.find_element(By.CSS_SELECTOR, selecteur)
            if bouton.is_displayed():
                bouton.click()
                time.sleep(0.5)
                return
        except Exception:
            continue

    # Fallback : bandeau mubawab.tn avec un bouton texte "ACCEPTER"
    try:
        bouton = driver.find_element(
            By.XPATH,
            "//*[self::button or self::div or self::a]"
            "[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accepter')]"
        )
        if bouton.is_displayed():
            bouton.click()
            time.sleep(0.5)
    except Exception:
        pass


def diagnostiquer_bouton_appelez(driver):
    """Si le sélecteur habituel ne trouve rien, on cherche directement dans
    le HTML de la page tous les endroits où le mot 'Appelez' apparaît, et on
    affiche le contexte autour (pour identifier la vraie classe/balise sans
    avoir à rouvrir les DevTools à la main)."""

    source = driver.page_source

    occurrences = [m.start() for m in re.finditer("Appelez", source)]

    print(f"\n--- DIAGNOSTIC : {len(occurrences)} occurrence(s) de 'Appelez' trouvée(s) ---")

    for i, pos in enumerate(occurrences[:5], start=1):
        debut = max(0, pos - 250)
        fin = pos + 50
        print(f"\n[Occurrence {i}]")
        print(source[debut:fin])

    with open("debug_page_source.html", "w", encoding="utf-8") as f:
        f.write(source)

    print("\nPage complète sauvegardée : debug_page_source.html")
    print("--- FIN DIAGNOSTIC ---\n")


def fermer_popup_telephone(driver):
    """Ferme la popup #phonePopup après lecture, pour repartir propre
    (utile si jamais on enchaîne plusieurs actions sur la même page)."""

    try:
        bouton_fermer = driver.find_element(
            By.CSS_SELECTOR,
            "div.fancybox-close, div[title='Fermer']"
        )
        if bouton_fermer.is_displayed():
            bouton_fermer.click()
    except Exception:
        pass


def scraper_telephone_mubawab(url: str, driver, debug: bool = True) -> list:
    """Retourne la liste des numéros affichés dans la popup Mubawab pour
    l'URL donnée (souvent 1, parfois 2), ou [] si rien n'a pu être récupéré.

    Si debug=True, sauvegarde une capture d'écran en cas d'échec pour
    comprendre ce qui bloque (bandeau cookie, page différente, etc.)."""

    try:

        driver.get(url)

        print("URL réellement chargée :", driver.current_url)
        print("Titre de la page :", driver.title)

        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        fermer_popup_cookies(driver)

        bouton = trouver_bouton_telephone(driver, timeout=15)

        if bouton is None:
            if debug:
                driver.save_screenshot("debug_page_avant_clic.png")
                print("Aucun bouton téléphone trouvé (aucune des 2 variantes connues).")
                print("Capture sauvegardée : debug_page_avant_clic.png")
                diagnostiquer_bouton_appelez(driver)
            raise TimeoutException("Bouton téléphone introuvable")

        # Scroll pour être sûr que le bouton est visible avant de cliquer
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bouton)
        time.sleep(0.5)

        try:
            bouton.click()
        except Exception:
            # Si un élément par-dessus intercepte le clic normal, on force en JS
            driver.execute_script("arguments[0].click();", bouton)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#phoneCol #response p.phoneText")
                )
            )
        except Exception:
            if debug:
                driver.save_screenshot("debug_apres_clic.png")
                print("Popup/numéro introuvable après le clic.")
                print("Capture sauvegardée : debug_apres_clic.png")
            raise

        elements_numero = driver.find_elements(
            By.CSS_SELECTOR,
            "#phoneCol #response p.phoneText"
        )

        numeros = [
            e.text.strip()
            for e in elements_numero
            if PATTERN_TELEPHONE.match(e.text.strip())
        ]

        fermer_popup_telephone(driver)

        if not numeros:
            print("Popup ouverte mais aucun numéro détecté :", url)

        return numeros

    except InvalidSessionIdException:
        # Session Chrome morte / crashée : on laisse remonter cette erreur
        # au script appelant, qui va redémarrer un navigateur frais.
        # (Un simple [] ici cacherait le problème pour toutes les annonces
        # suivantes, comme c'était le cas avant.)
        raise

    except Exception as e:
        print("Erreur récupération téléphone :", url, "-", repr(e))
        return []


if __name__ == "__main__":
    # Test manuel sur une seule annonce avant de lancer sur toute la liste.
    # Remplace l'URL par la vraie annonce que tu as testée dans DevTools.
    url_test = "https://www.mubawab.tn/fr/a/REMPLACE_MOI"

    driver = creer_driver(headless=False)  # headless=False pour observer le clic

    try:
        resultat = scraper_telephone_mubawab(url_test, driver)
        print("Téléphone(s) trouvé(s) :", resultat)
    finally:
        driver.quit()