import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model, isValidObjectId, FilterQuery } from 'mongoose';
import { Property, PropertyDocument } from './schemas/property.schema';
import { PaginationDto } from './dto/pagination.dto';
import { SearchDto } from './dto/search.dto';
import { LatestDto } from './dto/latest.dto';

// ─── Response shapes ─────────────────────────────────────────────────────────

export interface PaginatedResult<T> {
  data: T[];
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export interface StatsResult {
  total: number;
  bySource: Record<string, number>;
  byVille: Record<string, number>;
  prix: {
    moyenne: number | null;
    minimum: number | null;
    maximum: number | null;
  };
}

// ─── Service ─────────────────────────────────────────────────────────────────

@Injectable()
export class PropertiesService {
  constructor(
    @InjectModel(Property.name)
    private readonly propertyModel: Model<PropertyDocument>,
  ) {}

  // ── 1. GET /properties ─────────────────────────────────────────────────────

  async findAll(dto: PaginationDto): Promise<PaginatedResult<PropertyDocument>> {
    const { page, limit } = dto;
    const skip = (page - 1) * limit;

    const [data, total] = await Promise.all([
      this.propertyModel
        .find()
        .sort({ 'listing.date_scraping': -1 })
        .skip(skip)
        .limit(limit)
        .lean()
        .exec(),
      this.propertyModel.countDocuments().exec(),
    ]);

    return {
      data: data as unknown as PropertyDocument[],
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
    };
  }

  // ── 2. GET /properties/sources ─────────────────────────────────────────────

  async getSources(): Promise<string[]> {
    const sources = await this.propertyModel
      .distinct('metadonnees_scraping.source')
      .exec();
    return (sources as string[]).filter(Boolean).sort();
  }

  // ── 3. GET /properties/stats ───────────────────────────────────────────────

  async getStats(): Promise<StatsResult> {
    const [total, sourceAgg, villeAgg, prixAgg] = await Promise.all([
      this.propertyModel.countDocuments().exec(),

      this.propertyModel.aggregate<{ _id: string; count: number }>([
        { $match: { 'metadonnees_scraping.source': { $ne: null } } },
        { $group: { _id: '$metadonnees_scraping.source', count: { $sum: 1 } } },
        { $sort: { count: -1 } },
      ]),

      this.propertyModel.aggregate<{ _id: string; count: number }>([
        { $match: { 'localisation.ville': { $ne: null } } },
        { $group: { _id: '$localisation.ville', count: { $sum: 1 } } },
        { $sort: { count: -1 } },
        { $limit: 20 },
      ]),

      this.propertyModel.aggregate<{
        avg: number | null;
        min: number | null;
        max: number | null;
      }>([
        { $match: { 'transaction.prix': { $ne: null, $gt: 0 } } },
        {
          $group: {
            _id: null,
            avg: { $avg: '$transaction.prix' },
            min: { $min: '$transaction.prix' },
            max: { $max: '$transaction.prix' },
          },
        },
      ]),
    ]);

    const bySource: Record<string, number> = {};
    for (const s of sourceAgg) bySource[s._id] = s.count;

    const byVille: Record<string, number> = {};
    for (const v of villeAgg) byVille[v._id] = v.count;

    const p = prixAgg[0] ?? { avg: null, min: null, max: null };

    return {
      total,
      bySource,
      byVille,
      prix: {
        moyenne: p.avg !== null ? Math.round(p.avg) : null,
        minimum: p.min ?? null,
        maximum: p.max ?? null,
      },
    };
  }

  // ── 4. GET /properties/latest ──────────────────────────────────────────────

  async getLatest(dto: LatestDto): Promise<PropertyDocument[]> {
    const docs = await this.propertyModel
      .find()
      .sort({ 'listing.date_scraping': -1 })
      .limit(dto.limit)
      .lean()
      .exec();
    return docs as unknown as PropertyDocument[];
  }

  // ── 5. GET /properties/search ──────────────────────────────────────────────

  async search(dto: SearchDto): Promise<PropertyDocument[]> {
    const filter: FilterQuery<PropertyDocument> = {};

    if (dto.source)
      filter['metadonnees_scraping.source'] = dto.source;

    if (dto.ville)
      filter['localisation.ville'] = { $regex: dto.ville, $options: 'i' };

    if (dto.delegation)
      filter['localisation.delegation'] = {
        $regex: dto.delegation,
        $options: 'i',
      };

    if (dto.type)
      filter['bien.type'] = { $regex: dto.type, $options: 'i' };

    if (dto.transaction)
      filter['transaction.type'] = dto.transaction;

    if (dto.statut)
      filter['listing.statut'] = dto.statut;

    if (dto.prixMin !== undefined || dto.prixMax !== undefined) {
      filter['transaction.prix'] = {};
      if (dto.prixMin !== undefined)
        filter['transaction.prix'].$gte = dto.prixMin;
      if (dto.prixMax !== undefined)
        filter['transaction.prix'].$lte = dto.prixMax;
    }

    if (dto.surfaceMin !== undefined || dto.surfaceMax !== undefined) {
      filter['bien.superficie_totale'] = {};
      if (dto.surfaceMin !== undefined)
        filter['bien.superficie_totale'].$gte = dto.surfaceMin;
      if (dto.surfaceMax !== undefined)
        filter['bien.superficie_totale'].$lte = dto.surfaceMax;
    }

    if (dto.nombreChambres !== undefined)
      filter['bien.nombre_chambres'] = dto.nombreChambres;

    const docs = await this.propertyModel
      .find(filter)
      .sort({ 'listing.date_scraping': -1 })
      .limit(100)
      .lean()
      .exec();

    return docs as unknown as PropertyDocument[];
  }

  // ── 6. GET /properties/source/:source ─────────────────────────────────────

  async findBySource(source: string): Promise<PropertyDocument[]> {
    const docs = await this.propertyModel
      .find({ 'metadonnees_scraping.source': source })
      .sort({ 'listing.date_scraping': -1 })
      .lean()
      .exec();
    return docs as unknown as PropertyDocument[];
  }

  // ── 7. GET /properties/:id ─────────────────────────────────────────────────

  async findOne(id: string): Promise<PropertyDocument> {
    if (!isValidObjectId(id)) {
      throw new BadRequestException(`"${id}" n'est pas un ObjectId valide`);
    }

    const doc = await this.propertyModel.findById(id).lean().exec();

    if (!doc) {
      throw new NotFoundException(`Annonce introuvable : ${id}`);
    }

    return doc as unknown as PropertyDocument;
  }
}
