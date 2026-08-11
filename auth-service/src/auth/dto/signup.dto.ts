import { IsEmail, IsString, Matches, MinLength, MaxLength } from 'class-validator';

/**
 * POST /auth/signup
 * No role field — client can never choose ADMIN.
 * whitelist: true in ValidationPipe strips any extra fields.
 *
 * Password rules (same as FastAPI version):
 *   - 8–64 characters
 *   - at least 1 uppercase, 1 lowercase, 1 digit, 1 special char
 */
export class SignupDto {
  @IsEmail({}, { message: 'Invalid email address.' })
  email: string;

  @IsString()
  @MinLength(8, { message: 'Password must be at least 8 characters.' })
  @MaxLength(64, { message: 'Password must be at most 64 characters.' })
  @Matches(
    /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+\[\]{};':",./<>?]).{8,64}$/,
    {
      message:
        'Password must contain at least 1 uppercase, 1 lowercase, 1 digit and 1 special character (!@#$%^&*...).',
    },
  )
  password: string;
}
