import { useState, useCallback } from 'react';
import { Link, useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { toast } from 'sonner';
import { Eye, EyeOff, UserPlus } from 'lucide-react';
import { TurnstileWidget, isTurnstileEnabled } from '../../components/TurnstileWidget';

const LOGO_URL = 'https://customer-assets.emergentagent.com/job_hire-hub-33/artifacts/umsjvfj8_VHC_logo-removebg_edited_edited.png';

export default function Register() {
  const { register, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    role: 'candidate',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [justRegistered, setJustRegistered] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState('');

  // Only redirect if already authenticated AND not in the process of registering
  if (isAuthenticated && user && !justRegistered) {
    return <Navigate to={`/${user.role}`} replace />;
  }

  const handleChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (isTurnstileEnabled && !turnstileToken) {
      toast.error('Please complete the CAPTCHA verification.');
      return;
    }

    setLoading(true);
    setJustRegistered(true);

    try {
      const userData = await register({ ...formData, turnstile_token: turnstileToken });
      toast.success(`Welcome to Ventures HRD, ${userData.name}!`);
      window.location.href = `/${userData.role}`;
    } catch (error) {
      const message = error.response?.data?.detail || 'Registration failed. Please try again.';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC] p-4">
      <div className="w-full max-w-md animate-fade-in">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src={LOGO_URL} alt="Ventures HRD" className="h-16 w-auto mb-4" />
          <h1 className="font-heading text-2xl font-bold text-slate-900">Ventures HRD</h1>
          <p className="text-slate-500 text-sm mt-1">Recruitment Operating System</p>
        </div>

        <Card className="border-slate-200 shadow-lg">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="font-heading text-xl">Create your account</CardTitle>
            <CardDescription>Register as a candidate to explore opportunities</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Full Name</Label>
                <Input
                  id="name"
                  placeholder="John Doe"
                  value={formData.name}
                  onChange={(e) => handleChange('name', e.target.value)}
                  required
                  data-testid="register-name-input"
                  className="focus-visible:ring-[#7CB342]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={(e) => handleChange('email', e.target.value)}
                  required
                  data-testid="register-email-input"
                  className="focus-visible:ring-[#7CB342]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Create a password"
                    value={formData.password}
                    onChange={(e) => handleChange('password', e.target.value)}
                    required
                    minLength={6}
                    data-testid="register-password-input"
                    className="pr-10 focus-visible:ring-[#7CB342]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <Button
                type="submit"
                className="w-full bg-[#7CB342] hover:bg-[#689F38] text-white"
                disabled={loading}
                data-testid="register-submit-btn"
              >
                {loading ? (
                  <div className="spinner w-5 h-5 border-2 border-white border-t-transparent" />
                ) : (
                  <>
                    <UserPlus className="w-4 h-4 mr-2" />
                    Create Account
                  </>
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-slate-500">
                Already have an account?{' '}
                <Link
                  to="/login"
                  className="text-[#7CB342] hover:text-[#689F38] font-medium"
                  data-testid="login-link"
                >
                  Sign in
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-slate-400">
          © 2026 Ventures HRD. All rights reserved.
        </p>
      </div>
    </div>
  );
}
