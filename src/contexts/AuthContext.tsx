import React, { createContext, useContext, useEffect, useState } from 'react';
import { Session, User } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

interface AuthContextType {
  session: Session | null;
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signUp: (email: string, password: string, fullName: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    // Check if we have a hash in the URL (from OAuth redirect)
    if (window.location.hash && window.location.hash.includes('access_token')) {
      // We have an OAuth redirect, let supabase handle it
      setLoading(true);
      const { data, error } = supabase.auth.getSession();
      
      if (error) {
        console.error('Error getting session from hash:', error);
        toast.error('Error during authentication');
        setLoading(false);
      } else {
        // Clear the hash from the URL
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
        setUser(session?.user ?? null);
        setLoading(false);
        
        // Navigate to home page when user signs in
        if (session && window.location.pathname.includes('/signin')) {
          navigate('/');
          toast.success('Successfully signed in!');
        }
      }
    );

    return () => subscription.unsubscribe();
  }, [navigate]);

  const signIn = async (email: string, password: string) => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      
      if (error) {
        throw error;
      }
      
      navigate('/');
      toast.success('Successfully signed in!');
    } catch (error: any) {
      toast.error(error.message || 'Error signing in');
      console.error('Error signing in:', error);
    } finally {
      setLoading(false);
    }
  };

  const signInWithGoogle = async () => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}`,
        },
      });
      
      if (error) {
        throw error;
      }
      
      // No need for navigate or toast here as the OAuth flow will handle redirection
    } catch (error: any) {
      toast.error(error.message || 'Error signing in with Google');
      console.error('Error signing in with Google:', error);
      setLoading(false);
    }
  };

  const signUp = async (email: string, password: string, fullName: string) => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName,
          },
        },
      });
      
      if (error) {
        throw error;
      }
      
      toast.success('Account created successfully! Please check your email for confirmation.');
      navigate('/signin');
    } catch (error: any) {
      toast.error(error.message || 'Error creating account');
      console.error('Error signing up:', error);
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    try {
      setLoading(true);
      const { error } = await supabase.auth.signOut();
      
      if (error) {
        throw error;
      }
      
      navigate('/signin');
      toast.success('Successfully signed out!');
    } catch (error: any) {
      toast.error(error.message || 'Error signing out');
      console.error('Error signing out:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthContext.Provider value={{ session, user, loading, signIn, signInWithGoogle, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
