
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { supabase, ensureUserProfile } from '@/integrations/supabase/client';
import SignInForm from '@/components/auth/SignInForm';
import { toast } from 'sonner';

const SignIn = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Get the redirect path from location state or default to dashboard
  const from = location.state?.from?.pathname || '/dashboard';
  
  useEffect(() => {
    // Check if user is already logged in
    const checkSession = async () => {
      try {
        const { data, error } = await supabase.auth.getSession();
        
        if (error) {
          console.error('Error checking session:', error);
          return;
        }
        
        if (data.session) {
          console.log('User already logged in, redirecting to dashboard');
          navigate('/dashboard', { replace: true });
        }
      } catch (err) {
        console.error('Unexpected error checking session:', err);
      }
    };
    
    checkSession();
  }, [navigate]);
  
  const handleSignIn = async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password
      });
      
      if (error) {
        throw error;
      }
      
      if (data.user) {
        console.log('Sign in successful, user ID:', data.user.id);
        toast.success('Successfully signed in!');
        
        // Make multiple attempts to ensure the profile exists
        let profileSuccess = false;
        let attempts = 0;
        const maxAttempts = 3;
        
        while (!profileSuccess && attempts < maxAttempts) {
          attempts++;
          
          try {
            console.log(`Attempting to verify/create profile (attempt ${attempts}/${maxAttempts})`);
            profileSuccess = await ensureUserProfile(data.user.id, data.user.email);
            
            if (profileSuccess) {
              console.log('Profile verification successful');
              break;
            }
            
            // Small delay between attempts
            if (attempts < maxAttempts) {
              await new Promise(resolve => setTimeout(resolve, 1000));
            }
          } catch (profileErr) {
            console.error(`Profile check attempt ${attempts} failed:`, profileErr);
          }
        }
        
        if (!profileSuccess) {
          console.warn('Failed to verify or create profile after multiple attempts');
          toast.warning('Profile setup may be incomplete. Some features may be limited.');
        }
        
        // Navigate to the requested page or dashboard
        // Add a slight delay to ensure the auth state is updated
        setTimeout(() => {
          navigate(from, { replace: true });
        }, 500);
      }
    } catch (err: any) {
      console.error('Error signing in:', err);
      setError(err.message || 'An error occurred during sign in');
      toast.error(err.message || 'Sign in failed');
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleGoogleSignIn = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        }
      });
      
      if (error) {
        throw error;
      }
      // Don't set isLoading to false here as we're redirecting to Google
    } catch (err: any) {
      console.error('Error signing in with Google:', err);
      setError(err.message || 'An error occurred during sign in');
      toast.error(err.message || 'Sign in with Google failed');
      setIsLoading(false);
    }
  };
  
  return (
    <div className="min-h-screen flex flex-col bg-muted/30">
      <div className="container max-w-7xl mx-auto px-4 py-16 flex-1 flex flex-col justify-center items-center">
        <SignInForm 
          onSignIn={handleSignIn} 
          onGoogleSignIn={handleGoogleSignIn}
          isLoading={isLoading}
          error={error || undefined}
          className="w-full max-w-md"
        />
      </div>
    </div>
  );
};

export default SignIn;
