export default function PillarHero({ hero }) {
  if (!hero) return null;
  return (
    <section
      style={{
        background: 'linear-gradient(135deg, #111827 0%, #1e293b 100%)',
        padding: '80px 24px 72px',
        color: 'white',
        textAlign: 'center',
      }}
      data-testid="pillar-hero"
    >
      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        <h1
          style={{
            fontSize: 'clamp(28px, 5vw, 48px)',
            fontWeight: 800,
            marginBottom: '20px',
            lineHeight: 1.2,
          }}
          data-testid="pillar-h1"
        >
          {hero.headline}
        </h1>
        {hero.subtext && (
          <p style={{ fontSize: '18px', opacity: 0.85, lineHeight: 1.7, marginBottom: '32px', maxWidth: '640px', margin: '0 auto 32px' }}>
            {hero.subtext}
          </p>
        )}
        {hero.cta_text && (
          <a
            href={hero.cta_link || '/website/contact.html'}
            data-testid="pillar-hero-cta"
            style={{
              display: 'inline-block',
              background: '#9acd32',
              color: '#111827',
              padding: '14px 36px',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '15px',
              textDecoration: 'none',
              transition: 'opacity 0.2s',
            }}
          >
            {hero.cta_text}
          </a>
        )}
      </div>
    </section>
  );
}
