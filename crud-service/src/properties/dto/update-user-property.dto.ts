import {
  IsString,
  IsNumber,
  IsOptional,
  IsBoolean,
  IsArray,
  ValidateNested,
} from 'class-validator';
import { Type, Transform } from 'class-transformer';
import { PhotoInputDto } from './create-user-property.dto';

export class UpdateUserPropertyDto {
  /** Titre de l'annonce */
  @IsOptional()
  @IsString()
  titre?: string;

  /** Description détaillée */
  @IsOptional()
  @IsString()
  texte?: string;

  /** Type de transaction (ex: 'Vente', 'Location') */
  @IsOptional()
  @IsString()
  type_transaction?: string;

  /** Prix en DT */
  @IsOptional()
  @IsNumber()
  prix?: number;

  @IsOptional()
  @IsBoolean()
  prix_negociable?: boolean;

  /** Type de bien (ex: 'Appartement', 'Villa') */
  @IsOptional()
  @IsString()
  type_bien?: string;

  @IsOptional()
  @IsNumber()
  superficie_totale?: number;

  @IsOptional()
  @IsNumber()
  nombre_pieces?: number;

  @IsOptional()
  @IsNumber()
  nombre_chambres?: number;

  @IsOptional()
  @IsNumber()
  nombre_salles_bain?: number;

  @IsOptional()
  @IsString()
  etage?: string;

  @IsOptional()
  @IsBoolean()
  meuble?: boolean;

  /** Localisation */
  @IsOptional()
  @IsString()
  ville?: string;

  @IsOptional()
  @IsString()
  delegation?: string;

  @IsOptional()
  @IsString()
  adresse?: string;

  @IsOptional()
  @IsString()
  code_postal?: string;

  /** Contact */
  @IsOptional()
  @IsString()
  nom_contact?: string;

  @IsOptional()
  @Transform(({ value }) => (Array.isArray(value) ? value : typeof value === 'string' ? [value] : value))
  @IsArray()
  @IsString({ each: true })
  telephone?: string[];

  @IsOptional()
  @IsString()
  email_contact?: string;

  /** Photos */
  @IsOptional()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => PhotoInputDto)
  photos?: PhotoInputDto[];
}
