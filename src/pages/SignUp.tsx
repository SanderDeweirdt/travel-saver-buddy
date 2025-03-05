
import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Link, Navigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Mail, Lock, User, ArrowRight, AlertCircle } from 'lucide-react';

const SignUp = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const { signUp, user, loading } = useAuth();

  // Redirect if already logged in
  if (user) {
    return <Navigate to="/" />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!email.trim() || !password.trim() || !confirmPassword.trim() || !fullName.trim()) {
      setFormError('Please fill in all fields');
      return;
    }
    
    if (!email.includes('@')) {
      setFormError('Please enter a valid email address');
      return;
    }
    
    if (password.length < 6) {
      setFormError('Password must be at least 6 characters');
      return;
    }
    
    if (password !== confirmPassword) {
      setFormError('Passwords do not match');
      return;
    }
    
    setFormError(null);
    await signUp(email, password, fullName);
  };
  
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gray-50">
      <div className="bg-white p-6 rounded-xl shadow-elevation-2 w-full max-w-md">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-semibold">Create an account</h2>
          <p className="text-muted-foreground mt-1">Sign up for your Travel Buddy account</p>
        </div>
        
        {formError && (
          <div className="mb-5 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start space-x-2">
            <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
            <span className="text-sm text-red-700">{formError}</span>
          </div>
        )}
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="fullName">Full Name</Label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="fullName"
                type="text"
                placeholder="Enter your full name"
                className="pl-9"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>
          
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
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="password"
                type="password"
                placeholder="Create a password"
                className="pl-9"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm Password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="confirmPassword"
                type="password"
                placeholder="Confirm your password"
                className="pl-9"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
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
                <span className="mr-2">Creating account</span>
                <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              </span>
            ) : (
              <span className="flex items-center">
                Sign up
                <ArrowRight className="ml-2 h-4 w-4" />
              </span>
            )}
          </Button>
        </form>
        
        <div className="mt-6 text-center text-sm">
          <span className="text-muted-foreground">Already have an account?</span>{" "}
          <Link to="/signin" className="text-primary font-medium hover:underline">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
};

export default SignUp;
