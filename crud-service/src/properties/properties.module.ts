import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { PropertiesController } from './properties.controller';
import { AdminPropertiesController } from './admin-properties.controller';
import { PropertiesService } from './properties.service';
import { Property, PropertySchema } from './schemas/property.schema';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: Property.name, schema: PropertySchema },
    ]),
  ],
  controllers: [PropertiesController, AdminPropertiesController],
  providers: [PropertiesService],
  exports: [PropertiesService],
})
export class PropertiesModule {}
