import {
  Injectable,
  NotFoundException,
  BadRequestException,
  Logger,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model, isValidObjectId, FilterQuery, Types } from 'mongoose';
import * as fs from 'fs';
import * as path from 'path';
import { Property, PropertyDocument } from './schemas/property.schema';
import { PaginationDto } from './dto/pagination.dto';
import { SearchDto } from './dto/search.dto';
import { LatestDto } from './dto/latest.dto';
import { CreateUserPropertyDto } from './dto/create-user-property.dto';
import { UpdateUserPropertyDto } from './dto/update-user-property.dto';

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
  private readonly logger = new Logger(PropertiesService.name);

  constructor(
    @InjectModel(Property.name)
    private readonly propertyModel: Model<PropertyDocument>,
  ) { }

  // ── 1. GET /properties ─────────────────────────────────────────────────────

  async findAll(dto: PaginationDto): Promise<PaginatedResult<PropertyDocument>> {
    const { page, limit } = dto;
    const siteFilter = dto.site ?? dto.source;
    const skip = (page - 1) * limit;

    const filter: FilterQuery<PropertyDocument> = {
      $or: [{ scraping: true }, { status: 'accepted' }],
    };

    const [data, total] = await Promise.all([
      this.propertyModel
        .find(filter)
        .sort({ createdAt: -1, 'listing.date_scraping': -1 })
        .skip(skip)
        .limit(limit)
        .lean()
        .exec(),
      this.propertyModel.countDocuments(filter).exec(),
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
      .distinct('metadonnees_scraping.source', {
        $or: [{ scraping: true }, { status: 'accepted' }],
      })
      .exec();
    return (sources as string[]).filter(Boolean).sort();
  }

  // ── 3. GET /properties/stats ───────────────────────────────────────────────

  async getStats(): Promise<StatsResult> {
    const baseMatch = { $or: [{ scraping: true }, { status: 'accepted' }] };
    const [total, sourceAgg, villeAgg, prixAgg] = await Promise.all([
      this.propertyModel.countDocuments(baseMatch).exec(),

      this.propertyModel.aggregate<{ _id: string; count: number }>([
        { $match: { ...baseMatch, 'metadonnees_scraping.source': { $ne: null } } },
        { $group: { _id: '$metadonnees_scraping.source', count: { $sum: 1 } } },
        { $sort: { count: -1 } },
      ]),

      this.propertyModel.aggregate<{ _id: string; count: number }>([
        { $match: { ...baseMatch, 'localisation.ville': { $ne: null } } },
        { $group: { _id: '$localisation.ville', count: { $sum: 1 } } },
        { $sort: { count: -1 } },
        { $limit: 20 },
      ]),

      this.propertyModel.aggregate<{
        avg: number | null;
        min: number | null;
        max: number | null;
      }>([
        { $match: { ...baseMatch, 'transaction.prix': { $ne: null, $gt: 0 } } },
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
    const filter: FilterQuery<PropertyDocument> = {
      $or: [{ scraping: true }, { status: 'accepted' }],
    };
    const docs = await this.propertyModel
      .find(filter)
      .sort({ 'listing.date_scraping': -1 })
      .limit(dto.limit)
      .lean()
      .exec();
    return docs as unknown as PropertyDocument[];
  }

  // ── 5. GET /properties/search ──────────────────────────────────────────────

  async search(dto: SearchDto): Promise<PropertyDocument[]> {
    const filter: FilterQuery<PropertyDocument> = {
      $or: [{ scraping: true }, { status: 'accepted' }],
    };

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
      .limit(20)
      .lean()
      .exec();

    return docs as unknown as PropertyDocument[];
  }


  // ── 6. GET /properties/source/:source ─────────────────────────────────────

  async findBySource(
    source: string,
    dto: PaginationDto = new PaginationDto(),
  ): Promise<PaginatedResult<PropertyDocument>> {
    return this.findAll({ ...dto, site: source });
  }


  // ── 7. GET /properties/:id ─────────────────────────────────────────────────

  async findOne(id: string): Promise<PropertyDocument> {
    if (!isValidObjectId(id)) {
      throw new BadRequestException(`"${id}" n'est pas un ObjectId valide`);
    }

    const doc = await this.propertyModel
      .findOne({
        _id: id,
        $or: [{ scraping: true }, { status: 'accepted' }],
      })
      .lean()
      .exec();

    if (!doc) {
      throw new NotFoundException(`Annonce introuvable : ${id}`);
    }

    return doc as unknown as PropertyDocument;
  }

  // ── 8. USER CRUD: POST /properties ────────────────────────────────────────

  async createUserProperty(
    userId: string,
    dto: CreateUserPropertyDto,
  ): Promise<PropertyDocument> {
    if (!isValidObjectId(userId)) {
      throw new BadRequestException(`ID utilisateur invalide : ${userId}`);
    }

    const nowIso = new Date().toISOString();

    const newProperty = new this.propertyModel({
      scraping: false,
      addedBy: new Types.ObjectId(userId),
      status: 'pending',
      listing: {
        id_source: null,
        id_universel: `user_${userId}_${Date.now()}`,
        url_source: null,
        url_canonique: null,
        date_scraping: nowIso,
        date_publication: nowIso,
        date_maj: nowIso,
        statut: 'disponible',
        langue: 'fr',
      },
      transaction: {
        type: dto.type_transaction,
        prix: dto.prix,
        devise: 'TND',
        prix_negociable: dto.prix_negociable ?? false,
      },
      bien: {
        type: dto.type_bien,
        superficie_totale: dto.superficie_totale ?? null,
        nombre_pieces: dto.nombre_pieces ?? null,
        nombre_chambres: dto.nombre_chambres ?? null,
        nombre_salles_bain: dto.nombre_salles_bain ?? null,
        etage: dto.etage ?? null,
        meuble: dto.meuble ?? null,
      },
      localisation: {
        pays: 'Tunisie',
        pays_code: 'TN',
        ville: dto.ville,
        delegation: dto.delegation ?? null,
        adresse: dto.adresse ?? null,
        code_postal: dto.code_postal ?? null,
      },
      description: {
        titre: dto.titre,
        texte: dto.texte ?? null,
      },
      medias: {
        photos: dto.photos ?? [],
        nombre_photos: dto.photos?.length ?? 0,
      },
      contact: {
        type_vendeur: 'Particulier',
        nom_vendeur: dto.nom_contact ?? null,
        telephone: dto.telephone ?? [],
        email: dto.email_contact ?? null,
      },
      metadonnees_scraping: {
        source: 'user_submission',
        methode: 'manual_entry',
        statut_scraping: 'success',
      },
    });

    const saved = await newProperty.save();
    return saved as unknown as PropertyDocument;
  }

  // ── 9. USER CRUD: GET /properties/my-properties ───────────────────────────

  async findMyProperties(
    userId: string,
    dto: PaginationDto = new PaginationDto(),
  ): Promise<PaginatedResult<PropertyDocument>> {
    if (!isValidObjectId(userId)) {
      throw new BadRequestException(`ID utilisateur invalide : ${userId}`);
    }

    const { page, limit } = dto;
    const skip = (page - 1) * limit;

    const filter: FilterQuery<PropertyDocument> = {
      addedBy: new Types.ObjectId(userId),
      status: { $ne: 'inactive' },
    };

    const [total, data] = await Promise.all([
      this.propertyModel.countDocuments(filter),
      this.propertyModel
        .find(filter)
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(limit)
        .lean()
        .exec(),
    ]);

    return {
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
      data: data as unknown as PropertyDocument[],
    };
  }

  // ── 10. USER CRUD: PATCH /properties/my-properties/:id ────────────────────

  async updateMyProperty(
    userId: string,
    propertyId: string,
    dto: UpdateUserPropertyDto,
  ): Promise<PropertyDocument> {
    if (!isValidObjectId(propertyId)) {
      throw new BadRequestException(`ID propriété invalide : ${propertyId}`);
    }

    const prop = await this.propertyModel.findOne({
      _id: propertyId,
      addedBy: new Types.ObjectId(userId),
    });

    if (!prop) {
      throw new NotFoundException(
        `Annonce introuvable ou vous n'êtes pas autorisé à la modifier.`,
      );
    }

    // Update mapped fields
    if (dto.titre !== undefined) prop.description.titre = dto.titre;
    if (dto.texte !== undefined) prop.description.texte = dto.texte;
    if (dto.type_transaction !== undefined) prop.transaction.type = dto.type_transaction;
    if (dto.prix !== undefined) prop.transaction.prix = dto.prix;
    if (dto.prix_negociable !== undefined) prop.transaction.prix_negociable = dto.prix_negociable;
    if (dto.type_bien !== undefined) prop.bien.type = dto.type_bien;
    if (dto.superficie_totale !== undefined) prop.bien.superficie_totale = dto.superficie_totale;
    if (dto.nombre_pieces !== undefined) prop.bien.nombre_pieces = dto.nombre_pieces;
    if (dto.nombre_chambres !== undefined) prop.bien.nombre_chambres = dto.nombre_chambres;
    if (dto.nombre_salles_bain !== undefined) prop.bien.nombre_salles_bain = dto.nombre_salles_bain;
    if (dto.etage !== undefined) prop.bien.etage = dto.etage;
    if (dto.meuble !== undefined) prop.bien.meuble = dto.meuble;
    if (dto.ville !== undefined) prop.localisation.ville = dto.ville;
    if (dto.delegation !== undefined) prop.localisation.delegation = dto.delegation;
    if (dto.adresse !== undefined) prop.localisation.adresse = dto.adresse;
    if (dto.code_postal !== undefined) prop.localisation.code_postal = dto.code_postal;
    if (dto.nom_contact !== undefined) prop.contact.nom_vendeur = dto.nom_contact;
    if (dto.telephone !== undefined) prop.contact.telephone = dto.telephone;
    if (dto.email_contact !== undefined) prop.contact.email = dto.email_contact;
    if (dto.photos !== undefined) {
      prop.medias.photos = dto.photos as any;
      prop.medias.nombre_photos = dto.photos.length;
    }

    // Modification puts status back to 'pending' for re-validation
    prop.status = 'pending';
    prop.listing.date_maj = new Date().toISOString();

    const saved = await prop.save();
    return saved as unknown as PropertyDocument;
  }

  // ── 11. USER CRUD: DELETE /properties/my-properties/:id ───────────────────

  async deleteMyProperty(userId: string, propertyId: string): Promise<{ message: string }> {
    if (!isValidObjectId(propertyId)) {
      throw new BadRequestException(`ID propriété invalide : ${propertyId}`);
    }

    const res = await this.propertyModel.deleteOne({
      _id: propertyId,
      addedBy: new Types.ObjectId(userId),
    });

    if (res.deletedCount === 0) {
      throw new NotFoundException(
        `Annonce introuvable ou vous n'êtes pas autorisé à la supprimer.`,
      );
    }

    return { message: 'Annonce supprimée avec succès.' };
  }

  // ── 11b. INTERNAL: HARD DELETE ALL PROPERTIES & PHOTOS OF A USER ─────────

  async deleteUserProperties(userId: string): Promise<{ deletedCount: number }> {
    if (!isValidObjectId(userId)) {
      throw new BadRequestException(`ID utilisateur invalide : ${userId}`);
    }

    // 1. Trouver les propriétés pour supprimer leurs photos locales sur le disque
    const userProperties = await this.propertyModel.find({
      addedBy: new Types.ObjectId(userId),
    });

    for (const prop of userProperties) {
      if (prop.medias?.photos && Array.isArray(prop.medias.photos)) {
        for (const photoItem of prop.medias.photos) {
          try {
            const rawUrl = typeof photoItem === 'string' ? photoItem : (photoItem as any)?.url;
            if (rawUrl && typeof rawUrl === 'string') {
              const filename = rawUrl.split('/').pop();
              if (filename) {
                const photoPath = path.join('/app/uploads/properties', filename);
                if (fs.existsSync(photoPath)) {
                  fs.unlinkSync(photoPath);
                }
              }
            }
          } catch (e) {
            this.logger.warn(`Impossible de supprimer le fichier photo : ${e}`);
          }
        }
      }
    }

    // 2. Supprimer définitivement les annonces de la base de données
    const res = await this.propertyModel.deleteMany({
      addedBy: new Types.ObjectId(userId),
    });

    this.logger.log(`[CascadeDelete] ${res.deletedCount} annonces supprimées pour l'utilisateur ${userId}`);
    return { deletedCount: res.deletedCount };
  }

  async deactivateUserProperties(userId: string): Promise<{ modifiedCount: number }> {
    if (!isValidObjectId(userId)) {
      throw new BadRequestException(`ID utilisateur invalide : ${userId}`);
    }

    const res = await this.propertyModel.updateMany(
      { addedBy: new Types.ObjectId(userId) },
      { $set: { status: 'inactive', 'listing.date_maj': new Date().toISOString() } },
    );

    return { modifiedCount: res.modifiedCount };
  }

  // ── 12. ADMIN CRUD: ALL PROPERTIES WITH FILTERS ───────────────────────────

  async adminFindAll(
    query: {
      page?: number;
      limit?: number;
      status?: string;
      scraping?: string;
      site?: string;
      startDate?: string;
      endDate?: string;
    } = {},
  ): Promise<PaginatedResult<PropertyDocument>> {
    const page = Math.max(1, Number(query.page) || 1);
    const limit = Math.min(100, Math.max(1, Number(query.limit) || 20));
    const skip = (page - 1) * limit;

    const filter: FilterQuery<PropertyDocument> = {};

    if (query.status) {
      filter.status = query.status;
    }
    if (query.scraping !== undefined) {
      filter.scraping = query.scraping === 'true';
    }
    if (query.site) {
      filter['metadonnees_scraping.source'] = query.site;
    }

    if (query.startDate || query.endDate) {
      filter['listing.date_scraping'] = {};
      if (query.startDate) {
        filter['listing.date_scraping'].$gte = query.startDate.length === 10
          ? `${query.startDate}T00:00:00.000Z`
          : query.startDate;
      }
      if (query.endDate) {
        filter['listing.date_scraping'].$lte = query.endDate.length === 10
          ? `${query.endDate}T23:59:59.999Z`
          : query.endDate;
      }
    }

    const [total, data] = await Promise.all([
      this.propertyModel.countDocuments(filter),
      this.propertyModel
        .find(filter)
        .sort({ 'listing.date_scraping': -1, createdAt: -1 })
        .skip(skip)
        .limit(limit)
        .lean()
        .exec(),
    ]);

    return {
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
      data: data as unknown as PropertyDocument[],
    };
  }

  // ── 13. ADMIN CRUD: MODERATE STATUS (ACCEPT / REJECT) ─────────────────────

  async adminUpdateStatus(
    id: string,
    status: 'accepted' | 'rejected' | 'pending' | 'inactive',
  ): Promise<PropertyDocument> {
    if (!isValidObjectId(id)) {
      throw new BadRequestException(`ID invalide : ${id}`);
    }

    const prop = await this.propertyModel.findById(id);
    if (!prop) {
      throw new NotFoundException(`Annonce introuvable : ${id}`);
    }

    prop.status = status;
    prop.listing.date_maj = new Date().toISOString();

    const saved = await prop.save();
    return saved as unknown as PropertyDocument;
  }

  // ── 14. ADMIN CRUD: FULL UPDATE ───────────────────────────────────────────

  async adminUpdateProperty(id: string, updateData: any): Promise<PropertyDocument> {
    if (!isValidObjectId(id)) {
      throw new BadRequestException(`ID invalide : ${id}`);
    }

    const updated = await this.propertyModel
      .findByIdAndUpdate(id, { $set: updateData, 'listing.date_maj': new Date().toISOString() }, { new: true })
      .lean()
      .exec();

    if (!updated) {
      throw new NotFoundException(`Annonce introuvable : ${id}`);
    }

    return updated as unknown as PropertyDocument;
  }

  // ── 15. ADMIN CRUD: DELETE ANY PROPERTY ───────────────────────────────────

  async adminDeleteProperty(id: string): Promise<{ message: string }> {
    if (!isValidObjectId(id)) {
      throw new BadRequestException(`ID invalide : ${id}`);
    }

    const res = await this.propertyModel.findByIdAndDelete(id);
    if (!res) {
      throw new NotFoundException(`Annonce introuvable : ${id}`);
    }

    return { message: `Annonce ${id} supprimée avec succès par l'administrateur.` };
  }
}

