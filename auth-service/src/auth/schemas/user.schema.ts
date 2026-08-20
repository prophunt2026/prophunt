import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';

export type UserDocument = HydratedDocument<User>;

export enum UserRole {
  USER  = 'USER',
  ADMIN = 'ADMIN',
}

@Schema({ timestamps: true, collection: 'users' })
export class User {
  @Prop({ required: true, unique: true, lowercase: true, trim: true })
  email: string;

  @Prop({ required: true })
  password_hash: string;

  @Prop({ required: true, enum: UserRole, default: UserRole.USER })
  role: UserRole;

  // ─── Champs Profil ─────────────────────────────────────────────────────────

  /** Nom complet de l'utilisateur (ex: "Mohamed Ben Ali") */
  @Prop({ type: String, default: null, trim: true })
  nom: string | null;

  /** Numéro de téléphone de l'utilisateur */
  @Prop({ type: String, default: null, trim: true })
  telephone: string | null;

  /**
   * URL ou chemin de l'image de profil uploadée.
   * Stockée dans le volume Docker /app/uploads/avatars/<user_id>.<ext>
   */
  @Prop({ type: String, default: null })
  avatar: string | null;

  /** Compte actif ou désactivé (true par défaut) */
  @Prop({ type: Boolean, default: true })
  isActive: boolean;
}

export const UserSchema = SchemaFactory.createForClass(User);

