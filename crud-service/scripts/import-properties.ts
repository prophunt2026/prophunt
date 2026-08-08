/**
 * PropHunter TN – Property Import Script
 *
 * Reads all scraped JSON files, validates each listing,
 * detects duplicates via listing.id_universel, and inserts
 * new documents into MongoDB.
 *
 * Usage:  npm run import
 */

import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';
import mongoose, { Schema, model, connect, disconnect } from 'mongoose';

// ─── Load env ────────────────────────────────────────────────────────────────

dotenv.config({ path: path.resolve(__dirname, '../.env') });

const MONGODB_URI =
  process.env.MONGODB_URI ?? 'mongodb://localhost:27017/prophunter';

// ─── Source configuration ────────────────────────────────────────────────────
// Add a new entry here whenever a new scraping source is added.

interface SourceConfig {
  name: string;
  file: string;
}

const SOURCES: SourceConfig[] = [
  {
    name: 'mubawab',
    file: path.resolve(__dirname, '../data/scraped/mubawab_standard.json'),
  },
  {
    name: 'tecnocasa',
    file: path.resolve(__dirname, '../data/scraped/tecnocasa_standard.json'),
  },
  {
    name: 'tayara',
    file: path.resolve(__dirname, '../data/scraped/tayara.json'),
  },
  {
    name: 'tunisie_annonce',
    file: path.resolve(__dirname, '../data/scraped/tunisie_annonce.json'),
  },
  {
    name: 'home_in_tunisia',
    file: path.resolve(__dirname, '../data/scraped/home_in_tunisia_standard.json'),
  },
  {
    name: 'fi_dari',
    file: path.resolve(__dirname, '../data/scraped/fi_dari_standard.json'),
  },
];

// ─── Minimal Mongoose schema (mirrors property.schema.ts) ────────────────────
// We use a permissive Mixed schema here so the script does not depend on
// NestJS decorators, but data is stored in exactly the same collection.

const PropertySchema = new Schema(
  {
    schema_version:      { type: String, default: null },
    schema_name:         { type: String, default: null },
    listing:             { type: Schema.Types.Mixed, default: {} },
    transaction:         { type: Schema.Types.Mixed, default: {} },
    bien:                { type: Schema.Types.Mixed, default: {} },
    localisation:        { type: Schema.Types.Mixed, default: {} },
    equipements:         { type: Schema.Types.Mixed, default: {} },
    description:         { type: Schema.Types.Mixed, default: {} },
    medias:              { type: Schema.Types.Mixed, default: {} },
    contact:             { type: Schema.Types.Mixed, default: {} },
    metadonnees_scraping: { type: Schema.Types.Mixed, default: {} },
    scoring_ia:          { type: Schema.Types.Mixed, default: {} },
    donnees_brutes:      { type: Schema.Types.Mixed, default: null },
  },
  {
    collection: 'properties',
    timestamps: true,
    versionKey: false,
  },
);

// Unique sparse index — same as property.schema.ts
PropertySchema.index(
  { 'listing.id_universel': 1 },
  { unique: true, sparse: true },
);

const PropertyModel = model('Property', PropertySchema);

// ─── Types ───────────────────────────────────────────────────────────────────

interface RawListing {
  id_universel?: string | null;
  [key: string]: unknown;
}

interface RawMetadonnees {
  source?: string | null;
  [key: string]: unknown;
}

interface RawProperty {
  schema_version?: string | null;
  schema_name?: string | null;
  listing?: RawListing;
  metadonnees_scraping?: RawMetadonnees;
  [key: string]: unknown;
}

interface SourceStats {
  name: string;
  total: number;
  inserted: number;
  duplicates: number;
  invalid: number;
  errors: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function readJsonFile(filePath: string): RawProperty[] {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) {
    throw new Error(`Expected JSON array, got ${typeof parsed}`);
  }
  return parsed as RawProperty[];
}

/**
 * If listing.id_universel is null but id_source + source are present,
 * generate a fallback id: "<source>_<id_source>".
 * This handles tayara and tunisie_annonce which the scraper left without a
 * universal ID.
 */
function normalize(doc: RawProperty, sourceName: string): void {
  if (!doc.listing) return;

  const idUniversel = doc.listing.id_universel;
  const idSource    = doc.listing.id_source as string | undefined;
  const source      = doc.metadonnees_scraping?.source ?? sourceName;

  if (!idUniversel && idSource && source) {
    doc.listing.id_universel = `${source}_${idSource}`;
  }
}

function validate(
  doc: RawProperty,
  sourceName: string,
  index: number,
): string | null {
  const idUniversel = doc?.listing?.id_universel;
  const source = doc?.metadonnees_scraping?.source;

  if (!idUniversel) {
    return `[${sourceName}] #${index} — manque listing.id_universel et impossible de le générer (id_source absent)`;
  }
  if (!source) {
    return `[${sourceName}] #${index} (${idUniversel}) — manque metadonnees_scraping.source`;
  }
  return null; // valid
}

// ─── Core import logic ───────────────────────────────────────────────────────

async function importSource(source: SourceConfig): Promise<SourceStats> {
  const stats: SourceStats = {
    name: source.name,
    total: 0,
    inserted: 0,
    duplicates: 0,
    invalid: 0,
    errors: 0,
  };

  console.log(`\n── ${source.name.toUpperCase()} ──`);
  console.log(`   Fichier : ${source.file}`);

  // 1. Read file
  let docs: RawProperty[];
  try {
    docs = readJsonFile(source.file);
  } catch (err) {
    console.error(`   ✖ Impossible de lire le fichier : ${(err as Error).message}`);
    stats.errors++;
    return stats;
  }

  stats.total = docs.length;
  console.log(`   Annonces trouvées : ${stats.total}`);

  // 2. Process each document
  for (let i = 0; i < docs.length; i++) {
    const doc = docs[i];

    // Normalize missing id_universel
    normalize(doc, source.name);

    // Validate
    const validationError = validate(doc, source.name, i);
    if (validationError) {
      console.warn(`   ⚠  INVALIDE — ${validationError}`);
      stats.invalid++;
      continue;
    }

    const idUniversel = doc.listing!.id_universel as string;

    try {
      // Duplicate check
      const existing = await PropertyModel.findOne(
        { 'listing.id_universel': idUniversel },
        { _id: 1 },
      ).lean();

      if (existing) {
        stats.duplicates++;
        continue;
      }

      // Insert
      await PropertyModel.create(doc);
      stats.inserted++;
    } catch (err) {
      console.error(
        `   ✖ Erreur insertion ${idUniversel} : ${(err as Error).message}`,
      );
      stats.errors++;
    }
  }

  console.log(
    `   ✔ Terminé — insérées: ${stats.inserted} | doublons: ${stats.duplicates} | invalides: ${stats.invalid} | erreurs: ${stats.errors}`,
  );

  return stats;
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('╔══════════════════════════════════════════╗');
  console.log('║  PropHunter TN — Import des annonces     ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log(`\nConnexion MongoDB : ${MONGODB_URI}`);

  await connect(MONGODB_URI);
  console.log('✔ MongoDB connecté\n');

  const allStats: SourceStats[] = [];

  for (const source of SOURCES) {
    const stats = await importSource(source);
    allStats.push(stats);
  }

  // ─── Summary ───────────────────────────────────────────────────────────────

  const totalAnalysed  = allStats.reduce((s, r) => s + r.total, 0);
  const totalInserted  = allStats.reduce((s, r) => s + r.inserted, 0);
  const totalDuplicates = allStats.reduce((s, r) => s + r.duplicates, 0);
  const totalInvalid   = allStats.reduce((s, r) => s + r.invalid, 0);
  const totalErrors    = allStats.reduce((s, r) => s + r.errors, 0);

  console.log('\n╔══════════════════════════════════════════╗');
  console.log('║            RÉSUMÉ D\'IMPORT               ║');
  console.log('╠══════════════════════════════════════════╣');
  console.log('║  Sources traitées :                      ║');

  for (const s of allStats) {
    const label = `${s.name} : ${s.total} annonces`.padEnd(40);
    console.log(`║    ${label}║`);
  }

  console.log('╠══════════════════════════════════════════╣');
  console.log(`║  Total analysé    : ${String(totalAnalysed).padEnd(20)}║`);
  console.log(`║  Insérées         : ${String(totalInserted).padEnd(20)}║`);
  console.log(`║  Doublons ignorés : ${String(totalDuplicates).padEnd(20)}║`);
  console.log(`║  Invalides        : ${String(totalInvalid).padEnd(20)}║`);
  console.log(`║  Erreurs          : ${String(totalErrors).padEnd(20)}║`);
  console.log('╚══════════════════════════════════════════╝');

  await disconnect();
  console.log('\n✔ Connexion MongoDB fermée.');

  // Exit with error code if any errors occurred
  if (totalErrors > 0) process.exit(1);
}

main().catch((err: Error) => {
  console.error('\n✖ Erreur fatale :', err.message);
  disconnect().finally(() => process.exit(1));
});
