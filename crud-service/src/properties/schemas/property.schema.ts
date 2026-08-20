import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { Document, HydratedDocument, Schema as MongooseSchema, Types } from 'mongoose';

export type PropertyDocument = HydratedDocument<Property>;

// ─── Listing ────────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Listing {
  @Prop({ type: String, default: null }) id_source: string | null;
  @Prop({ type: String, index: true, default: null }) id_universel: string | null;
  @Prop({ type: String, default: null }) url_source: string | null;
  @Prop({ type: String, default: null }) url_canonique: string | null;
  @Prop({ type: String, default: null }) date_scraping: string | null;
  @Prop({ type: String, default: null }) date_publication: string | null;
  @Prop({ type: String, default: null }) date_maj: string | null;
  @Prop({ type: String, default: null }) statut: string | null;
  @Prop({ type: String, default: null }) langue: string | null;
}
export const ListingSchema = SchemaFactory.createForClass(Listing);

// ─── Transaction ─────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Transaction {
  @Prop({ type: String, default: null }) type: string | null;
  @Prop({ type: Number, index: true, default: null }) prix: number | null;
  @Prop({ type: String, default: null }) devise: string | null;
  @Prop({ type: Boolean, default: null }) prix_negociable: boolean | null;
  @Prop({ type: Number, default: null }) prix_m2: number | null;
  @Prop({ type: Number, default: null }) loyer_mensuel: number | null;
  @Prop({ type: Number, default: null }) charges_mensuelles: number | null;
  @Prop({ type: Number, default: null }) caution: number | null;
  @Prop({ type: Number, default: null }) frais_agence: number | null;
  @Prop({ type: String, default: null }) disponibilite: string | null;
  @Prop({ type: String, default: null }) disponibilite_date: string | null;
}
export const TransactionSchema = SchemaFactory.createForClass(Transaction);

// ─── Bien ────────────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Bien {
  @Prop({ type: String, index: true, default: null }) type: string | null;
  @Prop({ type: String, default: null }) sous_type: string | null;
  @Prop({ type: String, default: null }) usage: string | null;
  @Prop({ type: Number, default: null }) superficie_totale: number | null;
  @Prop({ type: Number, default: null }) superficie_habitable: number | null;
  @Prop({ type: Number, default: null }) superficie_terrain: number | null;
  @Prop({ type: Number, default: null }) nombre_pieces: number | null;
  @Prop({ type: Number, default: null }) nombre_chambres: number | null;
  @Prop({ type: Number, default: null }) nombre_salles_bain: number | null;
  @Prop({ type: Number, default: null }) nombre_salles_eau: number | null;
  @Prop({ type: Number, default: null }) nombre_etages_total: number | null;
  @Prop({ type: String, default: null }) etage: string | null;
  @Prop({ type: Boolean, default: null }) dernier_etage: boolean | null;
  @Prop({ type: Number, default: null }) annee_construction: number | null;
  @Prop({ type: String, default: null }) etat_general: string | null;
  @Prop({ type: String, default: null }) standing: string | null;
  @Prop({ type: Boolean, default: null }) meuble: boolean | null;
  @Prop({ type: String, default: null }) orientation: string | null;
  @Prop({ type: String, default: null }) vue: string | null;
}
export const BienSchema = SchemaFactory.createForClass(Bien);

// ─── Coordonnees ─────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Coordonnees {
  @Prop({ type: Number, default: null }) latitude: number | null;
  @Prop({ type: Number, default: null }) longitude: number | null;
}
export const CoordonneesSchema = SchemaFactory.createForClass(Coordonnees);

// ─── Proximite ───────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Proximite {
  /** some sources use 'categorie', others use 'type' */
  @Prop({ type: String, default: null }) categorie: string | null;
  @Prop({ type: String, default: null }) type: string | null;
  @Prop({ type: String, default: null }) nom: string | null;
  @Prop({ type: Number, default: null }) distance_m: number | null;
}
export const ProximiteSchema = SchemaFactory.createForClass(Proximite);

// ─── Localisation ────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Localisation {
  @Prop({ type: String, default: null }) pays: string | null;
  @Prop({ type: String, default: null }) pays_code: string | null;
  @Prop({ type: String, default: null }) gouvernorat: string | null;
  @Prop({ type: String, default: null }) delegation: string | null;
  @Prop({ type: String, index: true, default: null }) ville: string | null;
  @Prop({ type: String, default: null }) localite: string | null;
  @Prop({ type: String, default: null }) quartier: string | null;
  @Prop({ type: String, default: null }) adresse: string | null;
  @Prop({ type: String, default: null }) code_postal: string | null;
  @Prop({ type: [ProximiteSchema], default: [] }) proximites: Proximite[];
  @Prop({ type: CoordonneesSchema, default: () => ({}) }) coordonnees: Coordonnees;
  @Prop({ type: String, default: null }) zone: string | null;
}
export const LocalisationSchema = SchemaFactory.createForClass(Localisation);

// ─── Equipements ─────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Equipements {
  @Prop({ type: Boolean, default: null }) climatisation: boolean | null;
  @Prop({ type: Boolean, default: null }) chauffage: boolean | null;
  @Prop({ type: Boolean, default: null }) ascenseur: boolean | null;
  @Prop({ type: Boolean, default: null }) garage: boolean | null;
  @Prop({ type: Number, default: null }) places_parking: number | null;
  @Prop({ type: Boolean, default: null }) parking_exterieur: boolean | null;
  @Prop({ type: Boolean, default: null }) cave: boolean | null;
  @Prop({ type: Boolean, default: null }) terrasse: boolean | null;
  @Prop({ type: Boolean, default: null }) balcon: boolean | null;
  @Prop({ type: Boolean, default: null }) jardin: boolean | null;
  @Prop({ type: Number, default: null }) superficie_jardin: number | null;
  @Prop({ type: Boolean, default: null }) piscine: boolean | null;
  @Prop({ type: Boolean, default: null }) cuisine_equipee: boolean | null;
  @Prop({ type: Boolean, default: null }) cuisine_americaine: boolean | null;
  @Prop({ type: Boolean, default: null }) double_vitrage: boolean | null;
  @Prop({ type: Boolean, default: null }) volets_roulants: boolean | null;
  @Prop({ type: Boolean, default: null }) porte_blindee: boolean | null;
  @Prop({ type: Boolean, default: null }) interphone: boolean | null;
  @Prop({ type: Boolean, default: null }) videophone: boolean | null;
  @Prop({ type: Boolean, default: null }) alarme: boolean | null;
  @Prop({ type: Boolean, default: null }) concierge: boolean | null;
  @Prop({ type: Boolean, default: null }) gardiennage: boolean | null;
  @Prop({ type: Boolean, default: null }) eau_chaude: boolean | null;
  @Prop({ type: Boolean, default: null }) antenne_tv: boolean | null;
  @Prop({ type: Boolean, default: null }) internet: boolean | null;
  @Prop({ type: Boolean, default: null }) adsl: boolean | null;
  @Prop({ type: Boolean, default: null }) fibre_optique: boolean | null;
  @Prop({ type: Boolean, default: null }) cheminee: boolean | null;
  @Prop({ type: Boolean, default: null }) dressing: boolean | null;
  @Prop({ type: Boolean, default: null }) salle_de_sport: boolean | null;
  @Prop({ type: Boolean, default: null }) espace_enfants: boolean | null;
  @Prop({ type: [String], default: [] }) autres: string[];
}
export const EquipementsSchema = SchemaFactory.createForClass(Equipements);

// ─── Description ─────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Description {
  @Prop({ type: String, default: null }) titre: string | null;
  @Prop({ type: String, default: null }) texte: string | null;
  @Prop({ type: String, default: null }) texte_ar: string | null;
  @Prop({ type: [String], default: [] }) points_forts: string[];
  @Prop({ type: String, default: null }) mentions_legales: string | null;
}
export const DescriptionSchema = SchemaFactory.createForClass(Description);

// ─── Photo ───────────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Photo {
  @Prop({ type: String, default: null }) url: string | null;
  @Prop({ type: String, default: null }) url_thumb: string | null;
  @Prop({ type: String, default: null }) legende: string | null;
  @Prop({ type: Number, default: null }) ordre: number | null;
  @Prop({ type: String, default: null }) type: string | null;
}
export const PhotoSchema = SchemaFactory.createForClass(Photo);

// ─── Medias ──────────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Medias {
  @Prop({ type: [PhotoSchema], default: [] }) photos: Photo[];
  @Prop({ type: [MongooseSchema.Types.Mixed], default: [] }) videos: unknown[];
  @Prop({ type: [MongooseSchema.Types.Mixed], default: [] }) plans: unknown[];
  @Prop({ type: String, default: null }) visite_virtuelle: string | null;
  @Prop({ type: Number, default: null }) nombre_photos: number | null;
}
export const MediasSchema = SchemaFactory.createForClass(Medias);

// ─── Contact ─────────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class Contact {
  @Prop({ type: String, default: null }) type_vendeur: string | null;
  @Prop({ type: String, default: null }) nom_vendeur: string | null;
  @Prop({ type: String, default: null }) nom_agence: string | null;
  @Prop({ type: [String], default: [] }) telephone: string[];
  @Prop({ type: String, default: null }) whatsapp: string | null;
  @Prop({ type: String, default: null }) email: string | null;
  @Prop({ type: String, default: null }) site_web: string | null;
  @Prop({ type: String, default: null }) logo_agence: string | null;
  @Prop({ type: String, default: null }) photo_agence: string | null;
  @Prop({ type: String, default: null }) url_profil: string | null;
  @Prop({ type: Number, default: null }) annonces_vendeur: number | null;
  @Prop({ type: String, default: null }) membre_depuis: string | null;
  @Prop({ type: Boolean, default: null }) verifie: boolean | null;
}
export const ContactSchema = SchemaFactory.createForClass(Contact);

// ─── MetadonnesScraping ──────────────────────────────────────────────────────

@Schema({ _id: false })
export class MetadonnesScraping {
  @Prop({ type: String, index: true, default: null }) source: string | null;
  @Prop({ type: MongooseSchema.Types.Mixed, default: {} }) selecteur_html: Record<string, unknown>;
  @Prop({ type: String, default: null }) methode: string | null;
  @Prop({ type: String, default: null }) statut_scraping: string | null;
  @Prop({ type: [String], default: [] }) erreurs: string[];
  @Prop({ type: Number, default: null }) temps_scraping_ms: number | null;
  @Prop({ type: String, default: null }) user_agent: string | null;
  @Prop({ type: String, default: null }) proxy_utilise: string | null;
  @Prop({ type: Boolean, default: null }) cache: boolean | null;
}
export const MetadonnesScrapingSchema = SchemaFactory.createForClass(MetadonnesScraping);

// ─── ScoringIA ───────────────────────────────────────────────────────────────

@Schema({ _id: false })
export class ScoringIA {
  @Prop({ type: Number, default: null }) prix_estime_marche: number | null;
  @Prop({ type: Number, default: null }) decote_pourcentage: number | null;
  @Prop({ type: Number, default: null }) score_opportunite: number | null;
  @Prop({ type: Number, default: null }) confiance_estimation: number | null;
  @Prop({ type: String, default: null }) tendance_quartier: string | null;
  @Prop({ type: Number, default: null }) rentabilite_locative: number | null;
  @Prop({ type: String, default: null }) delai_vente_estime: string | null;
  @Prop({ type: [MongooseSchema.Types.Mixed], default: [] }) alertes: unknown[];
}
export const ScoringIASchema = SchemaFactory.createForClass(ScoringIA);

// ─── DonneesBrutes ───────────────────────────────────────────────────────────

@Schema({ _id: false })
export class DonneesBrutes {
  @Prop({ type: MongooseSchema.Types.Mixed, default: null }) json_ld: unknown;
  @Prop({ type: String, default: null }) html_snippet: string | null;
}
export const DonneesBrutesSchema = SchemaFactory.createForClass(DonneesBrutes);

// ─── Property (root document) ────────────────────────────────────────────────

@Schema({
  collection: 'properties',
  timestamps: true,
  versionKey: false,
})
export class Property extends Document {
  /** Schema version from the scraper (e.g. "2.0.0") */
  @Prop({ type: String, default: null }) schema_version: string | null;
  @Prop({ type: String, default: null }) schema_name: string | null;

  @Prop({ type: ListingSchema, default: () => ({}) }) listing: Listing;
  @Prop({ type: TransactionSchema, default: () => ({}) }) transaction: Transaction;
  @Prop({ type: BienSchema, default: () => ({}) }) bien: Bien;
  @Prop({ type: LocalisationSchema, default: () => ({}) }) localisation: Localisation;
  @Prop({ type: EquipementsSchema, default: () => ({}) }) equipements: Equipements;
  @Prop({ type: DescriptionSchema, default: () => ({}) }) description: Description;
  @Prop({ type: MediasSchema, default: () => ({}) }) medias: Medias;
  @Prop({ type: ContactSchema, default: () => ({}) }) contact: Contact;
  @Prop({ type: MetadonnesScrapingSchema, default: () => ({}) }) metadonnees_scraping: MetadonnesScraping;
  @Prop({ type: ScoringIASchema, default: () => ({}) }) scoring_ia: ScoringIA;
  @Prop({ type: DonneesBrutesSchema, default: () => ({}) }) donnees_brutes: DonneesBrutes;

  // ─── Champs Utilisateur & Modération ───────────────────────────────────────
  @Prop({ type: Boolean, default: true, index: true })
  scraping: boolean;

  @Prop({ type: MongooseSchema.Types.ObjectId, ref: 'User', default: null, index: true })
  addedBy: Types.ObjectId | null;

  @Prop({
    type: String,
    enum: ['pending', 'accepted', 'rejected', 'inactive'],
    default: null,
    index: true,
  })
  status: 'pending' | 'accepted' | 'rejected' | 'inactive' | null;
}

export const PropertySchema = SchemaFactory.createForClass(Property);

// ─── Indexes ─────────────────────────────────────────────────────────────────

PropertySchema.index({ 'listing.id_universel': 1 }, { unique: true, sparse: true });
PropertySchema.index({ 'metadonnees_scraping.source': 1 });
PropertySchema.index({ 'localisation.ville': 1 });
PropertySchema.index({ 'bien.type': 1 });
PropertySchema.index({ 'transaction.prix': 1 });
// compound index useful for search + filter combos
PropertySchema.index({ 'bien.type': 1, 'localisation.ville': 1, 'transaction.prix': 1 });
