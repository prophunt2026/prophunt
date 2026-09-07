import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  Headers,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Post,
  Query,
  UnauthorizedException,
  UploadedFiles,
  UseInterceptors,
} from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import * as fs from 'fs';
import * as path from 'path';

import { PropertiesService, PaginatedResult, StatsResult } from './properties.service';
import { PaginationDto } from './dto/pagination.dto';
import { SearchDto } from './dto/search.dto';
import { LatestDto } from './dto/latest.dto';
import { CreateUserPropertyDto } from './dto/create-user-property.dto';
import { UpdateUserPropertyDto } from './dto/update-user-property.dto';
import { PropertyDocument } from './schemas/property.schema';

const propertyMulterOptions = {
  storage: diskStorage({
    destination: (req, file, cb) => {
      const uploadPath = '/app/uploads/properties';
      if (!fs.existsSync(uploadPath)) {
        fs.mkdirSync(uploadPath, { recursive: true });
      }
      cb(null, uploadPath);
    },
    filename: (req, file, cb) => {
      const userId = (req.headers['x-user-id'] as string) || 'unknown';
      const ext = path.extname(file.originalname).toLowerCase() || '.jpg';
      cb(null, `prop_${userId}_${Date.now()}_${Math.round(Math.random() * 1e6)}${ext}`);
    },
  }),
  limits: { fileSize: 5 * 1024 * 1024 }, // 5 MB max per image
  fileFilter: (req: any, file: any, cb: any) => {
    if (!file.mimetype.match(/\/(jpg|jpeg|png|webp)$/)) {
      return cb(new BadRequestException('Format d\'image non supporté (jpg, jpeg, png, webp uniquement).'), false);
    }
    cb(null, true);
  },
};

@Controller('properties')
export class PropertiesController {
  private readonly baseUrl: string;

  constructor(private readonly propertiesService: PropertiesService) {
    this.baseUrl = process.env.PUBLIC_BASE_URL ?? 'http://localhost:3000';
  }

  // ── Health (Static) ────────────────────────────────────────────────────────
  @Get('health')
  @HttpCode(HttpStatus.OK)
  getHealth(): object {
    return { status: 'ok', module: 'properties' };
  }

  // ── Static routes (MUST come before dynamic /:id) ──────────────────────────

  /**
   * GET /properties/sources
   */
  @Get('sources')
  getSources(): Promise<string[]> {
    return this.propertiesService.getSources();
  }

  /**
   * GET /properties/stats
   */
  @Get('stats')
  getStats(): Promise<StatsResult> {
    return this.propertiesService.getStats();
  }

  /**
   * GET /properties/latest?limit=20
   */
  @Get('latest')
  getLatest(@Query() dto: LatestDto): Promise<PropertyDocument[]> {
    return this.propertiesService.getLatest(dto);
  }

  /**
   * GET /properties/search?source=&ville=&prixMax=…
   */
  @Get('search')
  search(@Query() dto: SearchDto): Promise<PropertyDocument[]> {
    return this.propertiesService.search(dto);
  }

  // ── User Submitted Properties (Static prefix before /:id) ──────────────────

  /**
   * GET /properties/my-properties?page=1&limit=20
   * Retrieves all properties submitted by the authenticated user.
   */
  @Get('my-properties')
  findMyProperties(
    @Headers('x-user-id') userId: string,
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.propertiesService.findMyProperties(userId, dto);
  }

  /**
   * PATCH /properties/my-properties/:id
   * Updates an existing property owned by the authenticated user.
   * Supports both JSON and multipart/form-data (with direct file upload in 'images').
   */
  @Patch('my-properties/:id')
  @UseInterceptors(FilesInterceptor('images', 10, propertyMulterOptions))
  updateMyProperty(
    @Headers('x-user-id') userId: string,
    @Param('id') propertyId: string,
    @Body() dto: UpdateUserPropertyDto,
    @UploadedFiles() files?: Express.Multer.File[],
  ): Promise<PropertyDocument> {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    if (files && files.length > 0) {
      const uploadedPhotos = files.map((file, index) => ({
        url: `${this.baseUrl}/uploads/properties/${file.filename}`,
        legende: file.originalname,
        ordre: index + 1,
      }));
      dto.photos = [...(dto.photos || []), ...uploadedPhotos];
    }
    return this.propertiesService.updateMyProperty(userId, propertyId, dto);
  }

  /**
   * DELETE /properties/my-properties/:id
   * Deletes a property owned by the authenticated user.
   */
  @Delete('my-properties/:id')
  deleteMyProperty(
    @Headers('x-user-id') userId: string,
    @Param('id') propertyId: string,
  ): Promise<{ message: string }> {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.propertiesService.deleteMyProperty(userId, propertyId);
  }

  /**
   * DELETE /properties/internal/user-properties
   * Internal endpoint called when user account is deleted permanently.
   * Hard deletes all user submitted properties and their images.
   */
  @Delete('internal/user-properties')
  deleteUserProperties(
    @Headers('x-user-id') userId: string,
  ): Promise<{ deletedCount: number }> {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.propertiesService.deleteUserProperties(userId);
  }

  /**
   * PATCH /properties/internal/deactivate-user
   * Internal endpoint called when user account is deactivated.
   * Marks all user submitted properties as status='inactive'.
   */
  @Patch('internal/deactivate-user')
  deactivateUserProperties(
    @Headers('x-user-id') userId: string,
  ): Promise<{ modifiedCount: number }> {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.propertiesService.deactivateUserProperties(userId);
  }



  // ── Source / Site Filter Routes ────────────────────────────────────────────

  /**
   * GET /properties/source/:source
   */
  @Get('source/:source')
  findBySource(
    @Param('source') source: string,
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.findBySource(source, dto);
  }

  /**
   * GET /properties/site/:site
   */
  @Get('site/:site')
  findBySite(
    @Param('site') site: string,
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.findBySource(site, dto);
  }

  // ── Root Collection Routes ─────────────────────────────────────────────────

  /**
   * POST /properties
   * Allows authenticated user to submit a property (sets scraping=false, status=pending).
   * Supports both JSON and multipart/form-data (with direct file upload in 'images').
   */
  @Post()
  @HttpCode(HttpStatus.CREATED)
  @UseInterceptors(FilesInterceptor('images', 10, propertyMulterOptions))
  create(
    @Headers('x-user-id') userId: string,
    @Body() dto: CreateUserPropertyDto,
    @UploadedFiles() files?: Express.Multer.File[],
  ): Promise<PropertyDocument> {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    if (files && files.length > 0) {
      const uploadedPhotos = files.map((file, index) => ({
        url: `${this.baseUrl}/uploads/properties/${file.filename}`,
        legende: file.originalname,
        ordre: index + 1,
      }));
      dto.photos = [...(dto.photos || []), ...uploadedPhotos];
    }
    return this.propertiesService.createUserProperty(userId, dto);
  }

  /**
   * GET /properties?page=1&limit=20
   */
  @Get()
  findAll(
    @Query() dto: PaginationDto,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.findAll(dto);
  }

  // ── Parameterised /:id Route (MUST BE AT THE VERY BOTTOM) ──────────────────

  /**
   * GET /properties/:id
   */
  @Get(':id')
  findOne(@Param('id') id: string): Promise<PropertyDocument> {
    return this.propertiesService.findOne(id);
  }
}

