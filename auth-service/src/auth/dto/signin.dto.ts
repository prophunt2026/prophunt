import { IsEmail, IsString, IsNotEmpty } from 'class-validator';

/** POST /auth/signin */
export class SigninDto {
  @IsEmail({}, { message: 'Invalid email address.' })
  email: string;

  @IsString()
  @IsNotEmpty()
  password: string;
}
