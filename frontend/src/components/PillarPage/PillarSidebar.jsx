import { ArrowRight } from 'lucide-react';

const RELATED_LINKS = {
  'industrial-recruitment': [
    { label: 'HR Consulting Services', href: '/hr-consulting-services' },
    { label: 'Career Insights', href: '/career-insights' },
    { label: 'Industrial Hiring Insights', href: '/industrial-hiring-insights' },
  ],
  'hr-consulting-services': [
    { label: 'Industrial Recruitment', href: '/industrial-recruitment' },
    { label: 'Career Insights', href: '/career-insights' },
    { label: 'Industrial Hiring Insights', href: '/industrial-hiring-insights' },
  ],
  'career-insights': [
    { label: 'Industrial Recruitment', href: '/industrial-recruitment' },
    { label: 'HR Consulting Services', href: '/hr-consulting-services' },
    { label: 'Career Insights Blog', href: '/career-insights' },
  ],
};

export default function PillarSidebar({ slug }) {
  const links = RELATED_LINKS[slug] || [];

  return (
    <aside data-testid="pillar-sidebar" style={{ position: 'sticky', top: '32px', alignSelf: 'start' }}>
      {/* Related Pages */}
      <div style={{ background: '#f9fafb', borderRadius: '12px', padding: '28px', marginBottom: '24px' }}>
        <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', marginBottom: '16px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Related Pages</h3>
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {links.map((link, i) => (
            <a
              key={i}
              href={link.href}
              data-testid={`sidebar-link-${i}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: '8px',
                color: '#374151',
                fontSize: '14px',
                fontWeight: 500,
                textDecoration: 'none',
                background: 'white',
                border: '1px solid #e5e7eb',
                transition: 'border-color 0.15s, background 0.15s',
              }}
            >
              {link.label}
              <ArrowRight size={14} color="#9ca3af" />
            </a>
          ))}
        </nav>
      </div>

      {/* CTA Card */}
      <div style={{ background: '#111827', borderRadius: '12px', padding: '28px', color: 'white' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '10px' }}>Talk to an Expert</h3>
        <p style={{ fontSize: '14px', opacity: 0.75, lineHeight: 1.6, marginBottom: '20px' }}>
          Get a confidential consultation on your workforce needs.
        </p>
        <a
          href="/website/contact.html"
          data-testid="sidebar-cta"
          style={{
            display: 'inline-block',
            background: '#9acd32',
            color: '#111827',
            padding: '10px 24px',
            borderRadius: '8px',
            fontWeight: 600,
            fontSize: '14px',
            textDecoration: 'none',
          }}
        >
          Schedule a Call
        </a>
      </div>
    </aside>
  );
}
