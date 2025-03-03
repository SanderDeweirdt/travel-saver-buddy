
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

const AuthCallback = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const handleAuthCallback = async () => {
      try {
        console.log('Handling OAuth callback...');
        // Get the session after OAuth sign in/up
        const { data, error } = await supabase.auth.getSession();
        
        if (error) {
          console.error('Error getting session:', error);
          toast.error('Authentication failed. Please try again.');
          navigate('/signin');
          return;
        }
        
        if (!data.session) {
          console.error('No session found after OAuth callback');
          toast.error('No session found. Please sign in again.');
          navigate('/signin');
          return;
        }
        
        console.log('OAuth session found, user ID:', data.session.user.id);
        
        // Verify the profile exists and create it if needed
        const userId = data.session.user.id;
        const userEmail = data.session.user.email;
        
        // First check if profile exists
        const { data: profileData, error: profileError } = await supabase
          .from('profiles')
          .select('id')
          .eq('id', userId)
          .single();
          
        // If no profile or error (except "no rows returned"), create one
        if (!profileData || (profileError && profileError.code === 'PGRST116')) {
          console.log('Creating profile for OAuth user:', userId);
          
          // Try to create the profile
          const { error: insertError } = await supabase
            .from('profiles')
            .insert([{ 
              id: userId,
              email: userEmail,
            }])
            .select('id')
            .single();
              
          if (insertError) {
            console.error('Error creating profile in OAuth callback:', insertError);
            
            // Only show warning but continue with authentication since the
            // user is already authenticated - they'll just have limited functionality
            toast.warning('Failed to create user profile. Some features may be limited.');
          } else {
            console.log('Successfully created profile for OAuth user');
          }
        } else if (profileError && profileError.code !== 'PGRST116') {
          console.error('Error checking profile in OAuth callback:', profileError);
          toast.warning('Error checking user profile. Some features may be limited.');
        } else {
          console.log('Profile already exists for OAuth user');
        }
        
        // Verify the profile exists before redirecting, with retries
        let profileVerified = false;
        
        for (let attempt = 1; attempt <= 3; attempt++) {
          console.log(`Verifying profile exists (attempt ${attempt}/3)`);
          const { data: verifyData, error: verifyError } = await supabase
            .from('profiles')
            .select('id')
            .eq('id', userId)
            .single();
              
          if (verifyData && !verifyError) {
            profileVerified = true;
            console.log('Profile verified successfully');
            break;
          }
          
          if (verifyError) {
            console.error(`Profile verification error (attempt ${attempt}/3):`, verifyError);
          }
          
          // Wait a bit before retrying (400ms, 800ms, 1200ms)
          if (attempt < 3) {
            await new Promise(resolve => setTimeout(resolve, attempt * 400));
          }
        }
        
        if (profileVerified) {
          // Redirect to dashboard on successful login
          toast.success('Successfully signed in!');
        } else {
          // Show warning but still allow navigation
          toast.warning('Profile setup may be incomplete. Some features may be limited.');
        }
        
        // Add a slight delay to ensure toast is visible
        setTimeout(() => {
          navigate('/dashboard', { replace: true });
        }, 800);
      } catch (error) {
        console.error('Unexpected error during authentication:', error);
        toast.error('An unexpected error occurred');
        navigate('/signin');
      } finally {
        setIsLoading(false);
      }
    };

    handleAuthCallback();
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30">
      <div className="text-center">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
        <p className="text-muted-foreground">
          {isLoading ? 'Completing authentication...' : 'Redirecting...'}
        </p>
      </div>
    </div>
  );
};

export default AuthCallback;
