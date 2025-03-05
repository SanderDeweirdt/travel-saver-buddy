
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
          // Check if profile exists
          const { data: profileData, error: profileError } = await supabase
            .from('profiles')
            .select('*')
            .eq('id', data.session.user.id)
            .single();
            
          if (profileError && profileError.code !== 'PGRST116') {
            console.error('Error fetching profile:', profileError);
          }
          
          // If profile doesn't exist, create one
          if (!profileData) {
            const { error: insertError } = await supabase
              .from('profiles')
              .insert([
                { 
                  id: data.session.user.id,
                  email: data.session.user.email,
                }
              ]);
              
            if (insertError) {
              console.error('Error creating profile:', insertError);
              toast.error('Failed to create user profile');
            }
          }
          
          // Redirect to dashboard on successful login
          toast.success('Successfully signed in!');
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
