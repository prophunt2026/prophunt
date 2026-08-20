import mongoose from 'mongoose';
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '../.env') });

const MONGODB_URI =
  process.env.MONGODB_URI || 'mongodb://localhost:27018/prophunter';

async function runMigration() {
  console.log(`[Migration] Connexion à MongoDB : ${MONGODB_URI}...`);
  await mongoose.connect(MONGODB_URI);

  const db = mongoose.connection.db;
  if (!db) {
    throw new Error('[Migration] Impossible d’obtenir la référence à la base de données.');
  }

  console.log('[Migration] Application des valeurs par défaut pour les annonces existantes...');
  const result = await db.collection('properties').updateMany(
    { scraping: { $exists: false } },
    { $set: { scraping: true, addedBy: null, status: null } }
  );

  console.log(`[Migration] Terminé avec succès :`);
  console.log(`  - Documents trouvés sans le champ 'scraping' : ${result.matchedCount}`);
  console.log(`  - Documents mis à jour : ${result.modifiedCount}`);

  await mongoose.disconnect();
  console.log('[Migration] Déconnexion réussie.');
}

runMigration().catch((err) => {
  console.error('[Migration] Erreur lors de la migration :', err);
  process.exit(1);
});
