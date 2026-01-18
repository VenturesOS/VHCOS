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
        .catch(() => {
          logout();
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    const response = await authAPI.login(email, password);
    const { access_token, user: userData, requires_password_reset } = response.data;
    
    localStorage.setItem('vhc_token', access_token);
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
