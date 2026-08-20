import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  // bodyParser: false — le proxy gère lui-même le body brut
  // pour éviter la double-sérialisation JSON lors du forwarding
  const app = await NestFactory.create(AppModule, { bodyParser: false });

  // Activer express raw/json pour avoir accès au body brut dans req.body
  const expressApp = app.getHttpAdapter().getInstance();
  expressApp.use(require('express').json({ limit: '10mb' }));
  expressApp.use(require('express').urlencoded({ extended: true, limit: '10mb' }));

  // Servir les fichiers uploads statiques partagés (/app/uploads)
  const path = require('path');
  const fs = require('fs');
  const uploadsDir = '/app/uploads';
  if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
  }
  expressApp.use('/uploads', require('express').static(uploadsDir));

  const port = process.env.PORT ?? 3000;
  await app.listen(port);
  console.log(`Gateway is running on http://localhost:${port}`);
}
bootstrap();
