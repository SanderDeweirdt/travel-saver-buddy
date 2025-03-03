
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { Session, User } from '@supabase/supabase-js';
import { toast } from 'sonner';

type AuthContextType = {
  session: Session | null;
  user: User | null;
  loading: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  // Improved function to ensure user profile exists with proper error handling and verification
  const ensureUserProfile = async (user: User): Promise<boolean> => {
    try {
      console.log('Checking if profile exists for user:', user.id);
      
      // First, check if the profile already exists
      const { data: profile, error: selectError } = await supabase
        .from('profiles')
        .select('id')
        .eq('id', user.id)
        .single();
      
      // If profile exists, return true
      if (profile) {
        console.log('Profile already exists:', profile.id);
        return true;
      }
      
      // If error is not "No rows found" (PGRST116), something else went wrong
      if (selectError && selectError.code !== 'PGRST116') {
        console.error('Error checking user profile:', selectError);
        return false;
      }
      
      console.log('Profile does not exist, creating now...');
      
      // If profile doesn't exist (PGRST116), create it
      const { data: insertData, error: insertError } = await supabase
        .from('profiles')
        .insert([{ 
          id: user.id,
          email: user.email
        }])
        .select('id')
        .single();
      
      if (insertError) {
        console.error('Error creating profile:', insertError);
        
        // Check specifically for RLS policy violation
        if (insertError.code === '42501') {
          console.error('RLS policy violation. User lacks permission to create their profile.');
          toast.error('Authorization error. Please contact support.');
          return false;
        }
        
        toast.error('Failed to create user profile. Please try logging out and in again.');
        return false;
      }
      
      // Verify the profile was created by checking the returned data
      if (insertData && insertData.id) {
        console.log('Profile created successfully:', insertData.id);
        toast.success('Profile created successfully');
        return true;
      } else {
        // This shouldn't happen if insert succeeds, but check anyway
        console.error('Profile creation returned no data');
        toast.error('Profile creation failed. Please try again.');
        return false;
      }
    } catch (error) {
      console.error('Unexpected error in ensureUserProfile:', error);
      toast.error('An unexpected error occurred with your user profile');
      return false;
    }
  };

  // Verify profile existence with retries
  const verifyProfileExists = async (userId: string): Promise<boolean> => {
    // Try up to 3 times with a slight delay
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        console.log(`Verifying profile exists (attempt ${attempt}/3) for user:`, userId);
        const { data, error } = await supabase
          .from('profiles')
          .select('id')
          .eq('id', userId)
          .single();
        
        if (data) {
          console.log('Profile verification successful:', data.id);
          return true;
        }
        
        if (error && error.code !== 'PGRST116') {
          console.error(`Profile verification error (attempt ${attempt}/3):`, error);
        }
        
        // Wait a bit before retrying (200ms, 400ms, 600ms)
        if (attempt < 3) {
          await new Promise(resolve => setTimeout(resolve, attempt * 200));
        }
      } catch (err) {
        console.error(`Unexpected error in profile verification (attempt ${attempt}/3):`, err);
      }
    }
    
    console.error('Profile verification failed after 3 attempts');
    return false;
  };

  useEffect(() => {
    // Get session on mount
    const getInitialSession = async () => {
      try {
        console.log('Getting initial session...');
        const { data } = await supabase.auth.getSession();
        setSession(data.session);
        
        if (data.session?.user) {
          console.log('Session found, setting user:', data.session.user.id);
          
          // Important: First set the user so the app knows someone is logged in
          setUser(data.session.user);
          
          // Then check if the profile already exists
          const profileExists = await verifyProfileExists(data.session.user.id);
          
          if (!profileExists) {
            console.log('Profile does not exist on initial session, creating it');
            // Create the profile if it doesn't exist
            const created = await ensureUserProfile(data.session.user);
            
            if (!created) {
              console.warn('Failed to create profile on initial session');
              // We don't log out the user here, as they're technically authenticated
              // But operations requiring a profile might fail
            }
          }
        } else {
          console.log('No session found');
          setUser(null);
        }
      } catch (error) {
        console.error('Error getting initial session:', error);
      } finally {
        setLoading(false);
      }
    };

    getInitialSession();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        console.log('Auth state changed:', event, session?.user?.id);
        setSession(session);
        
        if (session?.user) {
          // First set the user so the app knows someone is logged in
          setUser(session.user);
          
          // Then verify the profile exists
          if (event === 'SIGNED_IN') {
            const profileExists = await verifyProfileExists(session.user.id);
            
            if (!profileExists) {
              console.log('Profile does not exist on auth change, creating it');
              const created = await ensureUserProfile(session.user);
              
              if (!created) {
                console.warn('Failed to create profile on auth change');
                // We don't log out the user here, as they're technically authenticated
                // But operations requiring a profile might fail
              }
            }
          }
        } else {
          setUser(null);
        }
        
        setLoading(false);
      }
    );

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  const signOut = async () => {
    try {
      await supabase.auth.signOut();
    } catch (error) {
      console.error('Error signing out:', error);
      toast.error('Error signing out. Please try again.');
    }
  };

  const value = {
    session,
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
