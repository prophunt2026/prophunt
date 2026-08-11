import {
  ConflictException,
  Injectable,
  OnModuleInit,
  UnauthorizedException,
  InternalServerErrorException,
  Logger,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { ConfigService } from '@nestjs/config';
import { Model } from 'mongoose';
import * as bcrypt from 'bcrypt';
import * as jwt from 'jsonwebtoken';
import { v4 as uuidv4 } from 'uuid';

import { User, UserDocument, UserRole } from './schemas/user.schema';
import { RefreshToken, RefreshTokenDocument } from './schemas/refresh-token.schema';
import { SignupDto } from './dto/signup.dto';
import { SigninDto } from './dto/signin.dto';
import { RefreshDto } from './dto/refresh.dto';

const BCRYPT_ROUNDS = 12;
const AUTH_ERROR    = 'Email ou mot de passe incorrect.';

@Injectable()
export class AuthService implements OnModuleInit {
  private readonly logger = new Logger(AuthService.name);

  constructor(
    @InjectModel(User.name)         private userModel:         Model<UserDocument>,
    @InjectModel(RefreshToken.name) private refreshTokenModel: Model<RefreshTokenDocument>,
    private readonly config: ConfigService,
  ) {}

  // ── Startup: create ADMIN if none exists ───────────────────────────────────

  async onModuleInit() {
    await this.createAdminIfNeeded();
  }

  private async createAdminIfNeeded(): Promise<void> {
    const adminEmail    = this.config.get<string>('ADMIN_EMAIL', '').trim().toLowerCase();
    const adminPassword = this.config.get<string>('ADMIN_PASSWORD', '').trim();

    if (!adminEmail || !adminPassword) {
      this.logger.warn('[Startup] ADMIN_EMAIL or ADMIN_PASSWORD not set — skipping admin creation.');
      return;
    }

    const exists = await this.userModel.findOne({ role: UserRole.ADMIN });
    if (exists) {
      this.logger.log('[Startup] ADMIN already exists — no creation needed.');
      return;
    }

    const password_hash = await bcrypt.hash(adminPassword, BCRYPT_ROUNDS);
    await this.userModel.create({
      email:         adminEmail,
      password_hash,
      role:          UserRole.ADMIN,
    });
    this.logger.log(`[Startup] ADMIN created: ${adminEmail}`);
  }

  // ── SIGNUP ─────────────────────────────────────────────────────────────────

  async signup(dto: SignupDto) {
    const email = dto.email.toLowerCase().trim();

    const existing = await this.userModel.findOne({ email });
    if (existing) {
      throw new ConflictException(`Un compte existe déjà avec l'adresse : ${email}`);
    }

    const password_hash = await bcrypt.hash(dto.password, BCRYPT_ROUNDS);

    try {
      const user = await this.userModel.create({
        email,
        password_hash,
        role: UserRole.USER,   // always USER — never from client
      });

      return {
        id:         user._id.toString(),
        email:      user.email,
        role:       user.role,
        created_at: (user as any).createdAt?.toISOString() ?? new Date().toISOString(),
      };
    } catch (err: any) {
      // Mongoose duplicate key error (code 11000)
      if (err.code === 11000) {
        throw new ConflictException(`Un compte existe déjà avec l'adresse : ${email}`);
      }
      throw new InternalServerErrorException('Erreur interne lors de la création du compte.');
    }
  }

  // ── SIGNIN ─────────────────────────────────────────────────────────────────

  async signin(dto: SigninDto) {
    const email = dto.email.toLowerCase().trim();
    const user  = await this.userModel.findOne({ email });

    // Generic error — never reveal which field is wrong
    if (!user) {
      throw new UnauthorizedException(AUTH_ERROR);
    }

    const passwordOk = await bcrypt.compare(dto.password, user.password_hash);
    if (!passwordOk) {
      throw new UnauthorizedException(AUTH_ERROR);
    }

    const userId = user._id.toString();
    const role   = user.role;   // role from MongoDB — never from client

    const { accessToken, expiresIn } = this.createAccessToken(userId, email, role);
    const { refreshToken, expiresAt } = this.createRefreshToken(userId);

    // Persist refresh token
    await this.refreshTokenModel.create({
      token:      refreshToken,
      user_id:    userId,
      expires_at: expiresAt,
      is_revoked: false,
    });

    return {
      access_token:  accessToken,
      refresh_token: refreshToken,
      token_type:    'bearer',
      expires_in:    expiresIn,
    };
  }

  // ── REFRESH (with rotation) ────────────────────────────────────────────────

  async refresh(dto: RefreshDto) {
    const invalid = new UnauthorizedException('Refresh token invalide ou expiré.');

    // 1+2 — Decode JWT + verify type=refresh
    let payload: any;
    try {
      payload = jwt.verify(dto.refresh_token, this.jwtSecret());
    } catch {
      throw invalid;
    }

    if (payload.type !== 'refresh' || !payload.sub) {
      throw invalid;
    }

    // 3 — Check in DB: not revoked, not expired
    const stored = await this.refreshTokenModel.findOne({
      token:      dto.refresh_token,
      is_revoked: false,
      expires_at: { $gt: new Date() },
    });
    if (!stored) throw invalid;

    // 4 — Revoke old token (rotation)
    await this.refreshTokenModel.updateOne(
      { token: dto.refresh_token },
      { $set: { is_revoked: true } },
    );

    // 5 — Reload user (fresh role)
    const user = await this.userModel.findById(payload.sub);
    if (!user) throw invalid;

    // 6 — New tokens
    const { accessToken, expiresIn } = this.createAccessToken(
      user._id.toString(), user.email, user.role,
    );
    const { refreshToken: newRt, expiresAt: newExp } = this.createRefreshToken(user._id.toString());

    // 7 — Persist new refresh token
    await this.refreshTokenModel.create({
      token:      newRt,
      user_id:    user._id.toString(),
      expires_at: newExp,
      is_revoked: false,
    });

    return {
      access_token:  accessToken,
      refresh_token: newRt,
      token_type:    'bearer',
      expires_in:    expiresIn,
    };
  }

  // ── JWT helpers ────────────────────────────────────────────────────────────

  private jwtSecret(): string {
    const s = this.config.get<string>('JWT_SECRET');
    if (!s) throw new Error('JWT_SECRET missing in .env');
    return s;
  }

  private createAccessToken(userId: string, email: string, role: string) {
    const raw     = this.config.get<string>('JWT_ACCESS_EXPIRES_IN', '30m');
    // Parse "30m" → 30 minutes. Support plain numbers too.
    const minutes = raw.endsWith('m') ? parseInt(raw, 10) : parseInt(raw, 10) || 30;
    const expiresIn = minutes * 60;

    const accessToken = jwt.sign(
      { sub: userId, email, role, type: 'access' },
      this.jwtSecret(),
      { expiresIn: `${minutes}m` },
    );
    return { accessToken, expiresIn };
  }

  private createRefreshToken(userId: string) {
    const days = parseInt(
      this.config.get<string>('JWT_REFRESH_EXPIRES_DAYS', '7'), 10,
    ) || 7;

    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + days);

    const refreshToken = jwt.sign(
      { sub: userId, type: 'refresh', jti: uuidv4() },
      this.jwtSecret(),
      { expiresIn: `${days}d` },
    );
    return { refreshToken, expiresAt };
  }
}
