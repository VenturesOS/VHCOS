import { Link } from 'react-router-dom';
import { ArrowLeft, Shield } from 'lucide-react';
import TrustBadge from '../../components/compliance/TrustBadge';

export function PrivacyPolicyPage() {
  return (
    <PolicyLayout title="Privacy Policy" lastUpdated="February 2026">
      <Section title="1. Introduction">
        Ventures HRD Consulting LLP ("Ventures HRD", "we", "us") is committed to protecting your personal data in compliance with the Digital Personal Data Protection Act, 2023 (DPDP Act). This Privacy Policy explains how we collect, use, store, and protect your information when you use our Talent Operating System and related recruitment services.
      </Section>
      <Section title="2. Data We Collect">
        <ul className="list-disc pl-5 space-y-1.5">
          <li><strong>Identity Data:</strong> Full name, date of birth, gender, nationality</li>
          <li><strong>Contact Data:</strong> Email address, phone number, residential address</li>
          <li><strong>Professional Data:</strong> Resume/CV, work history, qualifications, skills, certifications, current and expected compensation</li>
          <li><strong>Application Data:</strong> Job preferences, notice period, availability, cover letters</li>
          <li><strong>Technical Data:</strong> IP address, browser type, device information, access timestamps</li>
          <li><strong>Consent Records:</strong> Timestamps, versions, and preferences of your consent actions</li>
        </ul>
      </Section>
      <Section title="3. Purpose of Processing">
        We process your data for: matching candidates with job opportunities; communicating about applications and career opportunities; managing the recruitment pipeline on behalf of our employer clients; maintaining audit trails for compliance purposes; improving our platform and services through anonymised analytics.
      </Section>
      <Section title="4. Lawful Basis (DPDP 2023)">
        Under the DPDP Act, we process your data based on your explicit consent. Before collecting any personal data, we obtain clear, informed consent through our platform's consent mechanisms. You may withdraw consent at any time.
      </Section>
      <Section title="5. Data Sharing">
        Your data may be shared with: prospective employers (only with your consent for specific roles); our technology service providers who assist in operating the platform; regulatory or legal authorities when required by law. We do not sell your personal data to third parties.
      </Section>
      <Section title="6. Data Retention">
        We retain your data for as long as necessary to fulfil recruitment purposes, typically up to 24 months from last activity. You may request earlier deletion by contacting us. Consent audit logs are retained for a minimum of 5 years for compliance purposes.
      </Section>
      <Section title="7. Your Rights">
        Under the DPDP Act, you have the right to: access the personal data we hold about you; correct inaccurate data; request deletion of your data; withdraw consent at any time; file a complaint with the Data Protection Board of India.
      </Section>
      <Section title="8. Data Security">
        We implement appropriate technical and organisational measures including encryption in transit and at rest, access controls, regular security assessments, and secure cloud infrastructure to protect your data.
      </Section>
      <Section title="9. Contact">
        For privacy-related queries, data access requests, or to exercise your rights, contact our Data Protection Officer at: <strong>privacy@vhc.in</strong>
      </Section>
    </PolicyLayout>
  );
}

export function TermsOfUsePage() {
  return (
    <PolicyLayout title="Terms of Use" lastUpdated="February 2026">
      <Section title="1. Acceptance">
        By accessing or using the Ventures HRD Talent Operating System ("Platform"), you agree to be bound by these Terms of Use. If you do not agree, please do not use the Platform.
      </Section>
      <Section title="2. Platform Description">
        The Platform is an enterprise recruitment management system operated by Ventures HRD Consulting LLP. It facilitates job posting, candidate sourcing, application management, and recruitment pipeline tracking for employers, recruiters, and candidates.
      </Section>
      <Section title="3. User Accounts">
        You are responsible for maintaining the confidentiality of your account credentials. You agree to provide accurate, current information and to update it promptly if it changes. Ventures HRD reserves the right to suspend or terminate accounts that violate these terms.
      </Section>
      <Section title="4. Acceptable Use">
        You agree not to: submit false or misleading information; use the Platform for any unlawful purpose; attempt to gain unauthorised access to any part of the Platform; interfere with or disrupt the Platform's operation; scrape, crawl, or use automated means to access the Platform without permission.
      </Section>
      <Section title="5. Candidate Data">
        Candidates who submit applications consent to their data being processed as described in our Privacy Policy. Employers and recruiters accessing candidate data through the Platform agree to handle such data in compliance with applicable data protection laws including the DPDP Act, 2023.
      </Section>
      <Section title="6. Intellectual Property">
        All content, design, and technology of the Platform are the property of Ventures HRD or its licensors. You may not reproduce, distribute, or create derivative works without written permission.
      </Section>
      <Section title="7. Limitation of Liability">
        The Platform is provided "as is". Ventures HRD makes no warranties regarding uninterrupted access, accuracy of job listings, or hiring outcomes. Our liability is limited to the maximum extent permitted by law.
      </Section>
      <Section title="8. Governing Law">
        These Terms are governed by the laws of India. Disputes shall be subject to the exclusive jurisdiction of the courts in Mumbai, Maharashtra.
      </Section>
      <Section title="9. Changes">
        We may update these Terms periodically. Continued use of the Platform after changes constitutes acceptance of the updated Terms.
      </Section>
    </PolicyLayout>
  );
}

export function CookiePolicyPage() {
  return (
    <PolicyLayout title="Cookie Policy" lastUpdated="February 2026">
      <Section title="1. What Are Cookies">
        Cookies are small text files placed on your device when you visit our Platform. They help us provide essential functionality, remember your preferences, and understand how the Platform is used.
      </Section>
      <Section title="2. Types of Cookies We Use">
        <div className="space-y-3">
          <CookieType name="Essential Cookies" required desc="Required for core Platform functionality including authentication, security, and session management. These cannot be disabled." />
          <CookieType name="Analytics Cookies" desc="Help us understand how visitors interact with the Platform. We use this data to improve functionality and user experience. These are optional." />
          <CookieType name="Marketing Cookies" desc="Used to deliver relevant content and recommendations. These are optional and can be managed through your cookie preferences." />
        </div>
      </Section>
      <Section title="3. Managing Cookies">
        When you first visit the Platform, you will see a cookie consent banner allowing you to accept all cookies, reject non-essential cookies, or customise your preferences. You can change your preferences at any time by clearing your browser cookies and revisiting the Platform.
      </Section>
      <Section title="4. Third-Party Cookies">
        We may use third-party services (such as Google Analytics) that place their own cookies. These are governed by the respective third party's privacy policy.
      </Section>
      <Section title="5. Data Collected via Cookies">
        Cookies may collect: pages visited, time spent, browser type, device information, and referral source. This data is used in aggregate and is not linked to your personal identity unless you have an active session.
      </Section>
      <Section title="6. Cookie Retention">
        Essential cookies expire when your session ends or within 24 hours. Analytics and marketing cookies may persist for up to 12 months.
      </Section>
      <Section title="7. Contact">
        For questions about our use of cookies, contact: <strong>privacy@vhc.in</strong>
      </Section>
    </PolicyLayout>
  );
}

function PolicyLayout({ title, lastUpdated, children }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700">
            <ArrowLeft className="w-4 h-4" /> Back
          </Link>
          <TrustBadge variant="inline" />
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-4 py-10">
        <div className="flex items-center gap-3 mb-2">
          <Shield className="w-5 h-5 text-emerald-600" />
          <h1 className="text-2xl font-bold text-slate-900" data-testid="policy-title">{title}</h1>
        </div>
        <p className="text-xs text-slate-400 mb-8">Last updated: {lastUpdated} | Ventures HRD Consulting LLP</p>
        <div className="space-y-6">{children}</div>
        <div className="mt-12 pt-6 border-t text-center text-xs text-slate-400 space-y-1">
          <p>Ventures HRD Consulting LLP | CIN: AAR-6230</p>
          <div className="flex items-center justify-center gap-4">
            <Link to="/privacy-policy" className="hover:text-slate-600">Privacy Policy</Link>
            <Link to="/terms-of-use" className="hover:text-slate-600">Terms of Use</Link>
            <Link to="/cookie-policy" className="hover:text-slate-600">Cookie Policy</Link>
          </div>
        </div>
      </main>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="mb-2">
      <h2 className="text-base font-semibold text-slate-800 mb-2">{title}</h2>
      <div className="text-sm text-slate-600 leading-relaxed">{children}</div>
    </section>
  );
}

function CookieType({ name, desc, required }) {
  return (
    <div className="p-3 rounded-lg border border-slate-100 bg-white">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm font-medium text-slate-800">{name}</span>
        {required && <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">Always Active</span>}
      </div>
      <p className="text-xs text-slate-500">{desc}</p>
    </div>
  );
}
