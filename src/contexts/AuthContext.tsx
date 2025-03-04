
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { Session, User } from '@supabase/supabase-js';
import { toast } from 'sonner';

type AuthContextType = {
  session: Session | null;
  user: User | null;
  loading: boolean;
  signOut: () => Promise<void>;
  ensureProfile: () => Promise<boolean>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  // Helper function to ensure user profile exists
  const ensureProfile = async (): Promise<boolean> => {
    if (!user) {
      console.log('Cannot ensure profile: No user logged in');
      return false;
    }
    
    // Simply verify the profile exists
    const { data: profiles, error } = await supabase
      .from('profiles')
      .select('id')
      .eq('id', user.id)
      .single();
    
    if (error) {
      console.error('Error checking profile:', error);
      return false;
    }
    
    return true;
  };

  useEffect(() => {
    let isSubscribed = true;
    
    // Get session on mount with a timeout safeguard
    const getInitialSession = async () => {
      try {
        console.log('Getting initial session...');
        const { data, error } = await supabase.auth.getSession();
        
        if (error) {
          console.error('Error getting initial session:', error);
          if (isSubscribed) setLoading(false);
          return;
        }
        
        if (data.session?.user) {
          console.log('Session found, setting user:', data.session.user.id);
          if (isSubscribed) {
            setSession(data.session);
            setUser(data.session.user);
          }
        } else {
          console.log('No session found');
          if (isSubscribed) {
            setUser(null);
            setSession(null);
          }
        }
      } catch (error) {
        console.error('Error getting initial session:', error);
      } finally {
        // Always set loading to false
        if (isSubscribed) setLoading(false);
      }
    };

    // Set a timeout to ensure loading state doesn't get stuck
    const timeoutId = setTimeout(() => {
      if (loading && isSubscribed) {
        console.warn('Session check timed out, forcing loading state to false');
        setLoading(false);
      }
    }, 2000); // Use a shorter timeout for better UX
    
    getInitialSession();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, currentSession) => {
        console.log('Auth state changed:', event, currentSession?.user?.id);
        
        if (isSubscribed) {
          setSession(currentSession);
          
          if (currentSession?.user) {
            setUser(currentSession.user);
          } else {
            setUser(null);
          }
          
          setLoading(false);
        }
      }
    );

    return () => {
      isSubscribed = false;
      clearTimeout(timeoutId);
      subscription.unsubscribe();
    };
  }, []);

  const signOut = async () => {
    setLoading(true);
    try {
      await supabase.auth.signOut();
      setUser(null);
      setSession(null);
    } catch (error) {
      console.error('Error signing out:', error);
      toast.error('Error signing out. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const value = {
    session,
    user,
    loading,
    signOut,
    ensureProfile,
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
