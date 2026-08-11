/**
 * route-config.ts — Table de permissions centralisée du Gateway.
 *
 * Principe :
 *   Chaque route peut avoir un niveau d'accès :
 *     PUBLIC        → aucune vérification JWT
 *     AUTHENTICATED → JWT valide requis (USER ou ADMIN)
 *     ADMIN         → JWT valide + role === 'ADMIN'
 *
 * Comment ajouter une règle :
 *   1. Ajouter un pattern dans ROUTE_PERMISSIONS
 *   2. Le JwtGuard et RolesGuard liront automatiquement cette table
 *   → Aucune autre modification nécessaire
 *
 * Les patterns sont testés dans l'ordre — le premier match l'emporte.
 */

export enum AccessLevel {
  PUBLIC        = 'PUBLIC',
  AUTHENTICATED = 'AUTHENTICATED',
  ADMIN         = 'ADMIN',
}

export interface RoutePermission {
  /** Regex testée contre la path complète (ex: /v1/service-ia/scraping/tecnocasa) */
  pattern: RegExp;
  level:   AccessLevel;
}

/**
 * Table de permissions — ordonnée, premier match gagne.
 *
 * Règles actuelles :
 *   /v1/auth/*        → PUBLIC  (signup, signin, refresh sans token)
 *   /v1/service-ia/*  → ADMIN   (scraping réservé aux admins)
 *   tout le reste     → PUBLIC  (par défaut conservateur — à durcir selon besoin)
 */
export const ROUTE_PERMISSIONS: RoutePermission[] = [
  // ── Auth routes — toujours publiques ─────────────────────────────────────
  {
    pattern: /^\/v1\/auth\//,
    level:   AccessLevel.PUBLIC,
  },

  // ── Scraping — ADMIN uniquement ───────────────────────────────────────────
  {
    pattern: /^\/v1\/service-ia\//,
    level:   AccessLevel.ADMIN,
  },

  // ── CRUD routes — authentifié (USER ou ADMIN) ─────────────────────────────
  {
    pattern: /^\/v1\/crud\//,
    level:   AccessLevel.AUTHENTICATED,
  },
];

/**
 * Retourne le niveau d'accès requis pour un chemin donné.
 * Si aucune règle ne correspond, retourne PUBLIC par défaut.
 */
export function getAccessLevel(path: string): AccessLevel {
  for (const rule of ROUTE_PERMISSIONS) {
    if (rule.pattern.test(path)) {
      return rule.level;
    }
  }
  return AccessLevel.PUBLIC;
}
