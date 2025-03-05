
import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Link, Navigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Mail, Lock, ArrowRight, AlertCircle } from 'lucide-react';

const SignIn = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const { signIn, user, loading } = useAuth();

  // Redirect if already logged in
  if (user) {
    return <Navigate to="/" />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!email.trim() || !password.trim()) {
      setFormError('Please enter both email and password');
      return;
    }
    
    if (!email.includes('@')) {
      setFormError('Please enter a valid email address');
      return;
    }
    
    setFormError(null);
    await signIn(email, password);
  };
  
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gray-50">
      <div className="bg-white p-6 rounded-xl shadow-elevation-2 w-full max-w-md">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-semibold">Welcome back</h2>
          <p className="text-muted-foreground mt-1">Sign in to your Travel Buddy account</p>
        </div>
        
        {formError && (
          <div className="mb-5 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start space-x-2">
            <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
            <span className="text-sm text-red-700">{formError}</span>
          </div>
        )}
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="email"
                type="email"
                placeholder="Enter your email"
                className="pl-9"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                className="pl-9"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>
          
          <Button 
            type="submit" 
            className="w-full" 
            disabled={loading}
          >
            {loading ? (
              <span className="flex items-center">
                <span className="mr-2">Signing in</span>
                <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              </span>
            ) : (
              <span className="flex items-center">
                Sign in
                <ArrowRight className="ml-2 h-4 w-4" />
              </span>
            )}
          </Button>
        </form>
        
        <div className="mt-6 text-center text-sm">
          <span className="text-muted-foreground">Don't have an account?</span>{" "}
          <Link to="/signup" className="text-primary font-medium hover:underline">
            Sign up
          </Link>
        </div>
      </div>
    </div>
  );
};

export default SignIn;
