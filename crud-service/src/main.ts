import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import * as express from 'express';
import * as fs from 'fs';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  app.enableCors({
    origin: '*',
    methods: 'GET,HEAD,PUT,PATCH,POST,DELETE,OPTIONS',
    credentials: true,
  });

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

  // Servir les fichiers uploads statiques (/app/uploads)
  const expressApp = app.getHttpAdapter().getInstance();
  const uploadsDir = '/app/uploads';
  if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
  }
  expressApp.use('/uploads', express.static(uploadsDir));

  const port = process.env.PORT ?? 3002;
  await app.listen(port);
  console.log(`CRUD Service is running on http://localhost:${port}`);
}
bootstrap();
