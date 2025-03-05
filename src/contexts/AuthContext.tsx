
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

// Mock user type
type User = {
  id: string;
  email: string;
};

type AuthContextType = {
  user: User | null;
  loading: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user exists in localStorage (mock authentication)
    const checkLocalStorage = () => {
      const storedUser = localStorage.getItem('mockUser');
      if (storedUser) {
        setUser(JSON.parse(storedUser));
      }
      setLoading(false);
    };

    // Small timeout to simulate auth check
    const timeoutId = setTimeout(() => {
      checkLocalStorage();
    }, 500);

    return () => clearTimeout(timeoutId);
  }, []);

  const signOut = async () => {
    localStorage.removeItem('mockUser');
    setUser(null);
    return Promise.resolve();
  };

  const value = {
    user,
    loading,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
