"""
Étape 3 du pipeline Mubawab : récupération des numéros de téléphone via Selenium.

Mubawab affiche les téléphones uniquement après un clic sur un bouton,
ce qui rend requests/BeautifulSoup insuffisants — Selenium est nécessaire.

Deux variantes de bouton selon les annonces :
  - <a class="contactPhoneClick">
  - <div class="phone-number-box contact-box">
"""

import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    InvalidSessionIdException,
    WebDriverException,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)

PATTERN_TELEPHONE = re.compile(r"^[\d\s\+]{6,}$")

SELECTEURS_BOUTON = [
    "a.contactPhoneClick",
    "div.phone-number-box.contact-box",
]

# Redémarrage préventif du driver tous les N annonces
REDEMARRAGE_TOUTES_LES = 200


# ==========================================
# HELPERS
# ==========================================

def _creer_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1366,900")
    options.add_argument(f"user-agent={USER_AGENT}")
    return webdriver.Chrome(options=options)


def _fermer_popup_cookies(driver) -> None:
    selecteurs = [
        "#didomi-notice-agree-button",
        "button#onetrust-accept-btn-handler",
        ".didomi-continue-without-agreeing",
    ]
    for sel in selecteurs:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed():
                btn.click()
                time.sleep(0.5)
                return
        except Exception:
            continue
    # Fallback texte "accepter"
    try:
        btn = driver.find_element(
            By.XPATH,
            "//*[self::button or self::div or self::a]"
            "[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepter')]",
        )
        if btn.is_displayed():
            btn.click()
            time.sleep(0.5)
    except Exception:
        pass


def _trouver_bouton_telephone(driver, timeout: int = 15):
    fin = time.time() + timeout
    while time.time() < fin:
        for sel in SELECTEURS_BOUTON:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            visibles = [e for e in elements if e.is_displayed()]
            if visibles:
                return visibles[0]
        time.sleep(0.3)
    return None


def _scraper_telephone(url: str, driver) -> list:
    """Retourne la liste des numéros pour une annonce, ou [] si introuvable."""
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        _fermer_popup_cookies(driver)

        bouton = _trouver_bouton_telephone(driver)
        if bouton is None:
            print(f"Bouton téléphone introuvable : {url}")
            return []

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", bouton)
        time.sleep(0.5)
        try:
            bouton.click()
        except Exception:
            driver.execute_script("arguments[0].click();", bouton)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#phoneCol #response p.phoneText"))
        )

        elements = driver.find_elements(By.CSS_SELECTOR, "#phoneCol #response p.phoneText")
        numeros  = [e.text.strip() for e in elements if PATTERN_TELEPHONE.match(e.text.strip())]

        if not numeros:
            print(f"Popup ouverte mais aucun numéro détecté : {url}")

        return numeros

    except InvalidSessionIdException:
        raise  # remonter pour que l'appelant redémarre le driver
    except Exception as e:
        print(f"Erreur téléphone {url} : {repr(e)}")
        return []


# ==========================================
# LOGIQUE COMMUNE (privée)
# ==========================================

def _executer_passage_telephone(annonces: list, label: str = "TÉLÉPHONES") -> list:
    """
    Parcourt toutes les annonces dont telephone est vide,
    tente de récupérer les numéros via Selenium.
    Modifie la liste en place et la retourne.
    """
    a_traiter = [a for a in annonces if not a.get("telephone")]

    print(f"\n=================================")
    print(f"{label} : {len(a_traiter)} annonces à traiter (sur {len(annonces)})")
    print(f"=================================")

    if not a_traiter:
        return annonces

    driver = _creer_driver(headless=True)

    try:
        for i, annonce in enumerate(a_traiter, start=1):
            url = annonce.get("url", "")
            print(f"\n{label} {i}/{len(a_traiter)} - {url}")

            try:
                telephones = _scraper_telephone(url, driver)
            except (InvalidSessionIdException, WebDriverException) as e:
                print(f"Session Chrome perdue ({e.__class__.__name__}), redémarrage...")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = _creer_driver(headless=True)
                try:
                    telephones = _scraper_telephone(url, driver)
                except Exception as e2:
                    print(f"Echec après redémarrage : {e2}")
                    telephones = []

            annonce["telephone"] = telephones
            print(f"Trouvé : {telephones if telephones else 'aucun'}")

            if i % REDEMARRAGE_TOUTES_LES == 0:
                print(f"Redémarrage préventif du driver (après {i} annonces)")
                driver.quit()
                driver = _creer_driver(headless=True)

            time.sleep(1)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    sans_telephone = sum(1 for a in annonces if not a.get("telephone"))
    print(f"\n=================================")
    print(f"{label} TERMINÉ : {len(annonces) - sans_telephone}/{len(annonces)} remplis")
    print(f"=================================")

    return annonces


# ==========================================
# FONCTIONS PUBLIQUES
# ==========================================

def scrape_telephones(annonces: list) -> list:
    """
    Reçoit la liste d'annonces enrichies (sortie de scrape_details),
    ajoute les numéros de téléphone via Selenium et retourne la liste
    mise à jour (sans écrire de fichier).

    Premier passage : traite toutes les annonces sans téléphone.
    Les annonces qui échouent gardent telephone=[] pour le retry.

    Args:
        annonces: liste de dicts avec champ "url" et "telephone": []

    Returns:
        list: même liste avec "telephone" rempli quand possible
    """
    return _executer_passage_telephone(annonces, label="TÉLÉPHONES (1er passage)")


def retry_telephones(annonces: list) -> list:
    """
    Deuxième passage ciblé : retente uniquement les annonces dont
    telephone est encore vide après scrape_telephones().

    Même logique Selenium, même gestion des crashes Chrome.
    Conçu pour les runs longs (2800+ annonces) où quelques annonces
    ratent inévitablement lors du premier passage.

    Args:
        annonces: liste retournée par scrape_telephones()

    Returns:
        list: même liste avec les téléphones manquants comblés si possible
    """
    vides_avant = sum(1 for a in annonces if not a.get("telephone"))

    if vides_avant == 0:
        print("\n[Retry téléphones] Aucune annonce sans téléphone — retry ignoré.")
        return annonces

    print(f"\n[Retry téléphones] {vides_avant} annonces sans téléphone à retenter.")
    annonces = _executer_passage_telephone(annonces, label="TÉLÉPHONES (retry)")

    vides_apres = sum(1 for a in annonces if not a.get("telephone"))
    recuperes   = vides_avant - vides_apres
    print(f"[Retry téléphones] {recuperes} téléphones supplémentaires récupérés "
          f"({vides_apres} encore vides).")

    return annonces
