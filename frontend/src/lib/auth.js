import { createContext, useContext, useState, useEffect } from 'react';
import { authAPI } from './api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [requiresPasswordReset, setRequiresPasswordReset] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('vhc_token');
    const storedUser = localStorage.getItem('vhc_user');
    const storedResetFlag = localStorage.getItem('vhc_requires_reset');
    
    if (token && storedUser) {
      setUser(JSON.parse(storedUser));
      setRequiresPasswordReset(storedResetFlag === 'true');
      // Verify token is still valid
      authAPI.getMe()
        .then((res) => {
          setUser(res.data);
          localStorage.setItem('vhc_user', JSON.stringify(res.data));
          setRequiresPasswordReset(res.data.requires_password_reset || false);
          localStorage.setItem('vhc_requires_reset', res.data.requires_password_reset ? 'true' : 'false');
        })
        .catch((err) => {
          // Only logout on 401 (invalid/expired token).
          // Other errors (429, 500, network) should NOT log the user out.
          if (err?.response?.status === 401) {
            logout();
          }
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    // SEC: purge any stale session artifacts BEFORE writing the new user's
    // tokens. Without this, if the previous user's session was closed
    // without a proper logout, their `vhc_refresh_token` would survive
    // and the axios 401 interceptor would silently refresh into their
    // identity. Reported as: "Madhuri logs in but session flips to Nidhi
    // after some time." (2026-07-24 hotfix)
    localStorage.removeItem('vhc_token');
    localStorage.removeItem('vhc_refresh_token');
    localStorage.removeItem('vhc_user');
    localStorage.removeItem('vhc_requires_reset');

    const response = await authAPI.login(email, password);
    const { access_token, refresh_token, user: userData, requires_password_reset } = response.data;

    localStorage.setItem('vhc_token', access_token);
    // Always write refresh_token — even if the server returned null we must
    // NOT leave a previous user's value in place. `setItem(k, null)` stores
    // the string "null", so use removeItem when we have no fresh token.
    if (refresh_token) {
      localStorage.setItem('vhc_refresh_token', refresh_token);
    } else {
      localStorage.removeItem('vhc_refresh_token');
    }
    localStorage.setItem('vhc_user', JSON.stringify(userData));
    localStorage.setItem('vhc_requires_reset', requires_password_reset ? 'true' : 'false');
    setUser(userData);
    setRequiresPasswordReset(requires_password_reset || false);

    return { ...userData, requires_password_reset };
  };

  const register = async (data) => {
    const response = await authAPI.register(data);
    const { access_token, user: userData } = response.data;
    
    localStorage.setItem('vhc_token', access_token);
    localStorage.setItem('vhc_user', JSON.stringify(userData));
    localStorage.setItem('vhc_requires_reset', 'false');
    setUser(userData);
    setRequiresPasswordReset(false);
    
    return userData;
  };

  const logout = () => {
    localStorage.removeItem('vhc_token');
    localStorage.removeItem('vhc_refresh_token');
    localStorage.removeItem('vhc_user');
    localStorage.removeItem('vhc_requires_reset');
    setUser(null);
    setRequiresPasswordReset(false);
  };

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    isAuthenticated: !!user,
    requiresPasswordReset,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
