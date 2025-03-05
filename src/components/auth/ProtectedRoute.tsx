
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useState, useEffect } from 'react';
import { toast } from 'sonner';

type ProtectedRouteProps = {
  children: React.ReactNode;
};

const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [isTimeout, setIsTimeout] = useState(false);

  // Add a timeout to prevent infinite loading
  useEffect(() => {
    if (loading) {
      const timer = setTimeout(() => {
        console.log('Authentication verification timed out');
        setIsTimeout(true);
        toast.error('Authentication verification timed out. Please try signing in again.');
      }, 2000); // 2 second timeout

      return () => clearTimeout(timer);
    }
  }, [loading]);

  // Handle authentication timeout
  if (isTimeout) {
    console.log('Authentication timed out, redirecting to signin');
    return <Navigate to="/signin" state={{ from: location, error: "Authentication timed out" }} replace />;
  }

  // Show loading state while checking authentication
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-muted-foreground">Verifying your authentication...</p>
        </div>
      </div>
    );
  }

  // If not authenticated, redirect to signin page and save the attempted location
  if (!user) {
    console.log('User not authenticated, redirecting to signin');
    return <Navigate to="/signin" state={{ from: location }} replace />;
  }

  // User is authenticated, render the protected content
  return <>{children}</>;
};

export default ProtectedRoute;
