
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
  const [profileCheckInProgress, setProfileCheckInProgress] = useState(false);

  // Helper function to ensure user profile exists with proper error handling
  const ensureProfile = async (): Promise<boolean> => {
    if (!user) {
      console.log('Cannot ensure profile: No user logged in');
      return false;
    }
    
    if (profileCheckInProgress) {
      console.log('Profile check already in progress');
      return false;
    }
    
    try {
      setProfileCheckInProgress(true);
      
      // Simply verify the profile exists without creating it
      const { data: profiles, error } = await supabase
        .from('profiles')
        .select('id')
        .eq('id', user.id);
      
      if (error) {
        console.error('Error checking profile:', error);
        return false;
      }
      
      if (profiles && profiles.length > 0) {
        return true;
      }
      
      // If no profile is found, try to create one
      try {
        const { error: insertError } = await supabase
          .from('profiles')
          .insert([{ id: user.id, email: user.email }]);
        
        if (insertError) {
          console.error('Error creating profile:', insertError);
          return false;
        }
        
        return true;
      } catch (insertErr) {
        console.error('Error in profile creation:', insertErr);
        return false;
      }
    } catch (e) {
      console.error('Unexpected error in ensureProfile:', e);
      return false;
    } finally {
      setProfileCheckInProgress(false);
    }
  };

  useEffect(() => {
    // Get session on mount with a timeout safeguard
    const getInitialSession = async () => {
      try {
        console.log('Getting initial session...');
        const { data } = await supabase.auth.getSession();
        setSession(data.session);
        
        if (data.session?.user) {
          console.log('Session found, setting user:', data.session.user.id);
          setUser(data.session.user);
        } else {
          console.log('No session found');
          setUser(null);
        }
      } catch (error) {
        console.error('Error getting initial session:', error);
      } finally {
        // Always set loading to false, even if errors occur
        setLoading(false);
      }
    };

    // Set a timeout to ensure loading state doesn't get stuck
    const timeoutId = setTimeout(() => {
      if (loading) {
        console.warn('Session check timed out, forcing loading state to false');
        setLoading(false);
      }
    }, 5000); // 5 second timeout

    getInitialSession();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        console.log('Auth state changed:', event, session?.user?.id);
        setSession(session);
        
        if (session?.user) {
          setUser(session.user);
        } else {
          setUser(null);
        }
        
        setLoading(false);
      }
    );

    return () => {
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
