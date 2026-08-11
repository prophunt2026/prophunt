import {
  CanActivate,
  ExecutionContext,
  Injectable,
  Logger,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Request } from 'express';
import * as jwt from 'jsonwebtoken';

import { AccessLevel, getAccessLevel } from './route-config';

/**
 * JwtGuard — Premier garde du pipeline Gateway.
 *
 * Responsabilités :
 *   1. Lire le niveau d'accès requis pour la route (route-config.ts).
 *   2. Si PUBLIC → laisser passer sans vérification.
 *   3. Si AUTHENTICATED ou ADMIN :
 *      a. Vérifier la présence du header Authorization: Bearer <token>.
 *      b. Vérifier la signature JWT avec JWT_SECRET_KEY.
 *      c. Vérifier l'expiration (exp).
 *      d. Vérifier que type === 'access' (un refresh token est refusé).
 *      e. Attacher { userId, email, role } à req pour le RolesGuard.
 *
 * Ce garde ne connaît pas les rôles — c'est le RolesGuard qui s'en charge.
 *
 * Erreurs :
 *   401 Unauthorized → token absent, invalide, expiré, mauvais type
 */
@Injectable()
export class JwtGuard implements CanActivate {
  private readonly logger = new Logger(JwtGuard.name);

  constructor(private readonly config: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const req    = context.switchToHttp().getRequest<Request>();
    const path   = req.path;
    const level  = getAccessLevel(path);

    // Route publique — pas de vérification
    if (level === AccessLevel.PUBLIC) {
      return true;
    }

    // Extraire le token depuis Authorization: Bearer <token>
    const authHeader = req.headers['authorization'];
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      throw new UnauthorizedException(
        'Token d\'authentification manquant. Utilisez Authorization: Bearer <token>.',
      );
    }

    const token     = authHeader.slice(7); // supprimer "Bearer "
    const secretKey = this.config.get<string>('JWT_SECRET_KEY');

    if (!secretKey) {
      this.logger.error('JWT_SECRET_KEY manquant dans gateway/.env');
      throw new UnauthorizedException('Configuration JWT manquante.');
    }

    try {
      const payload = jwt.verify(token, secretKey) as jwt.JwtPayload;

      // Vérifier le type — un Refresh Token ne doit jamais être accepté ici
      if (payload['type'] !== 'access') {
        throw new UnauthorizedException(
          'Type de token invalide. Utilisez un Access Token.',
        );
      }

      // Attacher les infos utilisateur à la requête pour le RolesGuard
      (req as any).user = {
        userId: payload['sub'],
        email:  payload['email'],
        role:   payload['role'],
      };

      return true;
    } catch (err) {
      if (err instanceof UnauthorizedException) {
        throw err;
      }
      if (err instanceof jwt.TokenExpiredError) {
        throw new UnauthorizedException('Access Token expiré.');
      }
      if (err instanceof jwt.JsonWebTokenError) {
        throw new UnauthorizedException('Access Token invalide ou mal signé.');
      }
      throw new UnauthorizedException('Erreur d\'authentification.');
    }
  }
}
