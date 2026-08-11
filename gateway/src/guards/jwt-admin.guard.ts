import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  Logger,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as jwt from 'jsonwebtoken';
import type { Request } from 'express';

/**
 * JwtAdminGuard — protects routes that require an ADMIN JWT.
 *
 * Applied on:  ANY /v1/service-ia/*  (scraping endpoints)
 *
 * Flow:
 *   1. Extract Bearer token from Authorization header.
 *   2. Verify JWT signature + expiration.
 *   3. Verify token type === 'access'  (refresh tokens are rejected).
 *   4. Verify role === 'ADMIN'  → 403 if USER.
 *
 * HTTP responses:
 *   401  →  no token / invalid / expired / wrong type
 *   403  →  valid token but role !== ADMIN
 */
@Injectable()
export class JwtAdminGuard implements CanActivate {
  private readonly logger = new Logger(JwtAdminGuard.name);

  constructor(private readonly config: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();

    // ── 1. Extract token ───────────────────────────────────────────────────
    const authHeader = req.headers['authorization'];
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      throw new UnauthorizedException(
        'Access token required. Use Authorization: Bearer <token>.',
      );
    }

    const token = authHeader.slice(7);

    // ── 2. Verify JWT ──────────────────────────────────────────────────────
    const secret = this.config.get<string>('JWT_SECRET');
    if (!secret) {
      this.logger.error('JWT_SECRET missing in gateway/.env');
      throw new UnauthorizedException('JWT configuration error.');
    }

    let payload: any;
    try {
      payload = jwt.verify(token, secret);
    } catch (err: any) {
      if (err.name === 'TokenExpiredError') {
        throw new UnauthorizedException('Access token expired.');
      }
      throw new UnauthorizedException('Invalid or malformed access token.');
    }

    // ── 3. Verify token type ───────────────────────────────────────────────
    if (payload.type !== 'access') {
      throw new UnauthorizedException(
        'Invalid token type. Use an access token, not a refresh token.',
      );
    }

    // ── 4. Verify role ─────────────────────────────────────────────────────
    if (payload.role !== 'ADMIN') {
      this.logger.warn(
        `Access denied for role=${payload.role} on ${req.method} ${req.path}`,
      );
      throw new ForbiddenException(
        'Access restricted to ADMIN only.',
      );
    }

    return true;
  }
}
