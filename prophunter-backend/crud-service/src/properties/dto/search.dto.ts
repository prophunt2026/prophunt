import { IsOptional, IsString, IsNumber, Min, IsInt, IsIn } from 'class-validator';
import { Type } from 'class-transformer';

export class SearchDto {
  @IsOptional()
  @IsString()
  source?: string;

  @IsOptional()
  @IsString()
  ville?: string;

  @IsOptional()
  @IsString()
  delegation?: string;

  @IsOptional()
  @IsString()
  type?: string;

  /** Filter by transaction type. Accepted values: 'vente' | 'location' */
  @IsOptional()
  @IsString()
  @IsIn(['vente', 'location'])
  transaction?: 'vente' | 'location';

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  prixMin?: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  prixMax?: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  surfaceMin?: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  surfaceMax?: number;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  nombreChambres?: number;

  @IsOptional()
  @IsString()
  statut?: string;
}
