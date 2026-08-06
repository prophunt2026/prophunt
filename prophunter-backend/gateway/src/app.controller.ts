import { All, Controller, Get, Logger, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AppService } from './app.service';
import { ProxyService } from './proxy/proxy.service';

@Controller('v1')
export class AppController {
  private readonly logger = new Logger(AppController.name);

  constructor(
    private readonly appService: AppService,
    private readonly proxyService: ProxyService,
  ) {}


  // GET /v1 
  @Get()
  getHello(): string {
    return this.appService.getHello();
  }

  // ── AI Service ────────────────────────────────────────────────────────────

  /*
   * Examples:
   *   GET  /v1/service-ia/health
   *   POST /v1/service-ia/scraping/tayara
   */
  @All('service-ia/*path')
  async proxyToAiService(
    @Req() req: Request,
    @Res() res: Response,
  ): Promise<void> {
    this.logger.log(`Routing to AI Service: ${req.method} ${req.path}`);
    await this.proxyService.proxyRequest(req, res, this.url('AI_SERVICE_URL'));
  }

  // ── CRUD Service ──────────────────────────────────────────────────────────

  /**
   * Examples:
   *   GET  /v1/crud/health
   *   GET  /v1/crud/properties
  */
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
