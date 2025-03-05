
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

const AuthCallback = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Create a mock user for the OAuth callback
    const mockOAuthUser = {
      id: 'oauth-' + Math.random().toString(36).substring(2, 9),
      email: 'oauth-user@example.com'
    };
    
    // Store user in localStorage for our mock auth
    localStorage.setItem('mockUser', JSON.stringify(mockOAuthUser));
    
    // Show success message
    toast.success('Successfully authenticated!');
    
    // Navigate to dashboard
    setTimeout(() => {
      navigate('/dashboard', { replace: true });
    }, 1000);
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30">
      <div className="text-center">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
        <p className="text-muted-foreground">Completing authentication...</p>
      </div>
    </div>
  );
};

export default AuthCallback;
