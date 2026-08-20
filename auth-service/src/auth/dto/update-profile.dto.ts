import { IsOptional, IsString, MinLength } from 'class-validator';

export class UpdateProfileDto {
  /** Nom complet */
  @IsOptional()
  @IsString()
  @MinLength(2, { message: 'Le nom doit contenir au moins 2 caractères.' })
  nom?: string;

  /** Numéro de téléphone */
  @IsOptional()
  @IsString()
  telephone?: string;
}
