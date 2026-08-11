import { All, Controller, Get, Logger, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';

import { AppService }   from './app.service';
import { ProxyService } from './proxy/proxy.service';

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

  // ── Auth Service ──────────────────────────────────────────────────────────
  // Routes: /v1/auth/signup → /auth/signup
  //         /v1/auth/signin → /auth/signin
  //         /v1/auth/refresh → /auth/refresh
  //
  // buildTargetUrl strips /v1/<prefix> then appends the rest:
  //   /v1/auth/signup → strip /v1/auth → /auth/signup
  //   baseUrl = http://localhost:3003
  //   → http://localhost:3003/auth/signup ✓
  @All('auth/*path')
  async proxyToAuthService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to Auth Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AUTH_SERVICE_URL'));
  }

  // ── AI Service ────────────────────────────────────────────────────────────
  // Routes: /v1/service-ia/* → AI Service
  @All('service-ia/*path')
  async proxyToAiService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to AI Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AI_SERVICE_URL'));
  }

  // ── CRUD Service ──────────────────────────────────────────────────────────
  // Routes: /v1/crud/* → CRUD Service
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
