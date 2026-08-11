import { Module } from '@nestjs/common';
import { JwtGuard } from './jwt.guard';
import { RolesGuard } from './roles.guard';

/**
 * AuthModule — Fournit JwtGuard et RolesGuard au reste du Gateway.
 *
 * Ces gardes sont injectés dans AppController via APP_GUARD (global)
 * ou directement sur les handlers concernés.
 *
 * Architecture choisie : gardes appliqués globalement via APP_GUARD
 * dans AppModule pour couvrir automatiquement toutes les routes futures.
 * La table route-config.ts contrôle le comportement route par route.
 */
@Module({
  providers: [JwtGuard, RolesGuard],
  exports:   [JwtGuard, RolesGuard],
})
export class AuthModule {}
