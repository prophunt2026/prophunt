import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';

import { AppController } from './app.controller';
import { AppService } from './app.service';
import { ProxyModule } from './proxy/proxy.module';
import { AuthModule } from './auth/auth.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,   // ConfigService disponible dans JwtGuard et partout
    }),
    ProxyModule,
    AuthModule,
  ],
  controllers: [AppController],
  providers:   [AppService],
})
export class AppModule {}
