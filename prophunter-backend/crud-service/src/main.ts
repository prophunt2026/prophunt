import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Global validation pipe — transforms query params and validates DTOs
  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,           // convert query string values to declared types
      transformOptions: {
        enableImplicitConversion: true,
      },
      whitelist: true,           // strip unknown properties
      forbidNonWhitelisted: false,
    }),
  );

  const port = process.env.PORT ?? 3002;
  await app.listen(port);
  console.log(`CRUD Service is running on http://localhost:${port}`);
}
bootstrap();
