export default function PillarContent({ html, faq }) {
  return (
    <article data-testid="pillar-content">
      {/* Main HTML content — sanitized before reaching this component */}
      <div
        className="pillar-prose"
        data-testid="pillar-html-content"
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {/* FAQ Section (rendered from structured data for future JSON-LD) */}
      {faq && faq.length > 0 && (
        <section style={{ marginTop: '56px' }} data-testid="pillar-faq">
          <h2 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '24px' }}>Frequently Asked Questions</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {faq.map((item, i) => (
              <details
                key={i}
                style={{
                  border: '1px solid #e5e7eb',
                  borderRadius: '10px',
                  padding: '20px 24px',
                  background: '#fafafa',
                }}
                data-testid={`pillar-faq-${i}`}
              >
                <summary style={{ fontWeight: 600, fontSize: '16px', color: '#111827', cursor: 'pointer', lineHeight: 1.5 }}>
                  {item.question}
                </summary>
                <p style={{ marginTop: '12px', fontSize: '15px', color: '#4b5563', lineHeight: 1.7 }}>
                  {item.answer}
                </p>
              </details>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
