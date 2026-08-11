import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';

export type RefreshTokenDocument = HydratedDocument<RefreshToken>;

@Schema({ collection: 'refresh_tokens' })
export class RefreshToken {
  @Prop({ required: true, unique: true })
  token: string;

  @Prop({ required: true })
  user_id: string;

  @Prop({ required: true })
  expires_at: Date;

  @Prop({ default: false })
  is_revoked: boolean;

  @Prop({ default: () => new Date() })
  created_at: Date;
}

export const RefreshTokenSchema = SchemaFactory.createForClass(RefreshToken);

// TTL index — MongoDB auto-deletes expired tokens
RefreshTokenSchema.index({ expires_at: 1 }, { expireAfterSeconds: 0 });

// Fast lookup by token
RefreshTokenSchema.index({ token: 1 }, { unique: true });

// Revoke all tokens for a user
RefreshTokenSchema.index({ user_id: 1 });
