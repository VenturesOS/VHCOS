import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { blogAPI } from '../../lib/api';
import { ArrowLeft, Calendar, Clock, Tag, Globe, MapPin, Share2 } from 'lucide-react';

function ShareButtons({ title, url }) {
  const encoded = encodeURIComponent(url);
  const text = encodeURIComponent(title);
  const links = [
    { label: 'LinkedIn', color: '#0A66C2', href: `https://www.linkedin.com/sharing/share-offsite/?url=${encoded}` },
    { label: 'X', color: '#000', href: `https://x.com/intent/tweet?text=${text}&url=${encoded}` },
    { label: 'WhatsApp', color: '#25D366', href: `https://wa.me/?text=${text}%20${encoded}` },
  ];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '12px' }} data-testid="share-buttons">
      <Share2 size={15} color="#9CA3AF" />
      {links.map(l => (
        <a key={l.label} href={l.href} target="_blank" rel="noopener noreferrer"
          style={{ fontSize: '12px', fontWeight: 600, color: l.color, padding: '4px 14px', borderRadius: '20px', border: `1px solid ${l.color}22`, textDecoration: 'none', transition: 'background 0.15s' }}
          onMouseEnter={e => { e.currentTarget.style.background = `${l.color}10`; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
          data-testid={`share-${l.label.toLowerCase()}`}>
          {l.label}
        </a>
      ))}
    </div>
  );
}

function BlogArticleSchema({ blog, type }) {
  const baseUrl = window.location.origin;
  const path = type === 'employer' ? 'industrial-hiring-insights' : 'career-insights';
  const schema = {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": blog.title,
    "description": blog.meta_description,
    "url": `${baseUrl}/website/${path}/${blog.slug}`,
    "datePublished": blog.published_at,
    "dateModified": blog.updated_at || blog.published_at,
    "publisher": { "@type": "Organization", "name": "VHC Talent Advisory" },
    "author": { "@type": "Organization", "name": "VHC Talent Advisory" },
    "keywords": (blog.keywords || []).join(', '),
  };
  return <script type="application/ld+json">{JSON.stringify(schema)}</script>;
}

export function EmployerBlogList() {
  const [blogs, setBlogs] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    blogAPI.employerList(page).then(r => {
      setBlogs(r.data.blogs || []);
      setTotalPages(r.data.pages || 1);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [page]);

  const fmtDate = d => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' }) : '';

  return (
    <div className="min-h-screen bg-white" data-testid="employer-blog-list">
      <Helmet>
        <title>Industrial Hiring Insights - VHC Talent Advisory</title>
        <meta name="description" content="Expert insights on industrial recruitment, executive search, and talent acquisition across manufacturing, engineering, and technology sectors." />
        <meta property="og:title" content="Industrial Hiring Insights - VHC Talent Advisory" />
        <meta property="og:description" content="Expert insights on industrial recruitment and talent acquisition." />
        <meta property="og:type" content="website" />
      </Helmet>

      {/* Header */}
      <header style={{ background: '#111827', padding: '16px 24px' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <a href="/website/Index.html" style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none' }}>
            <img src="/website/assests/logo.svg" alt="VHC" style={{ height: '36px' }} onError={e => { e.target.style.display = 'none'; }} />
            <span style={{ color: 'white', fontWeight: 700, fontSize: '18px' }}>Ventures HRD Centre</span>
          </a>
          <a href="/website/contact.html" style={{ background: '#9acd32', color: '#111827', padding: '10px 24px', borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>Contact Us</a>
        </div>
      </header>

      {/* Hero */}
      <section style={{ background: 'linear-gradient(135deg, #111827 0%, #1e293b 100%)', padding: '80px 24px', textAlign: 'center', color: 'white' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
          <p style={{ color: '#9acd32', fontWeight: 600, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '2px', marginBottom: '16px' }}>Industrial Hiring Intelligence</p>
          <h1 style={{ fontSize: 'clamp(28px, 5vw, 48px)', fontWeight: 800, marginBottom: '16px', lineHeight: 1.2 }}>Industrial Hiring Insights</h1>
          <p style={{ fontSize: '18px', opacity: 0.8, lineHeight: 1.6 }}>Expert perspectives on recruitment strategies, talent markets, and hiring intelligence for industrial leaders</p>
        </div>
      </section>

      {/* Blog Grid */}
      <section style={{ maxWidth: '1200px', margin: '0 auto', padding: '60px 24px' }}>
        {loading ? <p style={{ textAlign: 'center', color: '#9ca3af', padding: '60px' }}>Loading articles...</p> :
          blogs.length === 0 ? <p style={{ textAlign: 'center', color: '#9ca3af', padding: '60px' }}>Articles coming soon. Check back for expert hiring insights.</p> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '32px' }}>
              {blogs.map(b => (
                <Link key={b.id} to={`/industrial-hiring-insights/${b.slug}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                  <article data-testid={`blog-card-${b.slug}`} style={{ background: '#f9fafb', borderRadius: '16px', padding: '32px', height: '100%', display: 'flex', flexDirection: 'column', transition: 'box-shadow 0.2s, transform 0.2s', cursor: 'pointer' }}
                    onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 8px 30px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                    onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'none'; }}>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
                      {b.region && <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '12px', background: b.region === 'global' ? '#EFF6FF' : '#F0FDF4', color: b.region === 'global' ? '#2563EB' : '#16A34A', padding: '4px 10px', borderRadius: '20px', fontWeight: 600 }}>{b.region === 'global' ? '🌍' : '🇮🇳'} {b.region}</span>}
                      <span style={{ fontSize: '12px', background: '#F3F4F6', color: '#6B7280', padding: '4px 10px', borderRadius: '20px' }}>{b.industry}</span>
                    </div>
                    <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', marginBottom: '12px', lineHeight: 1.4 }}>{b.title}</h2>
                    <p style={{ fontSize: '15px', color: '#6B7280', lineHeight: 1.7, flex: 1 }}>{b.meta_description}</p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '20px', fontSize: '13px', color: '#9CA3AF' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>{fmtDate(b.published_at)}</span>
                      <span>{b.word_count_estimate ? `${Math.ceil(b.word_count_estimate / 200)} min read` : ''}</span>
                    </div>
                  </article>
                </Link>
              ))}
            </div>
          )
        }
        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '48px' }}>
            {Array.from({ length: totalPages }, (_, i) => (
              <button key={`page-${i+1}`} onClick={() => setPage(i + 1)} style={{ width: '40px', height: '40px', borderRadius: '8px', border: page === i + 1 ? '2px solid #7CB342' : '1px solid #E5E7EB', background: page === i + 1 ? '#F0FDF4' : 'white', color: page === i + 1 ? '#7CB342' : '#6B7280', fontWeight: 600, cursor: 'pointer' }}>{i + 1}</button>
            ))}
          </div>
        )}
      </section>

      {/* Footer */}
      <footer style={{ background: '#111827', color: 'white', padding: '40px 24px', textAlign: 'center' }}>
        <p style={{ opacity: 0.6, fontSize: '14px' }}>&copy; {new Date().getFullYear()} Ventures HRD Centre Pvt Ltd. All rights reserved.</p>
      </footer>
    </div>
  );
}

export function EmployerBlogArticle() {
  const { slug } = useParams();
  const [blog, setBlog] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    blogAPI.employerBySlug(slug).then(r => {
      setBlog(r.data);
      // Track page view
      if (r.data?.id) blogAPI.trackEvent({ blog_id: r.data.id, event_type: 'view' }).catch(() => {});
    }).catch(() => setBlog(null)).finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><p style={{ color: '#9ca3af' }}>Loading article...</p></div>;
  if (!blog) return <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}><p style={{ fontSize: '24px', fontWeight: 700 }}>Article Not Found</p><Link to="/industrial-hiring-insights" style={{ color: '#7CB342' }}>Back to Insights</Link></div>;

  const fmtDate = d => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' }) : '';

  return (
    <div className="min-h-screen bg-white" data-testid="employer-blog-article">
      <Helmet>
        <title>{blog.title} - VHC Talent Advisory</title>
        <meta name="description" content={blog.meta_description} />
        <meta property="og:title" content={blog.title} />
        <meta property="og:description" content={blog.meta_description} />
        <meta property="og:type" content="article" />
        <meta name="keywords" content={(blog.keywords || []).join(', ')} />
      </Helmet>
      <BlogArticleSchema blog={blog} type="employer" />

      <header style={{ background: '#111827', padding: '16px 24px' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <a href="/website/Index.html" style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none' }}>
            <img src="/website/assests/logo.svg" alt="VHC" style={{ height: '36px' }} onError={e => { e.target.style.display = 'none'; }} />
            <span style={{ color: 'white', fontWeight: 700, fontSize: '18px' }}>Ventures HRD Centre</span>
          </a>
          <a href="/website/contact.html" style={{ background: '#9acd32', color: '#111827', padding: '10px 24px', borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>Contact Us</a>
        </div>
      </header>

      <article style={{ maxWidth: '800px', margin: '0 auto', padding: '48px 24px' }}>
        <Link to="/industrial-hiring-insights" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#7CB342', fontSize: '14px', fontWeight: 600, textDecoration: 'none', marginBottom: '32px' }} data-testid="back-link">
          <ArrowLeft size={16} /> Back to Insights
        </Link>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
          {blog.region && <span style={{ fontSize: '12px', background: '#F0FDF4', color: '#16A34A', padding: '4px 12px', borderRadius: '20px', fontWeight: 600, textTransform: 'capitalize' }}>{blog.region}</span>}
          <span style={{ fontSize: '12px', background: '#F3F4F6', color: '#6B7280', padding: '4px 12px', borderRadius: '20px' }}>{blog.industry}</span>
        </div>
        <h1 style={{ fontSize: 'clamp(28px, 5vw, 42px)', fontWeight: 800, color: '#111827', lineHeight: 1.3, marginBottom: '16px' }}>{blog.title}</h1>
        <div style={{ display: 'flex', gap: '16px', fontSize: '14px', color: '#9CA3AF', marginBottom: '40px', flexWrap: 'wrap' }}>
          <span>{fmtDate(blog.published_at)}</span>
          <span>{blog.word_count_estimate ? `${Math.ceil(blog.word_count_estimate / 200)} min read` : ''}</span>
        </div>
        <ShareButtons title={blog.title} url={window.location.href} />
        <div className="prose prose-lg prose-slate max-w-none" style={{ fontSize: '17px', lineHeight: 1.8, color: '#374151', marginTop: '32px' }} dangerouslySetInnerHTML={{ __html: blog.content }} />
        {blog.keywords?.length > 0 && (
          <div style={{ marginTop: '48px', paddingTop: '32px', borderTop: '1px solid #E5E7EB' }}>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {blog.keywords.map((k, i) => <span key={`kw-${k}-${i}`} style={{ fontSize: '12px', background: '#F3F4F6', color: '#6B7280', padding: '4px 12px', borderRadius: '20px' }}>{k}</span>)}
            </div>
          </div>
        )}
      </article>

      <footer style={{ background: '#111827', color: 'white', padding: '40px 24px', textAlign: 'center' }}>
        <p style={{ opacity: 0.6, fontSize: '14px' }}>&copy; {new Date().getFullYear()} Ventures HRD Centre Pvt Ltd. All rights reserved.</p>
      </footer>
    </div>
  );
}

export function CandidateBlogList() {
  const [blogs, setBlogs] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState('');

  const categories = [
    { value: '', label: 'All' },
    { value: 'career-growth', label: 'Career Growth' },
    { value: 'job-switching', label: 'Job Switching' },
    { value: 'resume-interview', label: 'Resume & Interview' },
    { value: 'salary-trends', label: 'Salary Trends' },
    { value: 'industry-opportunities', label: 'Industry Opportunities' },
  ];

  useEffect(() => {
    setLoading(true);
    blogAPI.candidateList(page, activeCategory || undefined).then(r => {
      setBlogs(r.data.blogs || []);
      setTotalPages(r.data.pages || 1);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [page, activeCategory]);

  const fmtDate = d => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' }) : '';

  return (
    <div className="min-h-screen bg-white" data-testid="candidate-blog-list">
      <Helmet>
        <title>Career Insights & Advice - VHC Talent Advisory</title>
        <meta name="description" content="Career growth tips, salary trends, resume guidance, and industry insights for industrial professionals including engineers, plant HR, and manufacturing leaders." />
        <meta property="og:title" content="Career Insights & Advice - VHC Talent Advisory" />
        <meta property="og:description" content="Career advice and insights for industrial professionals." />
        <meta property="og:type" content="website" />
      </Helmet>

      <header style={{ background: '#111827', padding: '16px 24px' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <a href="/website/Index.html" style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none' }}>
            <img src="/website/assests/logo.svg" alt="VHC" style={{ height: '36px' }} onError={e => { e.target.style.display = 'none'; }} />
            <span style={{ color: 'white', fontWeight: 700, fontSize: '18px' }}>Ventures HRD Centre</span>
          </a>
          <div style={{ display: 'flex', gap: '12px' }}>
            <a href="/register" style={{ background: '#9acd32', color: '#111827', padding: '10px 24px', borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>Create Profile</a>
          </div>
        </div>
      </header>

      <section style={{ background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)', padding: '80px 24px', textAlign: 'center' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
          <p style={{ color: '#7CB342', fontWeight: 600, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '2px', marginBottom: '16px' }}>Your Career, Our Priority</p>
          <h1 style={{ fontSize: 'clamp(28px, 5vw, 48px)', fontWeight: 800, color: '#111827', marginBottom: '16px', lineHeight: 1.2 }}>Career Insights & Advice</h1>
          <p style={{ fontSize: '18px', color: '#4B5563', lineHeight: 1.6 }}>Practical career guidance for engineers, manufacturing professionals, and industrial leaders</p>
        </div>
      </section>

      {/* Category Filter */}
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px 24px 0' }}>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
          {categories.map(c => (
            <button key={c.value} onClick={() => { setActiveCategory(c.value); setPage(1); }}
              data-testid={`cat-filter-${c.value || 'all'}`}
              style={{ padding: '8px 20px', borderRadius: '24px', border: activeCategory === c.value ? '2px solid #7CB342' : '1px solid #E5E7EB', background: activeCategory === c.value ? '#F0FDF4' : 'white', color: activeCategory === c.value ? '#7CB342' : '#6B7280', fontWeight: 600, fontSize: '14px', cursor: 'pointer' }}>
              {c.label}
            </button>
          ))}
        </div>
      </div>

      <section style={{ maxWidth: '1200px', margin: '0 auto', padding: '40px 24px 60px' }}>
        {loading ? <p style={{ textAlign: 'center', color: '#9ca3af', padding: '60px' }}>Loading articles...</p> :
          blogs.length === 0 ? <p style={{ textAlign: 'center', color: '#9ca3af', padding: '60px' }}>Articles coming soon. Great career advice is on its way!</p> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '32px' }}>
              {blogs.map(b => (
                <Link key={b.id} to={`/career-insights/${b.slug}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                  <article data-testid={`blog-card-${b.slug}`} style={{ background: 'white', border: '1px solid #E5E7EB', borderRadius: '16px', padding: '32px', height: '100%', display: 'flex', flexDirection: 'column', transition: 'box-shadow 0.2s, transform 0.2s', cursor: 'pointer' }}
                    onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 8px 30px rgba(0,0,0,0.08)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                    onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'none'; }}>
                    <div style={{ marginBottom: '16px' }}>
                      {b.category && <span style={{ fontSize: '12px', background: '#F5F3FF', color: '#7C3AED', padding: '4px 12px', borderRadius: '20px', fontWeight: 600 }}>{b.category.replace(/-/g, ' ')}</span>}
                    </div>
                    <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', marginBottom: '12px', lineHeight: 1.4 }}>{b.title}</h2>
                    <p style={{ fontSize: '15px', color: '#6B7280', lineHeight: 1.7, flex: 1 }}>{b.meta_description}</p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '20px', fontSize: '13px', color: '#9CA3AF' }}>
                      <span>{fmtDate(b.published_at)}</span>
                      <span>{b.word_count_estimate ? `${Math.ceil(b.word_count_estimate / 200)} min read` : ''}</span>
                    </div>
                  </article>
                </Link>
              ))}
            </div>
          )
        }
        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '48px' }}>
            {Array.from({ length: totalPages }, (_, i) => (
              <button key={`page-${i+1}`} onClick={() => setPage(i + 1)} style={{ width: '40px', height: '40px', borderRadius: '8px', border: page === i + 1 ? '2px solid #7CB342' : '1px solid #E5E7EB', background: page === i + 1 ? '#F0FDF4' : 'white', color: page === i + 1 ? '#7CB342' : '#6B7280', fontWeight: 600, cursor: 'pointer' }}>{i + 1}</button>
            ))}
          </div>
        )}
      </section>

      <footer style={{ background: '#111827', color: 'white', padding: '40px 24px', textAlign: 'center' }}>
        <p style={{ opacity: 0.6, fontSize: '14px' }}>&copy; {new Date().getFullYear()} Ventures HRD Centre Pvt Ltd. All rights reserved.</p>
      </footer>
    </div>
  );
}

export function CandidateBlogArticle() {
  const { slug } = useParams();
  const [blog, setBlog] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    blogAPI.candidateBySlug(slug).then(r => {
      setBlog(r.data);
      // Track page view
      if (r.data?.id) blogAPI.trackEvent({ blog_id: r.data.id, event_type: 'view' }).catch(() => {});
    }).catch(() => setBlog(null)).finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><p style={{ color: '#9ca3af' }}>Loading article...</p></div>;
  if (!blog) return <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}><p style={{ fontSize: '24px', fontWeight: 700 }}>Article Not Found</p><Link to="/career-insights" style={{ color: '#7CB342' }}>Back to Career Insights</Link></div>;

  const fmtDate = d => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' }) : '';

  return (
    <div className="min-h-screen bg-white" data-testid="candidate-blog-article">
      <Helmet>
        <title>{blog.title} - Career Insights | VHC Talent Advisory</title>
        <meta name="description" content={blog.meta_description} />
        <meta property="og:title" content={blog.title} />
        <meta property="og:description" content={blog.meta_description} />
        <meta property="og:type" content="article" />
        <meta name="keywords" content={(blog.keywords || []).join(', ')} />
      </Helmet>
      <BlogArticleSchema blog={blog} type="candidate" />

      <header style={{ background: '#111827', padding: '16px 24px' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <a href="/website/Index.html" style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none' }}>
            <img src="/website/assests/logo.svg" alt="VHC" style={{ height: '36px' }} onError={e => { e.target.style.display = 'none'; }} />
            <span style={{ color: 'white', fontWeight: 700, fontSize: '18px' }}>Ventures HRD Centre</span>
          </a>
          <a href="/register" style={{ background: '#9acd32', color: '#111827', padding: '10px 24px', borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>Create Profile</a>
        </div>
      </header>

      <article style={{ maxWidth: '760px', margin: '0 auto', padding: '48px 24px' }}>
        <Link to="/career-insights" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#7CB342', fontSize: '14px', fontWeight: 600, textDecoration: 'none', marginBottom: '32px' }} data-testid="back-link">
          <ArrowLeft size={16} /> Back to Career Insights
        </Link>
        <div style={{ marginBottom: '20px' }}>
          {blog.category && <span style={{ fontSize: '12px', background: '#F5F3FF', color: '#7C3AED', padding: '4px 12px', borderRadius: '20px', fontWeight: 600, textTransform: 'capitalize' }}>{blog.category.replace(/-/g, ' ')}</span>}
        </div>
        <h1 style={{ fontSize: 'clamp(26px, 5vw, 40px)', fontWeight: 800, color: '#111827', lineHeight: 1.3, marginBottom: '16px' }}>{blog.title}</h1>
        <div style={{ display: 'flex', gap: '16px', fontSize: '14px', color: '#9CA3AF', marginBottom: '40px' }}>
          <span>{fmtDate(blog.published_at)}</span>
          <span>{blog.word_count_estimate ? `${Math.ceil(blog.word_count_estimate / 200)} min read` : ''}</span>
        </div>
        <ShareButtons title={blog.title} url={window.location.href} />
        <div className="prose prose-lg prose-slate max-w-none" style={{ fontSize: '17px', lineHeight: 1.9, color: '#374151', marginTop: '32px' }} dangerouslySetInnerHTML={{ __html: blog.content }} />
        {blog.keywords?.length > 0 && (
          <div style={{ marginTop: '48px', paddingTop: '32px', borderTop: '1px solid #E5E7EB' }}>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {blog.keywords.map((k, i) => <span key={`kw-${k}-${i}`} style={{ fontSize: '12px', background: '#F3F4F6', color: '#6B7280', padding: '4px 12px', borderRadius: '20px' }}>{k}</span>)}
            </div>
          </div>
        )}
        {/* Soft CTA */}
        <div style={{ marginTop: '48px', background: '#F0FDF4', borderRadius: '16px', padding: '32px', textAlign: 'center', border: '1px solid #DCFCE7' }}>
          <h3 style={{ fontSize: '22px', fontWeight: 700, color: '#111827', marginBottom: '12px' }}>Looking for your next career move?</h3>
          <p style={{ color: '#4B5563', marginBottom: '20px', lineHeight: 1.6 }}>Create your profile and let top employers discover you. It takes less than 5 minutes.</p>
          <a href="/register" style={{ display: 'inline-block', background: '#7CB342', color: 'white', padding: '14px 32px', borderRadius: '8px', fontWeight: 700, textDecoration: 'none', fontSize: '16px' }}>Create Your Profile</a>
        </div>
      </article>

      <footer style={{ background: '#111827', color: 'white', padding: '40px 24px', textAlign: 'center' }}>
        <p style={{ opacity: 0.6, fontSize: '14px' }}>&copy; {new Date().getFullYear()} Ventures HRD Centre Pvt Ltd. All rights reserved.</p>
      </footer>
    </div>
  );
}
