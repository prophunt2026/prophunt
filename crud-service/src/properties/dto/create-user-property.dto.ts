import {
  IsString,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsBoolean,
  IsArray,
  ValidateNested,
} from 'class-validator';
import { Type, Transform } from 'class-transformer';

export class PhotoInputDto {
  @IsString()
  @IsNotEmpty()
  url: string;

  @IsOptional()
  @IsString()
  url_thumb?: string;

  @IsOptional()
  @IsString()
  legende?: string;

  @IsOptional()
  @IsNumber()
  ordre?: number;
}

export class CreateUserPropertyDto {
  /** Titre de l'annonce */
  @IsString()
  @IsNotEmpty({ message: 'Le titre est obligatoire.' })
  titre: string;

  /** Description détaillée */
  @IsOptional()
  @IsString()
  texte?: string;

  /** Type de transaction (ex: 'Vente', 'Location', 'Location vacances') */
  @IsString()
  @IsNotEmpty({ message: 'Le type de transaction est obligatoire.' })
  type_transaction: string;

  /** Prix en DT */
  @IsNumber({}, { message: 'Le prix doit être un nombre valide.' })
  @IsNotEmpty({ message: 'Le prix est obligatoire.' })
  prix: number;

  @IsOptional()
  @IsBoolean()
  prix_negociable?: boolean;

  /** Type de bien (ex: 'Appartement', 'Villa', 'Terrain', 'Bureau') */
  @IsString()
  @IsNotEmpty({ message: 'Le type de bien est obligatoire.' })
  type_bien: string;

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
  @IsString()
  @IsNotEmpty({ message: 'La ville est obligatoire.' })
  ville: string;

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
