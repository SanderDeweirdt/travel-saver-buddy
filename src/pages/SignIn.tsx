
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import SignInForm from '@/components/auth/SignInForm';
import { toast } from 'sonner';

const SignIn = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  useEffect(() => {
    // Check if user is already logged in
    const checkSession = async () => {
      const { data } = await supabase.auth.getSession();
      if (data.session) {
        navigate('/dashboard');
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
        toast.success('Successfully signed in!');
        navigate('/dashboard');
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
