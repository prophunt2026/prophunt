import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import * as express from 'express';
import * as fs from 'fs';

async function bootstrap() {
  // bodyParser: false — le proxy gère lui-même le body brut
  // pour éviter la double-sérialisation JSON lors du forwarding
  const app = await NestFactory.create(AppModule, { bodyParser: false });

  // Activer CORS pour le frontend
  app.enableCors({
    origin: '*',
    methods: 'GET,HEAD,PUT,PATCH,POST,DELETE,OPTIONS',
    credentials: true,
  });

  // Activer express raw/json pour avoir accès au body brut dans req.body
  const expressApp = app.getHttpAdapter().getInstance();
  expressApp.use(express.json({ limit: '10mb' }));
  expressApp.use(express.urlencoded({ extended: true, limit: '10mb' }));

  // Servir les fichiers uploads statiques partagés (/app/uploads)
  const uploadsDir = '/app/uploads';
  if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
  }
  expressApp.use('/uploads', express.static(uploadsDir));

  const port = process.env.PORT ?? 3000;
  await app.listen(port);
  console.log(`Gateway is running on http://localhost:${port}`);
}
bootstrap();
