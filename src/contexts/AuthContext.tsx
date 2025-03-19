
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
  signInWithGoogle: (requestGmailAccess?: boolean) => Promise<void>;
  signUp: (email: string, password: string, fullName: string) => Promise<void>;
  signOut: () => Promise<void>;
  connectGmail: () => Promise<void>;
  isGmailConnected: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isGmailConnected, setIsGmailConnected] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (window.location.hash && window.location.hash.includes('access_token')) {
      setLoading(true);
      
      const handleHashChange = async () => {
        try {
          const { data, error } = await supabase.auth.getSession();
          
          if (error) {
            console.error('Error getting session from hash:', error);
            toast.error('Error during authentication');
          } else {
            console.log('Successfully got session from hash:', data);
          }
        } catch (err) {
          console.error('Unexpected error during authentication:', err);
          toast.error('Unexpected error during authentication');
        } finally {
          window.history.replaceState({}, document.title, window.location.pathname);
          setLoading(false);
        }
      };
      
      handleHashChange();
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      
      if (session?.user) {
        const gmailConnected = session.user.user_metadata?.gmail_connected || false;
        setIsGmailConnected(gmailConnected);
      }
      
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
        setUser(session?.user ?? null);
        
        if (session?.user) {
          const gmailConnected = session.user.user_metadata?.gmail_connected || false;
          setIsGmailConnected(gmailConnected);
        } else {
          setIsGmailConnected(false);
        }
        
        setLoading(false);
        
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

  const signInWithGoogle = async (requestGmailAccess = false) => {
    try {
      setLoading(true);
      
      const options: any = {
        redirectTo: `${window.location.origin}`,
      };
      
      if (requestGmailAccess) {
        options.scopes = 'https://www.googleapis.com/auth/gmail.readonly';
        options.queryParams = {
          access_type: 'offline',
          prompt: 'consent',
        };
      }
      
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options,
      });
      
      if (error) {
        throw error;
      }
      
    } catch (error: any) {
      toast.error(error.message || 'Error signing in with Google');
      console.error('Error signing in with Google:', error);
      setLoading(false);
    }
  };

  const connectGmail = async () => {
    try {
      setLoading(true);
      
      const { data: { session: currentSession } } = await supabase.auth.getSession();
      
      // If we have a valid session but need to refresh the Gmail token
      if (currentSession?.user && isGmailConnected) {
        console.log('Refreshing Gmail token...');
      }
      
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/profile`,
          // Update to include full Gmail access scope to read messages and specifically request offline access
          scopes: 'https://www.googleapis.com/auth/gmail.readonly https://mail.google.com/',
          queryParams: {
            access_type: 'offline',
            prompt: 'consent',
            // Force approval prompt to get a refresh token every time
            approval_prompt: 'force',
          } as any,
        },
      });
      
      if (error) {
        throw error;
      }
      
      toast.info('Connecting to Gmail...');
      
      await supabase.auth.updateUser({
        data: { gmail_connected: true }
      });
      
      setIsGmailConnected(true);
      
    } catch (error: any) {
      toast.error(error.message || 'Error connecting Gmail');
      console.error('Error connecting Gmail:', error);
    } finally {
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
    <AuthContext.Provider value={{ 
      session, 
      user, 
      loading, 
      signIn, 
      signInWithGoogle, 
      signUp, 
      signOut,
      connectGmail,
      isGmailConnected
    }}>
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
