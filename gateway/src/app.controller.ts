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

import { AppService }      from './app.service';
import { ProxyService }    from './proxy/proxy.service';
import { JwtAdminGuard }   from './guards/jwt-admin.guard';

@Controller('v1')
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

  // ── Auth Service — PUBLIC ─────────────────────────────────────────────────
  // No guard — signup, signin, refresh are public.
  //
  // URL mapping (buildTargetUrl strips /v1 only for auth):
  //   /v1/auth/signup  → http://localhost:3003/auth/signup  ✓
  //   /v1/auth/signin  → http://localhost:3003/auth/signin  ✓
  //   /v1/auth/refresh → http://localhost:3003/auth/refresh ✓
  @All('auth/*path')
  async proxyToAuthService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to Auth Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AUTH_SERVICE_URL'));
  }

  // ── AI Service — ADMIN ONLY ───────────────────────────────────────────────
  // JwtAdminGuard verifies:
  //   1. Authorization: Bearer <token> header present
  //   2. JWT signature valid + not expired
  //   3. token type === 'access'  (refresh tokens rejected → 401)
  //   4. role === 'ADMIN'         (USER → 403 Forbidden)
  //
  // URL mapping:
  //   /v1/service-ia/scraping/tecnocasa → http://localhost:3001/scraping/tecnocasa ✓
  //   /v1/service-ia/health             → http://localhost:3001/health             ✓
  @All('service-ia/*path')
  @UseGuards(JwtAdminGuard)
  async proxyToAiService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to AI Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AI_SERVICE_URL'));
  }

  // ── CRUD Service — PUBLIC (for now) ──────────────────────────────────────
  // Add JwtAdminGuard or a JwtAuthGuard here later when CRUD auth is needed.
  //
  // URL mapping:
  //   /v1/crud/properties → http://localhost:3002/properties ✓
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
      this.logger.error(`Missing env var: ${envVar}. Add it to gateway/.env.`);
      throw new Error(`[Gateway] Missing env var: ${envVar}`);
    }
    return value;
  }
}
