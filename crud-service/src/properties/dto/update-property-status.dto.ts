import { IsIn, IsNotEmpty, IsOptional, IsString } from 'class-validator';

export class UpdatePropertyStatusDto {
  @IsString()
  @IsNotEmpty()
  @IsIn(['accepted', 'rejected', 'pending', 'inactive'])
  status: 'accepted' | 'rejected' | 'pending' | 'inactive';

  @IsOptional()
  @IsString()
  rejectionReason?: string;
}
