import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  Headers,
  HttpCode,
  HttpStatus,
  Patch,
  Post,
  UnauthorizedException,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import { Express } from 'express';
import * as fs from 'fs';
import * as path from 'path';

import { AuthService } from './auth.service';
import { SignupDto } from './dto/signup.dto';
import { SigninDto } from './dto/signin.dto';
import { RefreshDto } from './dto/refresh.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  // ─── Profile Routes (declared before or along public routes) ───────────────

  /** GET /auth/profile — returns profile of logged-in user */
  @Get('profile')
  getProfile(@Headers('x-user-id') userId: string) {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.authService.getProfile(userId);
  }

  /** PATCH /auth/profile — updates profile fields */
  @Patch('profile')
  updateProfile(
    @Headers('x-user-id') userId: string,
    @Body() dto: UpdateProfileDto,
  ) {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.authService.updateProfile(userId, dto);
  }

  /** DELETE /auth/profile — deactivates user profile */
  @Delete('profile')
  deleteProfile(@Headers('x-user-id') userId: string) {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    return this.authService.deleteProfile(userId);
  }

  /** POST /auth/profile/avatar — uploads and sets user profile avatar */
  @Post('profile/avatar')
  @UseInterceptors(
    FileInterceptor('avatar', {
      storage: diskStorage({
        destination: (req, file, cb) => {
          const uploadPath = '/app/uploads/avatars';
          if (!fs.existsSync(uploadPath)) {
            fs.mkdirSync(uploadPath, { recursive: true });
          }
          cb(null, uploadPath);
        },
        filename: (req, file, cb) => {
          const userId = (req.headers['x-user-id'] as string) || 'unknown';
          const ext = path.extname(file.originalname).toLowerCase() || '.jpg';
          cb(null, `${userId}_${Date.now()}${ext}`);
        },
      }),
      limits: { fileSize: 5 * 1024 * 1024 }, // 5 MB max
      fileFilter: (req, file, cb) => {
        if (!file.mimetype.match(/\/(jpg|jpeg|png|webp)$/)) {
          return cb(new BadRequestException('Format d\'image non supporté (jpg, jpeg, png, webp uniquement).'), false);
        }
        cb(null, true);
      },
    }),
  )
  uploadAvatar(
    @Headers('x-user-id') userId: string,
    @UploadedFile() file: Express.Multer.File,
  ) {
    if (!userId) throw new UnauthorizedException('Non authentifié.');
    if (!file) throw new BadRequestException('Aucun fichier image fourni.');

    const avatarUrl = `/uploads/avatars/${file.filename}`;
    return this.authService.updateAvatar(userId, avatarUrl);
  }

  // ─── Public Auth Routes ───────────────────────────────────────────────────

  /** POST /auth/signup — creates a USER account (role always USER) */
  @Post('signup')
  @HttpCode(HttpStatus.CREATED)
  signup(@Body() dto: SignupDto) {
    return this.authService.signup(dto);
  }

  /** POST /auth/signin — returns access_token + refresh_token */
  @Post('signin')
  @HttpCode(HttpStatus.OK)
  signin(@Body() dto: SigninDto) {
    return this.authService.signin(dto);
  }

  /** POST /auth/refresh — rotates refresh token, returns new pair */
  @Post('refresh')
  @HttpCode(HttpStatus.OK)
  refresh(@Body() dto: RefreshDto) {
    return this.authService.refresh(dto);
  }
}

