import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { authAPI } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { toast } from 'sonner';
import { ArrowLeft, Mail, Lock, Eye, EyeOff, CheckCircle2, Loader2 } from 'lucide-react';

const LOGO_URL = '/assets/vhc_logo.png';

export default function ForgotPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  return token ? <ResetWithToken token={token} /> : <RequestReset />;
}

function RequestReset() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authAPI.forgotPassword(email);
      setSent(true);
    } catch {
      toast.error('Something went wrong. Please try again.');
    } finally { setLoading(false); }
  };

  if (sent) {
    return (
      <Shell>
        <Card className="border-slate-200 shadow-lg">
          <CardContent className="py-10 text-center space-y-4">
            <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-7 h-7 text-green-600" />
            </div>
            <h2 className="font-heading text-xl font-bold text-slate-900">Check Your Email</h2>
            <p className="text-slate-500 text-sm max-w-xs mx-auto">If an account with <strong>{email}</strong> exists, we've sent a password reset link. It expires in 1 hour.</p>
            <Link to="/login" className="inline-flex items-center gap-1.5 text-sm text-[#7CB342] font-semibold hover:underline mt-2" data-testid="back-to-login-link">
              <ArrowLeft className="w-4 h-4" /> Back to Login
            </Link>
          </CardContent>
        </Card>
      </Shell>
    );
  }

  return (
    <Shell>
      <Card className="border-slate-200 shadow-lg">
        <CardHeader className="space-y-1 pb-4">
          <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center mb-2">
            <Mail className="w-6 h-6 text-blue-600" />
          </div>
          <CardTitle className="font-heading text-xl">Forgot Password</CardTitle>
          <CardDescription>Enter your email and we'll send you a reset link.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <Input id="email" type="email" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} required data-testid="forgot-email-input" className="focus-visible:ring-[#7CB342]" />
            </div>
            <Button type="submit" className="w-full bg-[#7CB342] hover:bg-[#689F38] text-white" disabled={loading} data-testid="forgot-submit-btn">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Mail className="w-4 h-4 mr-2" />}
              Send Reset Link
            </Button>
          </form>
          <div className="mt-4 text-center">
            <Link to="/login" className="text-sm text-slate-500 hover:text-[#7CB342]" data-testid="back-to-login">
              <ArrowLeft className="w-3.5 h-3.5 inline mr-1" />Back to Login
            </Link>
          </div>
        </CardContent>
      </Card>
    </Shell>
  );
}

function ResetWithToken({ token }) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password.length < 8) { toast.error('Password must be at least 8 characters'); return; }
    if (password !== confirm) { toast.error('Passwords do not match'); return; }
    setLoading(true);
    try {
      await authAPI.forgotPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Reset failed. The link may have expired.');
    } finally { setLoading(false); }
  };

  if (done) {
    return (
      <Shell>
        <Card className="border-slate-200 shadow-lg">
          <CardContent className="py-10 text-center space-y-4">
            <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-7 h-7 text-green-600" />
            </div>
            <h2 className="font-heading text-xl font-bold text-slate-900">Password Reset Complete</h2>
            <p className="text-slate-500 text-sm">You can now log in with your new password.</p>
            <Link to="/login" data-testid="go-to-login-btn">
              <Button className="bg-[#7CB342] hover:bg-[#689F38] text-white mt-2">Go to Login</Button>
            </Link>
          </CardContent>
        </Card>
      </Shell>
    );
  }

  return (
    <Shell>
      <Card className="border-slate-200 shadow-lg">
        <CardHeader className="space-y-1 pb-4">
          <div className="w-12 h-12 rounded-xl bg-amber-50 flex items-center justify-center mb-2">
            <Lock className="w-6 h-6 text-amber-600" />
          </div>
          <CardTitle className="font-heading text-xl">Set New Password</CardTitle>
          <CardDescription>Choose a strong password (min 8 characters).</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>New Password</Label>
              <Input type={showPw ? 'text' : 'password'} placeholder="Min 8 characters" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} data-testid="new-pw-input" className="focus-visible:ring-[#7CB342]" />
            </div>
            <div className="space-y-2">
              <Label>Confirm Password</Label>
              <div className="relative">
                <Input type={showPw ? 'text' : 'password'} placeholder="Confirm password" value={confirm} onChange={e => setConfirm(e.target.value)} required data-testid="confirm-pw-input" className="pr-10 focus-visible:ring-[#7CB342]" />
                <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <Button type="submit" className="w-full bg-[#7CB342] hover:bg-[#689F38] text-white" disabled={loading} data-testid="reset-pw-btn">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Lock className="w-4 h-4 mr-2" />}
              Reset Password
            </Button>
          </form>
        </CardContent>
      </Card>
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC] p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="flex flex-col items-center mb-8">
          <img src={LOGO_URL} alt="Ventures HRD" className="h-16 w-auto mb-4" />
          <h1 className="font-heading text-2xl font-bold text-slate-900">Ventures HRD</h1>
        </div>
        {children}
      </div>
    </div>
  );
}
