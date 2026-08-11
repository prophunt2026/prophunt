import {
  All,
  Controller,
  Get,
  Logger,
  Req,
  Res,
  UseGuards,
} from '@nestjs/common';
import type { Request, Response } from 'express';

import { AppService } from './app.service';
import { ProxyService } from './proxy/proxy.service';
import { JwtGuard } from './auth/jwt.guard';
import { RolesGuard } from './auth/roles.guard';

@Controller('v1')
@UseGuards(JwtGuard, RolesGuard)   // appliqué sur TOUS les handlers de ce contrôleur
export class AppController {
  private readonly logger = new Logger(AppController.name);

  constructor(
    private readonly appService: AppService,
    private readonly proxyService: ProxyService,
  ) {}

  // ── GET /v1 ───────────────────────────────────────────────────────────────
  @Get()
  getHello(): string {
    return this.appService.getHello();
  }

  // ── Auth Service ──────────────────────────────────────────────────────────
  //
  // PUBLIC — signup, signin, refresh ne nécessitent pas de token.
  // La vérification du niveau PUBLIC est faite dans JwtGuard via route-config.ts.
  //
  // Routing :
  //   POST /v1/auth/signup  → auth-service:3003/auth/signup
  //   POST /v1/auth/signin  → auth-service:3003/auth/signin
  //   POST /v1/auth/refresh → auth-service:3003/auth/refresh
  //
  // buildTargetUrl strip /v1/<prefix> :
  //   /v1/auth/signup → strip /v1/auth → /signup
  //   Mais auth-service expose /auth/signup, pas /signup.
  //   On passe donc l'URL de base avec /auth déjà inclus.

  @All('auth/*path')
  async proxyToAuthService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to Auth Service: ${req.method} ${req.path}`);
    // buildTargetUrl strip /v1/<prefix> du path :
    //   /v1/auth/signup → strip /v1/auth → /signup
    // auth-service expose /auth/signup, donc on ajoute /auth dans la baseUrl :
    //   baseUrl = http://localhost:3003/auth
    //   downstream path = /signup
    //   → http://localhost:3003/auth/signup ✓
    await this.proxyService.proxyRequest(
      req,
      res,
      `${this.url('AUTH_SERVICE_URL')}/auth`,
    );
  }

  // ── AI Service ────────────────────────────────────────────────────────────
  //
  // ADMIN — /v1/service-ia/scraping/* requiert role ADMIN.
  // Vérifié automatiquement par JwtGuard + RolesGuard via route-config.ts.
  //
  // Routing :
  //   POST /v1/service-ia/scraping/tecnocasa → ai-service:3001/scraping/tecnocasa
  //   GET  /v1/service-ia/health             → ai-service:3001/health

  @All('service-ia/*path')
  async proxyToAiService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to AI Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AI_SERVICE_URL'));
  }

  // ── CRUD Service ──────────────────────────────────────────────────────────
  //
  // AUTHENTICATED — requiert un JWT valide (USER ou ADMIN).
  // Vérifié automatiquement par JwtGuard via route-config.ts.

  @All('crud/*path')
  async proxyToCrudService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private url(envVar: string): string {
    const value = process.env[envVar];
    if (!value) {
      this.logger.error(
        `Missing required environment variable: ${envVar}. Add it to gateway/.env.`,
      );
      throw new Error(
        `[Gateway] Missing required environment variable: ${envVar}`,
      );
    }
    return value;
  }
}
