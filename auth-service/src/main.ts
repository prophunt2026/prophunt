import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Global validation pipe — transform + validate all DTOs
  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,
      whitelist: true,           // strip unknown fields (prevents role injection)
      forbidNonWhitelisted: false,
    }),
  );

  const port = process.env.PORT ?? 3003;
  await app.listen(port);
  console.log(`[AuthService] Running on http://localhost:${port}`);
}
bootstrap();
