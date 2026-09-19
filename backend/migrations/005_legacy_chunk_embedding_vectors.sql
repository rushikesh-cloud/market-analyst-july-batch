-- Older installations created embeddings as JSON before pgvector ingestion.
-- Preserve existing vectors and represent JSON null as SQL NULL.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'document_chunks'
          AND column_name = 'embedding' AND data_type IN ('json', 'jsonb')
    ) THEN
        ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)
        USING CASE WHEN embedding::text = 'null' THEN NULL
                   ELSE embedding::text::vector(1536) END;
    END IF;
END $$;

