
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
    const checkSession = () => {
      const storedUser = localStorage.getItem('mockUser');
      if (storedUser) {
        console.log('User already logged in, redirecting to dashboard');
        navigate('/dashboard', { replace: true });
      }
    };
    
    checkSession();
  }, [navigate]);
  
  const handleSignIn = async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);
    
    try {
      // Simulate authentication delay
      await new Promise(resolve => setTimeout(resolve, 800));
      
      // For demo purposes, any email/password combination works
      const mockUser = {
        id: '12345',
        email: email
      };
      
      // Store in localStorage for our mock auth
      localStorage.setItem('mockUser', JSON.stringify(mockUser));
      
      console.log('Sign in successful, user ID:', mockUser.id);
      toast.success('Successfully signed in!');
      
      // Navigate to the requested page or dashboard
      navigate(from, { replace: true });
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
      // Simulate authentication delay
      await new Promise(resolve => setTimeout(resolve, 800));
      
      // Mock Google auth
      const mockUser = {
        id: 'google-user-123',
        email: 'google-user@example.com'
      };
      
      localStorage.setItem('mockUser', JSON.stringify(mockUser));
      toast.success('Successfully signed in with Google!');
      navigate(from, { replace: true });
    } catch (err: any) {
      console.error('Error signing in with Google:', err);
      setError(err.message || 'An error occurred during sign in');
      toast.error(err.message || 'Sign in with Google failed');
    } finally {
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
