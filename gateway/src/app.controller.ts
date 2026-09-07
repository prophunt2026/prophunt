import {
  All,
  Controller,
  Get,
  Post,
  Logger,
  Req,
  Res,
  UseGuards,
} from '@nestjs/common';
import type { Request, Response } from 'express';

import { AppService }      from './app.service';
import { ProxyService }    from './proxy/proxy.service';
import { JwtAdminGuard }   from './guards/jwt-admin.guard';
import { JwtAuthGuard }    from './guards/jwt-auth.guard';

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

  // ── 1. AUTH SERVICE: PROFILE (AUTH REQUIRED) ──────────────────────────────
  // Specific static profile routes must precede general /auth/*path
  @All('auth/profile')
  @UseGuards(JwtAuthGuard)
  async proxyAuthProfile(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to Auth Profile: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AUTH_SERVICE_URL'));
  }

  @All('auth/profile/*path')
  @UseGuards(JwtAuthGuard)
  async proxyAuthProfileSub(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to Auth Profile Sub: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AUTH_SERVICE_URL'));
  }

  // ── 2. AUTH SERVICE: PUBLIC (SIGNUP, SIGNIN, REFRESH) ─────────────────────
  @All('auth/*path')
  async proxyToAuthService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to Auth Service (Public): ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AUTH_SERVICE_URL'));
  }

  // ── 3. CRUD SERVICE: ADMIN ONLY (MODERATION & FULL CRUD) ──────────────────
  @All('crud/admin/*path')
  @UseGuards(JwtAdminGuard)
  async proxyCrudAdmin(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Admin: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  // ── 4. CRUD SERVICE: USER MY-PROPERTIES (AUTH REQUIRED) ───────────────────
  @All('crud/properties/my-properties')
  @UseGuards(JwtAuthGuard)
  async proxyCrudMyProperties(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD My-Properties: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  @All('crud/properties/my-properties/*path')
  @UseGuards(JwtAuthGuard)
  async proxyCrudMyPropertiesSub(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD My-Properties Sub: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  // ── 5. CRUD SERVICE: CREATE PROPERTY (AUTH REQUIRED) ─────────────────────

  @Post('crud/properties')
  @UseGuards(JwtAuthGuard)
  async proxyCrudCreateProperty(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Create Property: POST ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  // ── 6. CRUD SERVICE: ADMIN-ONLY METADATA ENDPOINTS ────────────────────────
  // These MUST come before the public catch-all crud/*path
  @All('crud/properties/sources')
  @UseGuards(JwtAdminGuard)
  async proxyCrudSources(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Sources (Admin): ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  @All('crud/properties/stats')
  @UseGuards(JwtAdminGuard)
  async proxyCrudStats(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Stats (Admin): ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  @All('crud/properties/latest')
  @UseGuards(JwtAdminGuard)
  async proxyCrudLatest(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Latest (Admin): ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  // ── 7. CRUD SERVICE: PUBLIC (LISTINGS, SEARCH, DETAILS) ───────────────────
  // Note: site= / startDate= / endDate= filters on /properties are admin-only
  // and must be used via /v1/crud/admin/properties (adminFindAll).
  @All('crud/*path')
  async proxyToCrudService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to CRUD Service (Public): ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('CRUD_SERVICE_URL'));
  }

  // ── 8. AI SERVICE: ADMIN ONLY (SCRAPING) ───────────────────────────────────
  @All('service-ia/*path')
  @UseGuards(JwtAdminGuard)
  async proxyToAiService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to AI Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AI_SERVICE_URL'));
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

