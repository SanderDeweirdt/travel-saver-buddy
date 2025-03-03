
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
        // Get the session after OAuth sign in/up
        const { data, error } = await supabase.auth.getSession();
        
        if (error) {
          console.error('Error getting session:', error);
          toast.error('Authentication failed. Please try again.');
          navigate('/signin');
          return;
        }
        
        if (data.session) {
          // Verify the profile exists
          const { data: profileData, error: profileError } = await supabase
            .from('profiles')
            .select('id')
            .eq('id', data.session.user.id)
            .single();
            
          // If no profile or PGRST116, create one
          if ((!profileData || (profileError && profileError.code === 'PGRST116'))) {
            console.log('Creating profile for OAuth user:', data.session.user.id);
            
            // Try to create the profile
            const { error: insertError } = await supabase
              .from('profiles')
              .insert([
                { 
                  id: data.session.user.id,
                  email: data.session.user.email,
                }
              ])
              .select('id')
              .single();
              
            if (insertError) {
              console.error('Error creating profile in OAuth callback:', insertError);
              
              // Don't fail the whole login flow, but show a warning
              toast.warning('Failed to create user profile. Some features may be limited.');
            } else {
              console.log('Successfully created profile for OAuth user');
            }
          } else if (profileError && profileError.code !== 'PGRST116') {
            console.error('Error checking profile in OAuth callback:', profileError);
          } else {
            console.log('Profile already exists for OAuth user');
          }
          
          // Verify the profile actually exists before redirecting
          // Try up to 3 times with a delay
          let profileVerified = false;
          
          for (let attempt = 1; attempt <= 3; attempt++) {
            const { data: verifyData } = await supabase
              .from('profiles')
              .select('id')
              .eq('id', data.session.user.id)
              .single();
              
            if (verifyData) {
              profileVerified = true;
              break;
            }
            
            // Wait a bit before retrying (300ms, 600ms, 900ms)
            if (attempt < 3) {
              await new Promise(resolve => setTimeout(resolve, attempt * 300));
            }
          }
          
          if (profileVerified) {
            // Redirect to dashboard on successful login
            toast.success('Successfully signed in!');
          } else {
            // Show warning but still allow navigation
            toast.warning('Profile setup may be incomplete. Some features may be limited.');
          }
          
          navigate('/dashboard');
        } else {
          toast.error('No session found. Please sign in again.');
          navigate('/signin');
        }
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
