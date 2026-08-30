import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const blog = defineCollection({
	loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
	schema: z.object({
		titulo: z.string(),
		fecha: z.coerce.date(),
		resumen: z.string(),
		autor: z.string().default('OPRC'),
		imagenDestacada: z.string().optional(),
	}),
});

export const collections = { blog };
