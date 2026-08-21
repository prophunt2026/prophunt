import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Query,
} from '@nestjs/common';
import { PropertiesService, PaginatedResult } from './properties.service';
import { UpdatePropertyStatusDto } from './dto/update-property-status.dto';
import { PropertyDocument } from './schemas/property.schema';

@Controller('admin/properties')
export class AdminPropertiesController {
  constructor(private readonly propertiesService: PropertiesService) {}

  /**
   * GET /admin/properties
   * Query params: page, limit, status ('pending'|'accepted'|'rejected'), scraping ('true'|'false'), site
   */
  @Get()
  findAll(
    @Query('page') page?: number,
    @Query('limit') limit?: number,
    @Query('status') status?: string,
    @Query('scraping') scraping?: string,
    @Query('site') site?: string,
    @Query('startDate') startDate?: string,
    @Query('endDate') endDate?: string,
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.propertiesService.adminFindAll({
      page,
      limit,
      status,
      scraping,
      site,
      startDate,
      endDate,
    });
  }

  /**
   * PATCH /admin/properties/:id/status
   * Accepts or Rejects user property submissions.
   */
  @Patch(':id/status')
  updateStatus(
    @Param('id') id: string,
    @Body() dto: UpdatePropertyStatusDto,
  ): Promise<PropertyDocument> {
    return this.propertiesService.adminUpdateStatus(id, dto.status);
  }

  /**
   * PATCH /admin/properties/:id
   * Allows admin to update any field in a property.
   */
  @Patch(':id')
  update(
    @Param('id') id: string,
    @Body() updateData: any,
  ): Promise<PropertyDocument> {
    return this.propertiesService.adminUpdateProperty(id, updateData);
  }

  /**
   * DELETE /admin/properties/:id
   * Admin can delete any property from DB.
   */
  @Delete(':id')
  @HttpCode(HttpStatus.OK)
  delete(@Param('id') id: string): Promise<{ message: string }> {
    return this.propertiesService.adminDeleteProperty(id);
  }
}
