import {
  CanActivate,
  ExecutionContext,
  Injectable,
  Logger,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as jwt from 'jsonwebtoken';
import type { Request } from 'express';

/**
 * JwtAuthGuard — checks validity of Access Token for any logged-in user (USER or ADMIN).
 * Injects `x-user-id`, `x-user-email`, `x-user-role` into request headers.
 */
@Injectable()
export class JwtAuthGuard implements CanActivate {
  private readonly logger = new Logger(JwtAuthGuard.name);

  constructor(private readonly config: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();

    // ── 1. Extract Bearer token ──────────────────────────────────────────────
    const authHeader = req.headers['authorization'];
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      throw new UnauthorizedException(
        'Access token required. Use Authorization: Bearer <token>.',
      );
    }

    const token = authHeader.slice(7);

    // ── 2. Verify JWT ────────────────────────────────────────────────────────
    const secret = this.config.get<string>('JWT_SECRET');
    if (!secret) {
      this.logger.error('JWT_SECRET missing in gateway configuration');
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

    // ── 3. Verify token type ─────────────────────────────────────────────────
    if (payload.type !== 'access') {
      throw new UnauthorizedException(
        'Invalid token type. Use an access token, not a refresh token.',
      );
    }

    // ── 4. Forward user info to downstream services via headers ──────────────
    req.headers['x-user-id'] = payload.sub || payload.userId || payload.id;
    req.headers['x-user-email'] = payload.email;
    req.headers['x-user-role'] = payload.role;

    return true;
  }
}
