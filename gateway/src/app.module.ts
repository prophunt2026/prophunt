import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';

import { AppController } from './app.controller';
import { AppService }    from './app.service';
import { ProxyModule }   from './proxy/proxy.module';
import { JwtAdminGuard } from './guards/jwt-admin.guard';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    ProxyModule,
  ],
  controllers: [AppController],
  providers: [
    AppService,
    JwtAdminGuard,   // makes ConfigService injectable inside the guard
  ],
})
export class AppModule {}
