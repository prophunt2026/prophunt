import {
  Injectable,
  Logger,
  BadGatewayException,
  ServiceUnavailableException,
  HttpException,
} from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import type { Request, Response } from 'express';
import { AxiosError, AxiosRequestConfig, RawAxiosRequestHeaders } from 'axios';

@Injectable()
export class ProxyService {
  private readonly logger = new Logger(ProxyService.name);

  // Headers that must never be forwarded between proxies (RFC 2616 §13.5.1)
  // Also strip content-length — it changes when we re-serialize the body,
  // causing downstream services to abort with "request.aborted" (received != expected)
  private readonly HOP_BY_HOP = new Set([
    'host',
    'connection',
    'keep-alive',
    'transfer-encoding',
    'te',
    'trailer',
    'proxy-authorization',
    'proxy-authenticate',
    'upgrade',
    'content-length',   // recalculated by axios after body re-serialization
  ]);

  constructor(private readonly httpService: HttpService) {}

  /**
   * Generic reverse-proxy method.
   *
   * Receives the raw Express request + response and the base URL of the
   * target microservice, then:
   *   1. Strips the /v1/<prefix> segment from the path to build the final URL
   *   2. Forwards method, headers, query params and body unchanged
   *   3. Pipes the downstream status, headers and body back to the client
   *
   * The Gateway never reads or modifies the payload.
   *
   * URL reconstruction example:
   *   baseUrl  = http://localhost:3001
   *   req.path = /v1/service-ia/scraping/tayara
   *   target   = http://localhost:3001/scraping/tayara
   *
   * @param req      Incoming Express request
   * @param res      Outgoing Express response
   * @param baseUrl  Base URL of the target microservice (from env)
   */
  async proxyRequest(
    req: Request,
    res: Response,
    baseUrl: string,
  ): Promise<void> {
    const targetUrl = this.buildTargetUrl(baseUrl, req.path);

    const method = req.method.toLowerCase() as
      | 'get' | 'post' | 'put' | 'patch' | 'delete' | 'head' | 'options';

    // ── Build forwarded headers ────────────────────────────────────────────
    const forwardedHeaders: RawAxiosRequestHeaders = {};
    for (const [key, value] of Object.entries(req.headers)) {
      if (!this.HOP_BY_HOP.has(key.toLowerCase())) {
        forwardedHeaders[key] = value as string;
      }
    }

    // ── Axios config ───────────────────────────────────────────────────────
    // Sérialiser le body en JSON string si c'est un objet pour éviter
    // que Axios l'envoie comme "[object Object]"
    let requestData: unknown = undefined;
    if (['post', 'put', 'patch'].includes(method)) {
      const body = req.body;
      if (body !== undefined && body !== null) {
        requestData = typeof body === 'object' ? JSON.stringify(body) : body;
        // S'assurer que Content-Type est bien application/json
        if (!forwardedHeaders['content-type']) {
          forwardedHeaders['content-type'] = 'application/json';
        }
      }
    }

    const config: AxiosRequestConfig = {
      method,
      url: targetUrl,
      headers: forwardedHeaders,
      params: req.query,
      data: requestData,
      responseType: 'arraybuffer',  // never touch the payload
      validateStatus: () => true,   // forward 4xx/5xx as-is
      timeout: 30000,               // 30s max — couvre bcrypt (rounds=12 ~2-3s) + réseau
    };

    try {
      const downstream = await firstValueFrom(
        this.httpService.request(config),
      );

      // ── Forward response ─────────────────────────────────────────────────
      res.status(downstream.status);

      for (const [key, value] of Object.entries(downstream.headers)) {
        if (!this.HOP_BY_HOP.has(key.toLowerCase()) && value !== undefined) {
          res.setHeader(key, value as string | string[]);
        }
      }

      res.send(downstream.data);
    } catch (err) {
      const axiosErr = err as AxiosError;

      if (axiosErr.response) {
        const status = axiosErr.response.status;
        this.logger.error(
          `Downstream error ${status} for ${method.toUpperCase()} ${targetUrl}`,
        );
        throw new HttpException(
          axiosErr.response.data ?? 'Downstream service error',
          status,
        );
      }

      if (axiosErr.code === 'ECONNREFUSED' || axiosErr.code === 'ENOTFOUND') {
        this.logger.error(
          `Service unreachable [${axiosErr.code}]: ${targetUrl}`,
        );
        throw new ServiceUnavailableException(
          `Le microservice est indisponible (${targetUrl}). Veuillez réessayer plus tard.`,
        );
      }

      if (axiosErr.code === 'ECONNABORTED' || axiosErr.message?.includes('timeout')) {
        this.logger.error(`Timeout proxying to ${targetUrl}`);
        throw new ServiceUnavailableException(
          `Le microservice ne répond pas (timeout): ${targetUrl}`,
        );
      }

      this.logger.error(
        `Network error proxying to ${targetUrl}: ${axiosErr.message}`,
      );
      throw new BadGatewayException(
        `Erreur de communication avec le microservice: ${axiosErr.message}`,
      );
    }
  }

  // ── Private helpers ──────────────────────────────────────────────────────

  /**
   * Strips the /v1/<prefix> segment and appends the remaining path
   * to the microservice base URL.
   *
   * Examples:
   *   buildTargetUrl('http://localhost:3001', '/v1/service-ia/health')
   *     → 'http://localhost:3001/health'
   *
   *   buildTargetUrl('http://localhost:3002', '/v1/crud/properties')
   *     → 'http://localhost:3002/properties'
   *
   *   buildTargetUrl('http://localhost:3001', '/v1/service-ia/scraping/tayara')
   *     → 'http://localhost:3001/scraping/tayara'
   */
  private buildTargetUrl(baseUrl: string, requestPath: string): string {
    // Auth service: strip only /v1 — keep /auth prefix
    //   /v1/auth/signup  → /auth/signup → http://localhost:3003/auth/signup ✓
    if (requestPath.startsWith('/v1/auth/')) {
      const downstream = requestPath.replace(/^\/v1/, '') || '/';
      return `${baseUrl}${downstream}`;
    }

    // All other services: strip /v1/<prefix>
    //   /v1/service-ia/scraping/tecnocasa → /scraping/tecnocasa
    //   /v1/crud/properties               → /properties
    const downstream = requestPath.replace(/^\/v1\/[^/]+/, '') || '/';
    return `${baseUrl}${downstream}`;
  }
}
