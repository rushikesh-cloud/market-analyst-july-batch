import type { Chunk } from './document-types'

export default function ChunkCard({ chunk }: { chunk: Chunk }) {
  return (
    <article className="chunk">
      <dl className="chunk-metadata">
        <div>
          <dt>Chunk</dt>
          <dd>#{chunk.sequence + 1}</dd>
        </div>
        <div>
          <dt>Page</dt>
          <dd>{chunk.page_number}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{chunk.chunk_type}</dd>
        </div>
        <div>
          <dt>Tokens</dt>
          <dd>{chunk.token_count}</dd>
        </div>
        <div className="chunk-id">
          <dt>ID</dt>
          <dd>{chunk.id}</dd>
        </div>
        <div className="chunk-heading">
          <dt>Heading path</dt>
          <dd>{chunk.heading_path.join(' › ') || 'Document'}</dd>
        </div>
      </dl>
      {chunk.overlap_text && (
        <div className="overlap">
          <span>Previous 50-token context</span>
          {chunk.overlap_text}
        </div>
      )}
      <pre>{chunk.content}</pre>
    </article>
  )
}
