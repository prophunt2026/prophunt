import {
  Controller,
  Get,
  Param,
  Query,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { PropertiesService, PaginatedResult, StatsResult } from './properties.service';
import { PaginationDto } from './dto/pagination.dto';
import { SearchDto } from './dto/search.dto';
import { LatestDto } from './dto/latest.dto';
import { PropertyDocument } from './schemas/property.schema';

@Controller('properties')
export class PropertiesController {
  constructor(private readonly propertiesService: PropertiesService) {}

  // ── Health ─────────────────────────────────────────────────────────────────

  /**
   * GET /properties/health
   * Module health check — kept from Phase 3b.
   */
  @Get('health')
  @HttpCode(HttpStatus.OK)
  getHealth(): object {
    return { status: 'ok', module: 'properties' };
  }

  // ── Static routes MUST come before /:id ───────────────────────────────────

  /**
   * GET /properties/sources
   * Returns the list of distinct scraping sources present in the DB.
   */
  @Get('sources')
  getSources(): Promise<string[]> {
    return this.propertiesService.getSources();
  }

  /**
   * GET /properties/stats
   * Returns aggregate stats: totals, by-source, by-ville, and price range.
   */
  @Get('stats')
  getStats(): Promise<StatsResult> {
    return this.propertiesService.getStats();
  }

  /**
   * GET /properties/latest?limit=20
   * Returns the most recently scraped listings.
   */
  @Get('latest')
  getLatest(@Query() dto: LatestDto): Promise<PropertyDocument[]> {
    return this.propertiesService.getLatest(dto);
  }

  /**
   * GET /properties/search?source=&ville=&prixMax=…
   * Dynamic multi-criteria search. All params are optional and combinable.
   */
  @Get('search')
  search(@Query() dto: SearchDto): Promise<PropertyDocument[]> {
    return this.propertiesService.search(dto);
  }

  /**
   * GET /properties/source/:source?page=1&limit=10
   * GET /properties/site/:site?page=1&limit=10
   * Returns paginated listings from a specific scraping source (10 per page by default).
   */
  @Get('source/:source')
  findBySource(
    @Param('source') source: string,
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.findBySource(source, dto);
  }

  @Get('site/:site')
  findBySite(
    @Param('site') site: string,
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.findBySource(site, dto);
  }


  // ── Parameterised routes ───────────────────────────────────────────────────

  /**
   * GET /properties?page=1&limit=20
   * Returns paginated listings sorted by most recent first.
   */
  @Get()
  findAll(
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.findAll(dto);
  }

  /**
   * GET /properties/:id
   * Returns a single listing by its MongoDB ObjectId.
   * Returns 404 if not found, 400 if id is not a valid ObjectId.
   */
  @Get(':id')
  findOne(@Param('id') id: string): Promise<PropertyDocument> {
    return this.propertiesService.findOne(id);
  }
}
