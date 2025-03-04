
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

const AuthCallback = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleAuthCallback = async () => {
      try {
        console.log('Handling OAuth callback...');
        // Get the session after OAuth sign in/up
        const { data, error } = await supabase.auth.getSession();
        
        if (error) {
          console.error('Error getting session:', error);
          setError('Authentication failed. Please try again.');
          toast.error('Authentication failed. Please try again.');
          setTimeout(() => navigate('/signin'), 1500);
          return;
        }
        
        if (!data.session) {
          console.error('No session found after OAuth callback');
          setError('No session found. Please sign in again.');
          toast.error('No session found. Please sign in again.');
          setTimeout(() => navigate('/signin'), 1500);
          return;
        }
        
        console.log('OAuth session found, user ID:', data.session.user.id);
        
        // Use simplified profile creation logic
        const userId = data.session.user.id;
        const userEmail = data.session.user.email;
        
        try {
          // Check if profile exists
          const { data: profiles, error: profileError } = await supabase
            .from('profiles')
            .select('id')
            .eq('id', userId);
            
          if (profileError) {
            console.error('Error checking profile:', profileError);
          }
          
          // Create profile if it doesn't exist
          if (!profiles || profiles.length === 0) {
            console.log('Creating profile for user:', userId);
            const { error: insertError } = await supabase
              .from('profiles')
              .insert([{ 
                id: userId, 
                email: userEmail || '' 
              }]);
              
            if (insertError) {
              console.error('Error creating profile:', insertError);
              toast.warning('Profile setup may be incomplete. Some features may be limited.');
            } else {
              toast.success('Profile created successfully!');
            }
          } else {
            toast.success('Successfully signed in!');
          }
        } catch (profileErr) {
          console.error('Error in profile management:', profileErr);
          toast.warning('Profile setup may be incomplete. Some features may be limited.');
        }
        
        // Navigate to dashboard with delay to ensure auth state is updated
        setTimeout(() => {
          navigate('/dashboard', { replace: true });
        }, 1000);
      } catch (error: any) {
        console.error('Unexpected error during authentication:', error);
        setError(error.message || 'An unexpected error occurred');
        toast.error(error.message || 'An unexpected error occurred');
        setTimeout(() => navigate('/signin'), 1500);
      } finally {
        setIsLoading(false);
      }
    };

    handleAuthCallback();
  }, [navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-muted/30">
        <div className="text-center">
          <div className="text-red-500 mb-4">
            <svg className="h-12 w-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold mb-2">Authentication Error</h2>
          <p className="text-muted-foreground">{error}</p>
          <button 
            onClick={() => navigate('/signin')}
            className="mt-6 bg-primary text-white px-4 py-2 rounded-md hover:bg-primary/90 transition-colors"
          >
            Return to Sign In
          </button>
        </div>
      </div>
    );
  }

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
