import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  Logger,
} from '@nestjs/common';
import type { Request } from 'express';

import { AccessLevel, getAccessLevel } from './route-config';

/**
 * RolesGuard — Second garde du pipeline Gateway.
 *
 * S'exécute APRÈS JwtGuard (qui a déjà validé le token et attaché req.user).
 *
 * Responsabilités :
 *   - Si la route requiert ADMIN → vérifier que req.user.role === 'ADMIN'.
 *   - Sinon → laisser passer (JwtGuard a déjà vérifié l'authentification).
 *
 * Erreurs :
 *   403 Forbidden → utilisateur authentifié mais rôle insuffisant
 *
 * Distinction 401 / 403 :
 *   401 → géré par JwtGuard (pas de token ou token invalide)
 *   403 → géré ici (token valide mais role insuffisant)
 */
@Injectable()
export class RolesGuard implements CanActivate {
  private readonly logger = new Logger(RolesGuard.name);

  canActivate(context: ExecutionContext): boolean {
    const req   = context.switchToHttp().getRequest<Request>();
    const path  = req.path;
    const level = getAccessLevel(path);

    // PUBLIC ou AUTHENTICATED → pas de vérification de rôle ici
    if (level !== AccessLevel.ADMIN) {
      return true;
    }

    const user = (req as any).user;

    // Sécurité défensive : si user absent c'est un bug (JwtGuard aurait dû refuser)
    if (!user) {
      this.logger.error(
        `RolesGuard: req.user absent pour une route ADMIN (${path}). ` +
        'Vérifiez que JwtGuard est bien appliqué avant RolesGuard.',
      );
      throw new ForbiddenException('Accès refusé.');
    }

    if (user.role !== 'ADMIN') {
      this.logger.warn(
        `Accès refusé pour role=${user.role} sur ${path}`,
      );
      throw new ForbiddenException(
        'Accès réservé aux administrateurs.',
      );
    }

    return true;
  }
}
