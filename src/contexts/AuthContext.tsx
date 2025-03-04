
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
      
      // First, check for profiles using array result not single object
      const { data: profiles, error: selectError } = await supabase
        .from('profiles')
        .select('id')
        .eq('id', user.id);
      
      // If profile exists, return true
      if (profiles && profiles.length > 0) {
        console.log('Profile already exists:', profiles[0].id);
        return true;
      }
      
      // If error is not related to "no rows", something else went wrong
      if (selectError && selectError.code !== 'PGRST116') {
        console.error('Error checking user profile:', selectError);
        return false;
      }
      
      console.log('Profile does not exist, creating now...');
      
      // If profile doesn't exist, create it
      const { data: insertData, error: insertError } = await supabase
        .from('profiles')
        .insert([{ 
          id: user.id,
          email: user.email
        }]);
      
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
      
      console.log('Profile created successfully');
      toast.success('Profile created successfully');
      return true;
    } catch (error) {
      console.error('Unexpected error in ensureUserProfile:', error);
      toast.error('An unexpected error occurred with your user profile');
      return false;
    }
  };

  // Verify profile existence - simplified to not use single() which causes 406 errors
  const verifyProfileExists = async (userId: string): Promise<boolean> => {
    try {
      console.log('Verifying profile exists for user:', userId);
      const { data, error } = await supabase
        .from('profiles')
        .select('id')
        .eq('id', userId);
      
      if (data && data.length > 0) {
        console.log('Profile verification successful:', data[0].id);
        return true;
      }
      
      if (error) {
        console.error('Profile verification error:', error);
        return false;
      }
      
      return false;
    } catch (err) {
      console.error('Unexpected error in profile verification:', err);
      return false;
    }
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
            await ensureUserProfile(data.session.user);
          }
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
              await ensureUserProfile(session.user);
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
