import { IsString, IsNotEmpty } from 'class-validator';

/** POST /auth/refresh */
export class RefreshDto {
  @IsString()
  @IsNotEmpty()
  refresh_token: string;
}
